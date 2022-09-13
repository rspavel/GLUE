import copy
import warnings

import numpy as np
# Built with numpy '1.16.3', also tested with 1.21.5

import torch
import torch.utils.data
# Built with pytorch 1.3.1, also tested with 1.13b

import sklearn.metrics

# Built with sklearn 0.20.1, also tested with 1.1.1

torch.set_default_dtype(torch.float64)

from alInterface import getAllGNDData
from glueCodeTypes import SolverCode, BGKInputs, BGKOutputs


class Model():
    """
    Base class for a data-driven surrogate model.
    """

    def __init__(self, solver, networks, uq_fussyness, err_info=None):
        self.networks = networks
        self.err_info = err_info
        self.solver = solver
        self.uq_fussyness = uq_fussyness

    def __call__(self, request_params):
        """
        :param request_params: BGKInputs
        :return: result, errorbar
        """
        request_params = self.pack_inputs(request_params)

        result_mean, result_error = self.process(request_params)

        result_mean = self.unpack_outputs(result_mean)
        result_error = self.unpack_outputs(result_error)
        return result_mean, result_error

    def process(self, request_params, perform_column_extraction=True):  # as a numpy array
        """

        :param request_params:
        :param perform_column_extraction:
        :return: mean, standard deviation
        """
        batched = request_params.ndim > 1

        request_params = torch.as_tensor(request_params)
        if perform_column_extraction:
            request_params = request_params[..., SOLVER_INDEXES[self.solver]["input_slice"]]

        if not batched:
            request_params = request_params.unsqueeze(0)

        results = np.asarray([np.asarray(nn(request_params)) for nn in self.networks])

        mean = results.mean(axis=0)
        std = results.std(axis=0)

        if not batched:
            mean = mean[0]
            std = std[0]

        return mean, std

    def calibrate(self, dataset):
        """
        Set this Model to estimate uncertainty based on the comparison of
        the spread of predictions compared to the average spread of predictions on
        the training data.
        :param dataset:
        :return: None
        """
        pred, uncertainty = self.process(dataset[:][0].numpy(), perform_column_extraction=False)
        true = dataset[:][-1].numpy()
        abserr = np.abs(pred - true)

        calibration = np.mean(abserr, axis=0) / np.mean(uncertainty, axis=0)

        # Factor 3 is somewhat arbitrary... larger -> less fussy model.
        # Roughly corresponds to inverse number of standard deviations
        calibration *= self.uq_fussyness

        self.err_info /= calibration

        inactive_columns = (np.std(abserr, axis=0) == 0) & (np.std(uncertainty, axis=0) == 0)

        warnings.warn(
            "Inactive columns detected: {} , they will not be included in isokay.".format(np.where(inactive_columns)))
        self.err_info[inactive_columns] = np.inf

    def process_iserrok_fuzzy(self, errbars):
        """
        Core logic for if the error bars on a prediction are small or not
        A value of 1 or greater is a large error bar.

        :param errbars:
        :return: float
        """
        return errbars / self.err_info

    def process_iserrok(self, errbars):
        """
        Core logic for deciding if a point needs to be run with fine grained solver
        :param errbars:
        :return: boolean
        """
        return errbars < self.err_info

    def iserrok(self, errbars):
        """
        Return floating point representation of prediction uncertainty
        :param errbars:
        :return: prediction uncertainty
        """
        errbars = self.pack_outputs(errbars)
        iserrok = self.process_iserrok(errbars)
        iserrok = self.unpack_outputs(iserrok)
        return iserrok

    def iserrok_fuzzy(self, errbars):
        """
        Return boolean representation of prediction uncertainty
        :param errbars:
        :return: bool-> True if error bars are small, large if error bars are not small.
        """
        errbars = self.pack_outputs(errbars)
        iserrok = self.process_iserrok_fuzzy(errbars)
        iserrok = self.unpack_outputs(iserrok)
        return iserrok

    # The following 3 methods are solver-specific, converting between
    # NamedTuples for the specific solver to array formats.

    def pack_outputs(self, request):
        """

        :param request: NamedTuple for input space for coarse solver
        :return: array form
        """
        return NotImplemented

    def pack_inputs(self, request):
        """

        :param request: NamedTuple of inputs
        :return:  array version of inputs
        """
        return NotImplemented

    def unpack_outputs(self, result):
        """

        :param result: array of outputs
        :return: appropriate NamedTuple for the solver
        """
        return NotImplemented


# # BGKInputs
# #  Temperature: float
# #  Density: float[4]
# #  Charges: float[4]
# BGKInputs = collections.namedtuple('BGKInputs', 'Temperature Density Charges')
# # BGKoutputs
# #  Viscosity: float
# #  ThermalConductivity: float
# #  DiffCoeff: float[10]
# BGKOutputs = collections.namedtuple('BGKOutputs', 'Viscosity ThermalConductivity DiffCoeff')

class BGKModel(Model):
    """
    Concrete Model class for BGK problem.
    """

    def pack_outputs(self, outputs):
        output_vals = np.concatenate([[outputs.Viscosity], [outputs.ThermalConductivity], outputs.DiffCoeff])
        return output_vals

    def pack_inputs(self, request):
        packed_request = np.concatenate([[request.Temperature], request.Density, request.Charges])

        return packed_request

    def unpack_outputs(self, packed_result):
        # All things predicted
        v = packed_result[0]
        tc = packed_result[1]
        diff = packed_result[2:]
        unpacked_result = BGKOutputs(v, tc, diff)
        return unpacked_result


# Parameters governing input and outputs to problem
SOLVER_INDEXES = {
    SolverCode.BGK: dict(
        input_slice=slice(0, 9),  # slice of the data to use for input features
        output_slice=slice(10, 22),  # slice of the data to use for output features
        n_inputs=9,  # total number of inputs
        n_outputs=12,  # total number of outputs
        model_type=BGKModel,  # What model class to use with this solver
    )
    # Other solver codes can be added here...
}

# Parameters governing network structure
DEFAULT_NET_CONFIG = dict(
    n_layers=6,
    n_hidden=64,
    activation_type=torch.nn.ReLU,
    layer_type=torch.nn.Linear
)

# Parameters for ensemble uncertainty
DEFAULT_ENSEMBLE_CONFIG = dict(
    n_members=5,
    test_fraction=0.1,  # Test fraction for each ensemble member
    score_thresh=0.7,  # R^2 score minimum per task for a network to be considered acceptable
    max_model_tries=200,  # Number of retries in order to find n_members good networks.
)

# Parameters for the optimization process
DEFAULT_TRAINING_CONFIG = dict(
    n_epochs=2000,  # how long to train
    optimizer_type=torch.optim.Adam,  # what to optimize with
    validation_fraction=0.1,  # fraction to use for early stopping
    lr=1e-3,  # initial learning rate
    patience=20,  # patience for learning rate
    batch_size=50,  # batch size
    eval_batch_size=10000,  # batch size for non-training evaluations
    scheduler_type=torch.optim.lr_scheduler.ReduceLROnPlateau,  # plan for scheduling learning rate
    cost_type=torch.nn.MSELoss  # loss function to train with
)

# Bundle of all learning-related parameters
DEFAULT_LEARNING_CONFIG = dict(
    net_config=DEFAULT_NET_CONFIG,
    ensemble_config=DEFAULT_ENSEMBLE_CONFIG,
    solver_type=SolverCode.BGK,
    training_config=DEFAULT_TRAINING_CONFIG,
    uq_fussyness=1 / 3.,  # Factor 1/3 is somewhat arbitrary... smaller-> less points flagged as bad.
    # Roughly corresponds to inverse number of standard deviations
)


def assemble_dataset(raw_dataset, solver_code):
    """
    Convert database from numpy to pytorch
    :param raw_dataset: the numpy arrays for the dataset
    :param solver_code: what coarse-grained solver is being run
    :return: dataset
    """
    features = torch.as_tensor(raw_dataset[:, SOLVER_INDEXES[solver_code]["input_slice"]])
    targets = torch.as_tensor(raw_dataset[:, SOLVER_INDEXES[solver_code]["output_slice"]])

    return torch.utils.data.TensorDataset(features, targets)


# prototype, only covers ensemble uncertainties
def retrain(db_handle, learning_config=DEFAULT_LEARNING_CONFIG):
    """
    Function to train a network to a database
    :param db_handle: name for the database
    :param learning_config: configuration for the learner
    :return: new surrogate model based on the database
    """
    solver = learning_config["solver_type"]
    raw_dataset = getAllGNDData(db_handle, solver)
    full_dataset = assemble_dataset(raw_dataset, solver)

    ensemble_config = learning_config["ensemble_config"]
    n_total = len(full_dataset)
    n_test = int(ensemble_config["test_fraction"] * n_total)
    n_test = max(n_test, 2)
    n_train = n_total - n_test
    print("Total / train / test points:", n_total, n_train, n_test)

    networks = []
    network_errors = []
    network_scores = []

    successful_models = 0
    i = 0
    while successful_models < ensemble_config["n_members"]:
        print("Training model {}".format(i))
        i += 1
        if i > ensemble_config["max_model_tries"]:
            break
        print("Good models found:", successful_models)
        print("Training ensemble member", i)

        train_data, test_data = torch.utils.data.random_split(full_dataset, (n_train, n_test))

        # This is a place where we could trivially parallelize training.

        this_model = train_single_model(train_data, learning_config=learning_config)
        model_score, model_errors = get_error_info(this_model, test_data)
        print("Score:", model_score)
        if any(m < ensemble_config["score_thresh"] for m in model_score):
            print("Rejected.")
            continue
        print("Accepted.")

        successful_models += 1

        networks.append(this_model)
        network_scores.append(model_score)
        network_errors.append(model_errors)

    error_info = np.mean(np.asarray(network_errors), axis=0)

    uq_fussyness = learning_config["uq_fussyness"]
    full_model = SOLVER_INDEXES[solver]["model_type"](solver, networks, uq_fussyness, error_info)
    full_model.calibrate(full_dataset)

    return full_model


def train_single_model(train_data, learning_config):
    """
    Train a single network to the training data.
    :param train_data: dataset for training
    :param learning_config: configuration for training
    :return: a network
    """
    net_config = learning_config["net_config"]
    training_config = learning_config["training_config"]

    # Type parameters
    activation_type = net_config["activation_type"]
    layer_type = net_config["layer_type"]

    # Splitting
    n_total = len(train_data)
    n_valid = int(training_config["validation_fraction"] * n_total)
    n_valid = max(n_valid, 2)
    n_train = n_total - n_valid
    # print(type(train_data),type(train_data[:]))

    # Stupid fix for now, but this trick doesn't hurt anything and enables the #Normalizing line to work
    train_data.indices = np.asarray(train_data.indices)
    train_data, valid_data = torch.utils.data.random_split(train_data, (n_train, n_valid))
    # print(type(train_data),type(train_data[:]))

    # Normalizing
    train_features, train_labels = (train_data[:])

    inscaler = Scaler.from_tensor(train_features)
    cost_scaler = Scaler.from_tensor(train_labels)
    outscaler = Scaler.from_inversion((cost_scaler))

    # Size parameters
    solver = learning_config["solver_type"]
    indices = SOLVER_INDEXES[solver]

    n_inputs = indices["n_inputs"]
    n_outputs = indices["n_outputs"]
    n_hidden = net_config["n_hidden"]

    layers = [inscaler, layer_type(n_inputs, n_hidden), activation_type()]

    for i in range(net_config["n_layers"] - 2):
        layers.append(layer_type(n_hidden, n_hidden))
        layers.append(activation_type())
    layers.append(layer_type(n_hidden, n_outputs))

    train_network = torch.nn.Sequential(*layers)

    cost_fn = training_config["cost_type"]()
    opt = training_config["optimizer_type"](train_network.parameters(), lr=training_config["lr"])
    patience = training_config["patience"]
    scheduler = training_config["scheduler_type"](opt, patience=patience, verbose=False, factor=0.5)

    best_cost = np.inf
    boredom = 0
    best_params = train_network.state_dict()

    train_dloader = torch.utils.data.DataLoader(train_data, batch_size=training_config["batch_size"], shuffle=True)
    valid_dloader = torch.utils.data.DataLoader(valid_data, batch_size=training_config["eval_batch_size"],
                                                shuffle=False)

    # Need to add scales for costs
    for i in range(training_config["n_epochs"]):
        train_epoch(train_dloader, train_network, cost_fn, opt, scaler=cost_scaler)
        eval_cost = evaluate_dataset_errors(valid_dloader, train_network, scaler=cost_scaler).abs().mean().item()
        scheduler.step(eval_cost)
        if eval_cost < best_cost:
            best_cost = eval_cost
            best_params = copy.deepcopy(train_network.state_dict())
            boredom = 0
        else:
            boredom += 1

        if boredom > 2 * patience + 1:
            print("Training finalized at epoch", i)
            break
    else:
        print("Training finished due to max epoch", i)

    train_network.load_state_dict(best_params)
    real_scale_network = torch.nn.Sequential(*train_network[:], outscaler)

    for param in real_scale_network.parameters():
        param.requires_grad_(False)

    return real_scale_network


def train_epoch(train_data, network, cost_fn, opt, scaler):
    for batch_in, batch_out in train_data:
        opt.zero_grad()
        batch_pred = network(batch_in)
        cost = cost_fn(batch_pred, scaler(batch_out))
        cost.backward()
        opt.step()


def evaluate_dataset_errors(dloader, network, scaler, show=False):
    predicted = []
    true = []
    with torch.autograd.no_grad():
        for bin, bout in dloader:

            bpred = network(bin)
            if scaler is not None:
                bout = scaler(bout)

            true.append(bout)
            predicted.append(bpred)

    true = torch.cat(true, dim=0)
    predicted = torch.cat(predicted, dim=0)
    err = predicted - true

    return err


def l1_score(true, predicted):
    """
    L1 version of R^2 score. 1-> perfect model, 0->very bad model, lower-> terrible model
    :param true:
    :param predicted:
    :return:  nondimensional score
    """
    sum_abs_resid = np.abs(true - predicted).sum()
    med = np.median(true)
    sum_abs_dev = np.abs(true - med).sum()
    return 1 - sum_abs_resid / sum_abs_dev


def get_error_info(network, test_dset):
    """
    Get the error of a network on a test dataset
    :param network:
    :param test_dset:
    :return: the score for each of the tasks in the network
    """
    test_dloader = torch.utils.data.DataLoader(test_dset, batch_size=100, shuffle=False)

    error = evaluate_dataset_errors(test_dloader, network, scaler=None).numpy()
    true = test_dset[:][-1].numpy()
    predicted = true + error
    return get_score(predicted, true)


def get_score(predicted, true):
    """
    Get the score or a set of tasks.
    :param predicted:
    :param true:
    :return:
    """
    score = []
    rmse_list = []
    for i, (p, t) in enumerate(zip(predicted.T, true.T)):

        rmse = np.sqrt(sklearn.metrics.mean_squared_error(t, p))

        if p.std() < 1e-300 and t.std() < 1e-300:
            rsq = 1.
            l1resid = 1.
        else:
            rsq = sklearn.metrics.r2_score(t, p)
            l1resid = l1_score(t, p)

        # HARDCODED: SCORE FOR EACH THING TO PREDICT IS RSQ
        score.append(rsq)
        rmse_list.append(rmse)

    score = np.asarray(score)

    rmse_list = np.asarray(rmse_list)
    return score, rmse_list


class Scaler(torch.nn.Module):
    """
    A class for scaling input/output data so that
    the network can operate in a nondimensionalized space for each feature/target.
    """

    def __init__(self, means, stds, eps=1e-300):
        """
        Construct a new scaler
        :param means:
        :param stds:
        :param eps:
        """
        super().__init__()
        self.means = torch.nn.Parameter(means, requires_grad=False)
        self.stds = torch.nn.Parameter(stds, requires_grad=False)
        self.eps = eps

    @classmethod
    def from_tensor(cls, tensor):
        """
        Construct a scaler from a given tensor of shape (n_samples,n_features)
        :param tensor:
        :return: a new scaler
        """
        means = tensor.mean(dim=0)
        stds = tensor.std(dim=0)
        return cls(means, stds)

    @classmethod
    def from_inversion(cls, other):
        """
        Create a new scalar which is the inverse of a different scaler
        :param other: the sclar to invert
        :return: the new scaler
        """
        new_stds = 1 / (other.stds + other.eps)
        new_means = -other.means / (other.stds + other.eps)
        return cls(new_means, new_stds)

    def forward(self, tensor):
        return (tensor - self.means) / (self.stds + self.eps)

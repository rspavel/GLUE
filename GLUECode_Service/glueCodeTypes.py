from enum import Enum, IntEnum
import collections

class ALInterfaceMode(IntEnum):
    FGS = 0
    ACTIVELEARNER=2
    FAKE = 3
    DEFAULT = 4
    FASTFGS = 5
    ANALYTIC = 6
    KILL = 9

class SolverCode(Enum):
    BGK = 0
    LBMZEROD = 1
    BGKMASSES = 2

class ResultProvenance(IntEnum):
    FGS = 0
    ACTIVELEARNER = 2
    FAKE = 3
    FASTFGS = 5
    ANALYTIC = 6
    DB = 7

class LearnerBackend(IntEnum):
    MYSTIC = 1
    PYTORCH = 2
    FAKE = 3
    RANDFOREST = 4

class SchedulerInterface(IntEnum):
    SLURM = 0
    BLOCKING = 1
    FLUX = 2

class ProvisioningInterface(IntEnum):
    SPACK = 0
    MANUAL = 1

class DatabaseMode(IntEnum):
    SQLITE = 0
    MYSQL = 1
    HDF5 = 2

# BGKInputs
#  Temperature: float
#  Density: float[4]
#  Charges: float[4]
BGKInputs = collections.namedtuple('BGKInputs', 'Temperature Density Charges')
# BGKMassesInputs
#  Temperature: float
#  Density: float[4]
#  Charges: float[4]
#  Masses: float[4]
BGKMassesInputs = collections.namedtuple('BGKMassesInputs', 'Temperature Density Charges Masses')
# BGKoutputs
#  Viscosity: float
#  ThermalConductivity: float
#  DiffCoeff: float[10]
BGKOutputs = collections.namedtuple('BGKOutputs', 'Viscosity ThermalConductivity DiffCoeff')
# BGKMassesoutputs
#  Viscosity: float
#  ThermalConductivity: float
#  DiffCoeff: float[10]
BGKMassesOutputs = collections.namedtuple('BGKMassesOutputs', 'Viscosity ThermalConductivity DiffCoeff')

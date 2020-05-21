import numpy as np
import argparse
import os
from glueCodeTypes import ALInterfaceMode, SolverCode, ResultProvenance, LearnerBackend, BGKInputs, BGKMassesInputs, BGKOutputs, BGKMassesOutputs
from alInterface import  getAllGNDData, queueFGSJob
import getpass
import json
from glueArgParser import processGlueCodeArguments

def genTrainingData(configStruct, uname):
    code = configStruct['solverCode']
    reqid = 0
    pythonScriptDir = os.path.dirname(os.path.realpath(__file__))
    trainingDir = os.path.join(pythonScriptDir, "training")

    if code == SolverCode.BGK:
        csv = os.path.join(trainingDir, "bgk.csv")
        trainingEntries = np.loadtxt(csv)
        for row in trainingEntries:
            inArgs = BGKInputs(Temperature=row[0], Density=[row[1], row[2], 0.0, 0.0], Charges=[row[3], row[4], 0.0, 0.0])
            queueFGSJob(configStruct, uname, reqid, inArgs, 0, ALInterfaceMode.FGS)
            reqid += 1
    elif code == SolverCode.BGKMASSES:
        csv = os.path.join(trainingDir, "bgk_masses.csv")
        trainingEntries = np.loadtxt(csv)
        for row in trainingEntries:
            inArgs = BGKMassesInputs(Temperature=row[0], Density=[row[1], row[2], 0.0, 0.0], Charges=[row[3], row[4], 0.0, 0.0], Masses=[row[5], row[6], 0.0, 0.0])
            queueFGSJob(configStruct, uname, reqid, inArgs, 0, ALInterfaceMode.FGS)
            reqid += 1
    else:
        raise Exception('Using Unsupported Solver Code')

def printResults(gndTable, code):
    if code == SolverCode.BGK:
        header = "#"
        header += "InTemperature "
        for i in range(4):
            header += "InDensity[" + str(i) + "] "
        for i in range(4):
            header += "InCharges[" + str(i) + "] "
        header += "InVersion "
        header += "OutViscosity "
        header += "OutThermalConductivity "
        for i in range(10):
            header += "OutDiffusionCoefficient[" + str(i) + "] "
        header += "OutVersion "
        print(header)
        print(gndTable)
    else:
        raise Exception('Using Unsupported Solver Code')

if __name__ == "__main__":
    configStruct = processGlueCodeArguments()
    # We will not pass in uname via the json file
    uname =  getpass.getuser()
    if configStruct['GenerateTrainingData']:
        genTrainingData(configStruct, uname)
    if configStruct['ReadTrainingData']:
        results = getAllGNDData(fName, configStruct['solverCode'])
        printResults(results, configStruct['solverCode'])

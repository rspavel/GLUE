import argparse
from alInterface import  insertResult,  getGroundishTruthVersion, insertResultSlow
from glueCodeTypes import BGKOutputs, ALInterfaceMode, DatabaseMode, ResultProvenance, SolverCode, DatabaseMode
from ICF_Utils import write_output_coeff
from alDBHandlers import getDBHandle
import os
import re
import numpy as np

def speciesNotationToArrayIndex(in0, in1):
    (spec0, spec1) = sorted( (in0, in1) )
    if (spec0, spec1) == (0, 0):
        return 0
    elif (spec0, spec1) == (0, 1):
        return 1
    elif (spec0, spec1) == (0, 2):
        return 2
    elif (spec0, spec1) == (0, 3):
        return 3
    elif (spec0, spec1) == (1, 1):
        return 4
    elif (spec0, spec1) == (1, 2):
        return 5
    elif (spec0, spec1) == (1, 3):
        return 6
    elif (spec0, spec1) == (2, 2):
        return 7
    elif (spec0, spec1) == (2, 3):
        return 8
    elif (spec0, spec1) == (3, 3):
        return 9
    else:
        raise Exception('Improper Species Indices:' + str(spec0) + ',' + str(spec1))

def procBGKCSVFile(char, fname):
    retVal = -0.0
    stripString = char + '='
    with open(fname) as f:
        for line in f:
            stripString = line.strip(stripString)
            retVal = float(stripString)
    return retVal

def matchLammpsOutputsToArgs(outputDirectory):
    # Special thanks to Scot Halverson for figuring out clean solution
    diffCoeffs = 10*[0.0]
    visco = -0.0
    thermoCond = 0.0
    # Iterate over all output files
    for dirFile in os.listdir(outputDirectory):
        # Is this a diffusion output file?
        if re.match("diffusion_coefficient_\d+.csv", dirFile):
            # Pull the diffusion value out first
            diffVal = procBGKCSVFile('D', os.path.join(outputDirectory, dirFile))
            indexString = dirFile.replace("diffusion_coefficient_", "")
            indexString = indexString.replace(".csv", "")
            if len(indexString) != 2:
                raise Exception(dirFile + " is not mappable to a species index")
            # Map species indices to BGK indices
            outIndex = speciesNotationToArrayIndex( int(indexString[0]), int(indexString[1]) )
            # And write the result to the output array
            diffCoeffs[outIndex] = diffVal
        # Or is it a viscosity file?
        if re.match("viscosity_coefficient.csv", dirFile):
            visco = procBGKCSVFile('v', os.path.join(outputDirectory, dirFile))
        # Or a thermal conductivity file
        if re.match("conductivity_coefficient.csv", dirFile):
            thermoCond = procBGKCSVFile('k', os.path.join(outputDirectory, dirFile))
    return (diffCoeffs, visco, thermoCond)

def procOutputsAndProcess(tag, dbHandle, rank, reqid, lammpsMode, solverCode):
    if solverCode == SolverCode.BGK:
        # Pull densities
        densities = np.loadtxt("densities.txt")
        # Pull zeroes indices
        zeroDensitiesIndex = np.loadtxt("zeroes.txt").astype(int)
        # Generate coefficient files
        write_output_coeff(densities, zeroDensitiesIndex)
        # Get outputs array(s)
        (diffCoeffs, viscosity, thermalConductivity) = matchLammpsOutputsToArgs(os.getcwd())
        # Write results to an output namedtuple
        bgkOutput = BGKOutputs(Viscosity=viscosity, ThermalConductivity=thermalConductivity, DiffCoeff=diffCoeffs)
        # Write the tuple
        if(lammpsMode == ALInterfaceMode.FGS):
            insertResultSlow(rank, tag, reqid, bgkOutput, ResultProvenance.FGS, dbHandle)
        elif(lammpsMode == ALInterfaceMode.FASTFGS):
            insertResultSlow(rank, tag, reqid, bgkOutput, ResultProvenance.FASTFGS, dbHandle)
        else:
            raise Exception('Using Unsupported FGS Mode')
        outputList = []
        outputList.append(bgkOutput.Viscosity)
        outputList.append(bgkOutput.ThermalConductivity)
        outputList.extend(bgkOutput.DiffCoeff)
        outputList.append(getGroundishTruthVersion(SolverCode.BGK))
        return np.asarray(outputList)
    else:
        # Unknown solver code
        raise Exception('Not Implemented')

def insertGroundishTruth(dbHandle, outFGS, solverCode):
    if solverCode == SolverCode.BGK:
        #Pull data to write
        inFGS = np.loadtxt("inputs.txt")
        #np.savetxt("outputs.txt", outFGS)
        #Connect to DB
        dbHandle.openCursor()
        insString = "INSERT INTO BGKGND VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"
        insArgs = tuple(inFGS.tolist()) + tuple(outFGS.tolist())
        dbHandle.execute(insString, insArgs)
        dbHandle.commit()
        dbHandle.closeCursor()
    elif solverCode == SolverCode.BGKMASSES:
        #Pull data to write
        inFGS = np.loadtxt("inputs.txt")
        #np.savetxt("outputs.txt", outFGS)
        #Connect to DB
        dbHandle.openCursor()
        insString = "INSERT INTO BGKMASSESGND VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"
        insArgs = tuple(inFGS.tolist()) + tuple(outFGS.tolist())
        dbHandle.execute(insString, insArgs)
        dbHandle.commit()
        dbHandle.closeCursor()

if __name__ == "__main__":
    defaultFName = "testDB.db"
    defaultTag = "DUMMY_TAG_42"
    defaultRank = 0
    defaultID = 0
    defaultProcessing = ALInterfaceMode.FGS
    defaultSolver = SolverCode.BGK
    defaultDBBackend= DatabaseMode.SQLITE
    defaultUName="THISISBAD"
    defaultPassword="THISISrealBAD"

    # No need to preserve global arg parsing logic as we have all we need here

    argParser = argparse.ArgumentParser(description='Python Driver to Convert FGS BGK Result into DB Entry')

    #TODO: Add args for db uname and password
    argParser.add_argument('-t', '--tag', action='store', type=str, required=False, default=defaultTag, help="Tag for DB Entries")
    argParser.add_argument('-r', '--rank', action='store', type=int, required=False, default=defaultRank, help="MPI Rank of Requester")
    argParser.add_argument('-i', '--id', action='store', type=int, required=False, default=defaultID, help="Request ID")
    argParser.add_argument('-d', '--db', action='store', type=str, required=False, default=defaultFName, help="Filename for sqlite DB")
    argParser.add_argument('-m', '--mode', action='store', type=int, required=False, default=defaultProcessing, help="Default Request Type (FGS=0)")
    argParser.add_argument('-c', '--code', action='store', type=int, required=False, default=defaultSolver, help="Code to expect Packets from (BGK=0)")
    argParser.add_argument('-b', '--dbbackend', action='store', type=int, required=False, default=defaultDBBackend, help='Database Backend for Request (SQLUTE=0)')
    argParser.add_argument('-u', '--username', action='store', type=str, required=False, default=defaultUName, help="Default Username for Database")
    argParser.add_argument('-p', '--password', action='store', type=str, required=False, default=defaultPassword, help="Default Ridiculously Insecure Password for Database")

    args = vars(argParser.parse_args())

    tag = args['tag']
    # This is the fine grain DB so we are already good
    globalDBName = args['db']
    rank = args['rank']
    reqid = args['id']
    mode = ALInterfaceMode(args['mode'])
    code = SolverCode(args['code'])
    dbBackend = DatabaseMode(args['dbbackend'])

    dbConfigDict = {}
    dbConfigDict["DatabaseMode"] = dbBackend
    dbConfigDict["DatabaseURL"] = globalDBName
    dbConfigDict["DatabaseUser"] = args['username']
    dbConfigDict['DatabasePassword'] = args['password']

    dbHandle = getDBHandle(dbConfigDict)

    resultArr = procOutputsAndProcess(tag, dbHandle, rank, reqid, mode, code)
    if(mode == ResultProvenance.FGS):
        insertGroundishTruth(dbHandle, resultArr, code)
    dbHandle.closeDB()

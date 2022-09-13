#!/bin/bash
PYTHON_SCRIPT_DIR=${PYTHON_SCRIPT_DIR:=$(dirname $BASH_SOURCE)/../GLUECode_Service}
python3 "${PYTHON_SCRIPT_DIR}/initTables.py" -i "$(dirname "$BASH_SOURCE")/../jsonFiles/fullTest_collectiveICF.json"
python3 "${PYTHON_SCRIPT_DIR}//alInterface.py" -i "$(dirname "$BASH_SOURCE")/../jsonFiles/fullTest_collectiveICF.json" &
mpirun -n 4 $1
if [ $? -eq 0 ]
then
  sleep 2
  #rm ./testDB.db
  exit 0
else
  sleep 2
  #rm ./testDB.db
  echo "Full Collective Test Failed"
  exit 1
fi

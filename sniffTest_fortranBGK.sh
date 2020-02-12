#!/bin/bash
python $(dirname $BASH_SOURCE)/initTables.py --db foo.db -c 0
python $(dirname $BASH_SOURCE)/alInterface.py --db foo.db -t TAG -m 3 -r 0 -c 0 &
$(dirname $BASH_SOURCE)/sniffTest_fortranBGK
if [ $? -eq 0 ]
then
  sleep 2
  rm ./foo.db
  exit 0
else
  sleep 2
  rm ./foo.db
  echo "Fortran Sniff Test Failed"
  exit 1
fi
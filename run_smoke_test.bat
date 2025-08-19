@echo off
REM Quick CAMAC smoke test runner
REM Adjust RESOURCE if your GPIB address changes

set RESOURCE=GPIB0::16::INSTR
set CFG=config\daq.cfg

call venv\Scripts\python.exe tests\smoke_test.py --cfg %CFG% --mode visa --resource "%RESOURCE%" --write-module GATE --write-addr 0 --write-func 16 --write-data 0x1234
pause

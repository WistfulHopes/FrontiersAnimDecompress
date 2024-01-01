@echo off
set "program=FrontiersAnimDecompress.exe"
cd /d "%~dp0"
:process_files
if "%1"=="" goto :eof
start "" "%program%" "%~1"
shift
goto :process_files

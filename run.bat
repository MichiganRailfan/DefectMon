@echo off
cd /d "%~dp0"

::Open SDR Decoder/Recorder
::python sdrdecrec.py

::Open Decoder
start "" python "decoder.py"

::Open GUI
start "" pythonw "gui.pyw"
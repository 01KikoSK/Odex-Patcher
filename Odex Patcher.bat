@echo off
:: ==============================
:: Advanced Odex Patcher Script
:: ==============================
:: Author: 01KikoSK
:: Description: Patches odex files automatically in a specified directory.
:: ==============================

setlocal EnableExtensions EnableDelayedExpansion

:: Define directories
set "inputDir=.\input"
set "outputDir=.\output"
set "backupDir=.\backup"
set "toolsDir=.\tools"

:: Ensure directories exist
if not exist "%inputDir%" mkdir "%inputDir%"
if not exist "%outputDir%" mkdir "%outputDir%"
if not exist "%backupDir%" mkdir "%backupDir%"

:: Check for required tools
if not exist "%toolsDir%\odex_tool.exe" (
    echo [ERROR] Missing required tool: odex_tool.exe
    exit /b 1
)

:: Process odex files
echo [INFO] Starting Odex patching process...
for %%f in (%inputDir%\*.odex) do (
    echo Processing %%~nxf...

    :: Backup original file
    copy "%%~f" "%backupDir%" >nul
    echo [INFO] Backup created: %%~nxf

    :: Patch the odex file using the tool
    "%toolsDir%\odex_tool.exe" patch "%%~f" "%outputDir%\%%~nxf"
    if errorlevel 1 (
        echo [ERROR] Failed to patch: %%~nxf
        echo Skipping...
        next
    ) else (
        echo [INFO] Successfully patched: %%~nxf
    )
)

echo [INFO] Odex patching process completed.
pause
endlocal
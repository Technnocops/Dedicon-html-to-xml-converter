@echo off
setlocal
cd /d "%~dp0"

set "VERSION="
set "EXTRA_ARGS="

if "%~1"=="" goto prompt_version

set "FIRST_ARG=%~1"
if "%FIRST_ARG:~0,1%"=="-" goto collect_extra_args

set "VERSION=%FIRST_ARG%"
shift

:collect_extra_args
if "%~1"=="" goto after_args
set "EXTRA_ARGS=%EXTRA_ARGS% \"%~1\""
shift
goto collect_extra_args

:prompt_version
set /p "VERSION=Enter version to build [example Release-1.0.0]: "

:after_args
if "%VERSION%"=="" (
  echo No version entered. Build cancelled.
  exit /b 1
)

powershell -ExecutionPolicy Bypass -File "%~dp0build_release.ps1" -Version "%VERSION%" %EXTRA_ARGS%

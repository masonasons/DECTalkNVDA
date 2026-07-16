@echo off
rem bootstrap.bat - set up a fresh checkout so it can build.
rem
rem Fetches the proprietary DECtalk engine sources (not committed to this
rem repo). Safe to re-run.
rem
rem   scripts\bootstrap.bat

setlocal
set ROOT=%~dp0..
set UPSTREAM_REPO=https://github.com/dectalk/dectalk.git

if exist "%ROOT%\upstream\src" (
    echo upstream\ already present - skipping clone
) else (
    echo Cloning DECtalk engine into upstream\ ^(shallow^)
    git clone --depth 1 %UPSTREAM_REPO% "%ROOT%\upstream"
    if errorlevel 1 exit /b 1
)

rem Sonic time-stretcher (Apache-2.0, redistributable) - bundled for rate
rem boost on NVDA versions without a built-in sonic.dll.
if exist "%ROOT%\third_party\sonic\sonic.c" (
    echo third_party\sonic already present - skipping clone
) else (
    echo Cloning Sonic into third_party\sonic ^(shallow^)
    git clone --depth 1 https://github.com/waywardgeek/sonic.git "%ROOT%\third_party\sonic"
    if errorlevel 1 exit /b 1
)

echo Done. Next:
echo   scripts\build.bat          - build DECtalk.dll (x64 + x86) + dictionary
echo   python scripts\package.py  - build the .nvda-addon
exit /b 0

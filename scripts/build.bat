@echo off
rem build.bat - build the DECtalk engine DLL + dictionary for the NVDA add-on.
rem
rem Uses the upstream VS2022 projects: builds "DECtalk API" (DECtalk.dll) and
rem "Internal Dictionary Compiler" (whose post-build step compiles
rem dtalk_us.dic) for x64 and x86, then copies the artifacts into
rem addon\synthDrivers\dectalknew\.
rem
rem   scripts\build.bat           - build both architectures
rem   scripts\build.bat x64       - build only x64

setlocal enabledelayedexpansion
set ROOT=%~dp0..
set SRC=%ROOT%\upstream\src
set CONFIG=Release - ENGLISH_US
set DEST=%ROOT%\addon\synthDrivers\dectalknew

if not exist "%SRC%\DECtalk.sln" (
    echo Engine sources not found. Run scripts\bootstrap.bat first.
    exit /b 1
)

rem Locate MSBuild and vcvarsall via vswhere.
set VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe
set MSBUILD=
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.Component.MSBuild -find MSBuild\**\Bin\MSBuild.exe`) do set MSBUILD=%%i
if not defined MSBUILD (
    echo MSBuild not found. Install Visual Studio 2022 Build Tools with the C++ workload.
    exit /b 1
)
echo MSBuild: %MSBUILD%
set VCVARSALL=
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find VC\Auxiliary\Build\vcvarsall.bat`) do set VCVARSALL=%%i
if not defined VCVARSALL (
    echo vcvarsall.bat not found. Install the VS2022 C++ workload.
    exit /b 1
)

set PLATFORMS=x64 Win32
if not "%~1"=="" set PLATFORMS=%~1

for %%p in (%PLATFORMS%) do (
    echo === Building "%CONFIG%" ^| %%p ===
    "%MSBUILD%" "%SRC%\dapi\src\DECtalk API.vcxproj" /m /v:minimal /nologo /p:Configuration="%CONFIG%" /p:Platform=%%p /p:SolutionDir="%SRC%\\"
    if errorlevel 1 exit /b 1
    "%MSBUILD%" "%SRC%\dapi\src\Internal Dictionary Compiler.vcxproj" /m /v:minimal /nologo /p:Configuration="%CONFIG%" /p:Platform=%%p /p:SolutionDir="%SRC%\\"
    if errorlevel 1 exit /b 1

    rem Project platform -> add-on lib dir (x64 -> x64, Win32 -> x86)
    set LIBDIR=x64
    if "%%p"=="Win32" set LIBDIR=x86
    if not exist "%DEST%\lib\!LIBDIR!" mkdir "%DEST%\lib\!LIBDIR!"
    copy /y "%SRC%\dapi\build\dectalk\%%p\%CONFIG%\DECtalk.dll" "%DEST%\lib\!LIBDIR!\DECtalk.dll" >nul
    if errorlevel 1 exit /b 1
    echo   DECtalk.dll -^> lib\!LIBDIR!\

    rem The dictionary format is architecture-independent; either build's copy works.
    copy /y "%SRC%\dapi\build\dic\%%p\%CONFIG%\dtalk_us.dic" "%DEST%\dtalk_us.dic" >nul
    if errorlevel 1 exit /b 1
    echo   dtalk_us.dic -^> synthDrivers\dectalknew\

    rem Bundled Sonic time-stretcher (Apache-2.0; rate boost on NVDA versions
    rem without a built-in sonic.dll). vcvarsall arch: x64 or x64_x86.
    set VCARCH=x64
    if "%%p"=="Win32" set VCARCH=x64_x86
    if exist "%ROOT%\third_party\sonic\sonic.c" (
        if not exist "%ROOT%\build\sonic_%%p" mkdir "%ROOT%\build\sonic_%%p"
        rem Delayed expansion: the path contains "(x86)", whose ")" would
        rem break this parenthesized block if expanded at parse time.
        cmd /c ""!VCVARSALL!" !VCARCH! >nul && cl /nologo /O2 /LD "%ROOT%\third_party\sonic\sonic.c" /Fo"%ROOT%\build\sonic_%%p\\" /Fe"%DEST%\lib\!LIBDIR!\sonic.dll" /link /DEF:"%ROOT%\scripts\sonic.def" /IMPLIB:"%ROOT%\build\sonic_%%p\sonic.lib"" >nul
        if errorlevel 1 exit /b 1
        echo   sonic.dll -^> lib\!LIBDIR!\
        copy /y "%ROOT%\third_party\sonic\LICENSE" "%DEST%\lib\SONIC-LICENSE.txt" >nul
    ) else (
        echo   third_party\sonic missing - run scripts\bootstrap.bat; skipping sonic.dll
    )
)

echo Done.
exit /b 0

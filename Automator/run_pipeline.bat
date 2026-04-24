@echo off
cd /d "%~dp0"
set PYTHON=C:\Users\virat.arya\AppData\Local\anaconda3\python.exe
set CODE=C:\Users\virat.arya\ETG\SoftsDatabase - Documents\Database\Hardmine\Fundamental\TDM\Cotton Flow New\Code
set DB=C:\Users\virat.arya\ETG\SoftsDatabase - Documents\Database\Hardmine\Fundamental\TDM\Cotton Flow New\Database
set LOG=%~dp0run_log.txt
set EMAIL=virat.arya@etgworld.com
set FAILED=0
set ROWS_EXP_NEW=0
set ROWS_IMP_NEW=0

echo. >> "%LOG%"
echo ============================================================ >> "%LOG%"
echo Cotton TDM Pipeline  --  %DATE% %TIME% >> "%LOG%"
echo ============================================================ >> "%LOG%"

:: ── Row counts before ────────────────────────────────────────────────────────
for /f %%i in ('%PYTHON% -c "import pandas as pd; df=pd.read_parquet(r\"%DB%\tdm_cotton_exports.parquet\"); print(len(df))" 2^>nul') do set ROWS_EXP_BEFORE=%%i
for /f %%i in ('%PYTHON% -c "import pandas as pd; df=pd.read_parquet(r\"%DB%\tdm_cotton_imports.parquet\"); print(len(df))" 2^>nul') do set ROWS_IMP_BEFORE=%%i
if not defined ROWS_EXP_BEFORE set ROWS_EXP_BEFORE=0
if not defined ROWS_IMP_BEFORE set ROWS_IMP_BEFORE=0

echo Rows before  --  Exports: %ROWS_EXP_BEFORE%  Imports: %ROWS_IMP_BEFORE% >> "%LOG%"

:: ── Run ingests ───────────────────────────────────────────────────────────────
"%PYTHON%" "%CODE%\cotton_exports_ingest.py" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] cotton_exports_ingest.py failed >> "%LOG%"
    set FAILED=1
    goto :git_push
)

"%PYTHON%" "%CODE%\cotton_imports_ingest.py" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] cotton_imports_ingest.py failed >> "%LOG%"
    set FAILED=1
    goto :git_push
)

:: ── Row counts after ─────────────────────────────────────────────────────────
for /f %%i in ('%PYTHON% -c "import pandas as pd; df=pd.read_parquet(r\"%DB%\tdm_cotton_exports.parquet\"); print(len(df))"') do set ROWS_EXP_AFTER=%%i
for /f %%i in ('%PYTHON% -c "import pandas as pd; df=pd.read_parquet(r\"%DB%\tdm_cotton_imports.parquet\"); print(len(df))"') do set ROWS_IMP_AFTER=%%i

set /a ROWS_EXP_NEW=%ROWS_EXP_AFTER%-%ROWS_EXP_BEFORE%
set /a ROWS_IMP_NEW=%ROWS_IMP_AFTER%-%ROWS_IMP_BEFORE%

echo Rows after   --  Exports: %ROWS_EXP_AFTER%  Imports: %ROWS_IMP_AFTER% >> "%LOG%"
echo New rows     --  Exports: +%ROWS_EXP_NEW%   Imports: +%ROWS_IMP_NEW% >> "%LOG%"

:: ── Git push ──────────────────────────────────────────────────────────────────
:git_push
echo Pushing to GitHub... >> "%LOG%"
cd /d "%CODE%\.."
git add Database\tdm_cotton_exports.parquet Database\tdm_cotton_imports.parquet >> "%LOG%" 2>&1
git commit -m "auto: update cotton parquets %DATE% %TIME%" >> "%LOG%" 2>&1
git push >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] git push failed >> "%LOG%"
) else (
    echo [OK] git push succeeded >> "%LOG%"
)

echo All done -- %DATE% %TIME% >> "%LOG%"
echo ============================================================ >> "%LOG%"

:: ── Send email ────────────────────────────────────────────────────────────────
if %FAILED%==0 (
    powershell -NoProfile -Command "$o = New-Object -ComObject Outlook.Application; $m = $o.CreateItem(0); $m.To = '%EMAIL%'; $m.Subject = 'Cotton TDM Pipeline - OK [%DATE%]'; $m.Body = 'Cotton TDM pipeline completed successfully on %DATE% at %TIME%.`n`nNew rows added:`n  Exports : +%ROWS_EXP_NEW% (total %ROWS_EXP_AFTER%)`n  Imports : +%ROWS_IMP_NEW% (total %ROWS_IMP_AFTER%)'; $m.Send()"
) else (
    powershell -NoProfile -Command "$o = New-Object -ComObject Outlook.Application; $m = $o.CreateItem(0); $m.To = '%EMAIL%'; $m.Subject = 'Cotton TDM Pipeline - FAILED [%DATE%]'; $m.Body = 'Cotton TDM pipeline FAILED on %DATE% at %TIME%.`nCheck log: %LOG%'; $m.Send()"
)

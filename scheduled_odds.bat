@echo off
rem Run by the Windows task "FIBA Europe Cup odds" (every hour 10:00-21:00): python matchday_odds.py, output in data\odds.log
cd /d "C:\Users\antonis\Desktop\eurocup"
rem Playwright's browsers outside AppData, so Task Scheduler can see them (as for the EuroCup task)
set "PLAYWRIGHT_BROWSERS_PATH=C:\Users\antonis\playwright-browsers"
echo. >> data\odds.log
echo ===== %date% %time% ===== >> data\odds.log
"C:\Users\antonis\AppData\Local\Programs\Python\Python314\python.exe" -u matchday_odds.py >> data\odds.log 2>&1
set rc=%errorlevel%
echo exit code %rc% >> data\odds.log
exit /b %rc%

@echo off
title Narrative Intelligence
echo.
echo    ================================================
echo      NARRATIVE INTELLIGENCE  -  AAP Punjab
echo.
echo      App start ho raha hai... 5-10 second ruko.
echo      Window khud khul jayegi (login nahi chahiye).
echo.
echo      ( Is chhoti window ko band MAT karo --
echo        app isi se chalti hai. App band karna ho to
echo        bas app-window ka X dabao. )
echo    ================================================
echo.
cd /d "%~dp0"
"C:\Python314\python.exe" "%~dp0desktop_app.py"
echo.
echo App band ho gaya.
timeout /t 3 >nul

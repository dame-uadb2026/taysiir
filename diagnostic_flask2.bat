@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================================
echo   Diagnostic 2 - Test des bibliotheques une par une
echo ================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERREUR] Le dossier venv n'existe pas ici.
    pause
    exit /b 1
)

(
echo import sys
echo print^("Python :", sys.version^)
echo.
echo print^("1/5 - import flask ..."^)
echo from flask import Flask
echo print^("    OK"^)
echo.
echo print^("2/5 - import flask_sqlalchemy ..."^)
echo from flask_sqlalchemy import SQLAlchemy
echo print^("    OK"^)
echo.
echo print^("3/5 - import flask_login ..."^)
echo from flask_login import LoginManager
echo print^("    OK"^)
echo.
echo print^("4/5 - import flask_wtf ..."^)
echo from flask_wtf import CSRFProtect
echo print^("    OK"^)
echo.
echo print^("5/5 - import werkzeug.security ..."^)
echo from werkzeug.security import generate_password_hash
echo print^("    OK"^)
echo.
echo print^(""^)
echo print^("TOUT EST OK"^)
) > diagnostic_test2.py

echo Lancement du test detaille...
echo.
echo ------------------------------------------------
set PYTHONFAULTHANDLER=1
set PYTHONUNBUFFERED=1
"venv\Scripts\python.exe" diagnostic_test2.py
echo ------------------------------------------------
echo.
echo Fin du test. Code de sortie : %errorlevel%
echo.
pause

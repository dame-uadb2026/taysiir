@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================================
echo   Diagnostic Flask
echo ================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERREUR] Le dossier venv n'existe pas ici.
    echo Lance d'abord reparer_et_lancer.bat une fois.
    pause
    exit /b 1
)

echo Creation d'une mini-application de test...
(
echo from flask import Flask
echo app = Flask^(__name__^)
echo.
echo @app.route^("/"^)
echo def index^(^):
echo     return "OK - Flask fonctionne"
echo.
echo if __name__ == "__main__":
echo     print^("DEBUT DU TEST"^)
echo     app.run^(host="127.0.0.1", port=5050^)
) > diagnostic_test.py

echo.
echo Lancement du test (CTRL+C pour arreter une fois que tu vois un message)...
echo Si ca marche, ouvre http://127.0.0.1:5050 dans ton navigateur.
echo.
echo ------------------------------------------------
set PYTHONFAULTHANDLER=1
set PYTHONUNBUFFERED=1
"venv\Scripts\python.exe" diagnostic_test.py
echo ------------------------------------------------
echo.
echo Fin du test. Code de sortie : %errorlevel%
echo.
pause

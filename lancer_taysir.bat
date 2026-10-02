@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================================
echo   Taysir Al-Asir - AERTM
echo   Installation et lancement local
echo ================================================
echo.

REM --- 1. Verifier que Python est installe ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH.
    echo Va sur https://www.python.org/downloads/ et installe Python.
    echo IMPORTANT : coche la case "Add Python to PATH" pendant l'installation.
    echo.
    pause
    exit /b 1
)
echo [OK] Python detecte :
python --version
echo.

REM --- 2. Creer l'environnement virtuel s'il n'existe pas ---
if not exist "venv\Scripts\python.exe" (
    echo [1/4] Creation de l'environnement virtuel...
    python -m venv venv
    if errorlevel 1 (
        echo [ERREUR] La creation de l'environnement virtuel a echoue.
        pause
        exit /b 1
    )
    echo [OK] Environnement virtuel cree.
) else (
    echo [1/4] Environnement virtuel deja present.
)
echo.

REM --- 3. Installer les dependances avec le python du venv directement ---
REM (plus fiable que "call activate.bat" sur certaines installations Windows)
set PYVENV=venv\Scripts\python.exe
set PIPVENV=venv\Scripts\pip.exe

echo [2/4] Installation des dependances (peut prendre une minute)...
"%PYVENV%" -m pip install --upgrade pip >nul 2>nul
"%PIPVENV%" install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERREUR] L'installation des dependances a echoue.
    echo Verifie ta connexion internet, puis relance ce script.
    pause
    exit /b 1
)
echo [OK] Dependances installees.
echo.

REM --- 4. Preparer le dossier instance (pour SQLite en local) ---
if not exist "instance" mkdir "instance"

REM --- 5. Choisir un port libre (5000 par defaut, sinon 5001) ---
set FLASK_PORT=5000
netstat -ano | findstr ":5000" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Le port 5000 est deja utilise par un autre programme.
    echo [INFO] Utilisation du port 5001 a la place.
    set FLASK_PORT=5001
)

set FLASK_APP=app:create_app

echo [3/4] Configuration terminee.
echo.
echo [4/4] Lancement de l'application...
echo.
echo   Identifiants par defaut (a changer apres connexion, menu "Mon compte") :
echo     Numero WhatsApp : +221700000000
echo     Mot de passe    : aertm2026
echo.
echo   Ouvre ton navigateur a l'adresse : http://127.0.0.1:!FLASK_PORT!
echo   (CTRL+C dans cette fenetre pour arreter le serveur)
echo.
echo ------------------------------------------------
"%PYVENV%" -m flask run --port !FLASK_PORT!
echo ------------------------------------------------
echo.
echo Le serveur s'est arrete (ou n'a pas pu demarrer).
echo Si aucune erreur n'est visible ci-dessus, relis les 3 dernieres lignes
echo affichees juste au-dessus de ce message : c'est la le vrai motif.
echo.
pause

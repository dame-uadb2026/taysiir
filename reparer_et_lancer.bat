@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================================
echo   Taysir Al-Asir - AERTM
echo   Reparation complete + lancement
echo ================================================
echo.

REM --- 1. Chercher une version de Python stable et compatible ---
echo [1/6] Recherche d'une version de Python compatible (3.10 a 3.13)...
set "PYCMD="

where py >nul 2>nul
if not errorlevel 1 (
    for %%V in (3.12 3.11 3.13 3.10) do (
        if not defined PYCMD (
            py -%%V --version >nul 2>nul
            if not errorlevel 1 (
                set "PYCMD=py -%%V"
                echo [OK] Python %%V trouve, on l'utilise.
            )
        )
    )
)

if not defined PYCMD (
    echo [ATTENTION] Aucune version 3.10 a 3.13 trouvee via le lanceur "py".
    echo On va essayer avec la commande "python" par defaut.
    python --version >nul 2>nul
    if errorlevel 1 (
        echo.
        echo [ERREUR] Python n'est pas installe ou pas accessible.
        echo Va sur https://www.python.org/downloads/release/python-3120/
        echo installe Python 3.12 en cochant "Add python.exe to PATH", puis relance ce script.
        pause
        exit /b 1
    )
    set "PYCMD=python"
    echo [ATTENTION] Si le lancement echoue encore, installe Python 3.12 :
    echo https://www.python.org/downloads/release/python-3120/
)
echo.

REM --- 2. Supprimer l'ancien environnement virtuel (source de bugs si copie/deplace) ---
echo [2/6] Nettoyage de l'ancien environnement virtuel...
if exist "venv" (
    rmdir /s /q "venv"
    echo [OK] Ancien venv supprime.
) else (
    echo [OK] Rien a nettoyer.
)
echo.

REM --- 3. Creer un venv tout neuf ---
echo [3/6] Creation d'un nouvel environnement virtuel...
%PYCMD% -m venv venv
if errorlevel 1 (
    echo [ERREUR] La creation du venv a echoue.
    pause
    exit /b 1
)
echo [OK] Environnement virtuel cree.
echo.

set "PYVENV=venv\Scripts\python.exe"
set "PIPVENV=venv\Scripts\pip.exe"

REM --- 4. Installer les dependances ---
echo [4/6] Installation des dependances...
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

REM --- 5. Preparer le dossier instance et choisir un port libre ---
if not exist "instance" mkdir "instance"

set FLASK_PORT=5000
netstat -ano | findstr ":5000" | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Le port 5000 est deja utilise, passage au port 5001.
    set FLASK_PORT=5001
)

set FLASK_APP=app:create_app

echo [5/6] Configuration terminee.
echo.
echo [6/6] Lancement de l'application...
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
echo Si aucun message "Running on http://..." n'est apparu ci-dessus,
echo copie-colle tout le texte affiche entre les deux lignes de tirets
echo et envoie-le pour diagnostic.
echo.
pause

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _normalize_db_url(url: str) -> str:
    # Render / Heroku fournissent souvent "postgres://", SQLAlchemy 1.4+
    # exige "postgresql://".
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-moi-en-production")
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.environ.get(
            "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'taysir.db')}"
        )
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Création automatique du premier compte gérant au démarrage (utile sur
    # Render en gratuit, où il n'y a pas d'accès shell). Des valeurs par
    # défaut sont fournies pour que l'application soit utilisable dès le
    # déploiement ; CHANGE LE MOT DE PASSE après ta première connexion
    # (menu "Mon compte"), ou définis tes propres variables d'environnement
    # SEED_MANAGER_* sur Render pour les remplacer avant le premier déploiement.
    SEED_MANAGER_PRENOM = os.environ.get("SEED_MANAGER_PRENOM", "Admin")
    SEED_MANAGER_NOM = os.environ.get("SEED_MANAGER_NOM", "AERTM")
    SEED_MANAGER_WHATSAPP = os.environ.get("SEED_MANAGER_WHATSAPP", "+221700000000")
    SEED_MANAGER_PASSWORD = os.environ.get("SEED_MANAGER_PASSWORD", "aertm2026")

    # Nombre total de أجزاء dans le Coran, pour cette application : 30
    # (un جزء par membre, jamais deux).
    TOTAL_HIZB = 30

    # Nom de l'application
    APP_NAME = "تيسير العسير"
    ORG_NAME = "AERTM — Amicale des Étudiants Ressortissants de Touba Mbacké"

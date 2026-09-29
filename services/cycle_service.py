from __future__ import annotations

from datetime import datetime, timedelta

from database import db
from models import ActivityLog, Assignment, Cycle, Member, Settings


def get_settings() -> Settings:
    """Retourne la ligne unique de parametres, la cree si absente."""
    settings = Settings.query.first()
    if not settings:
        settings = Settings()
        db.session.add(settings)
        db.session.commit()
    elif settings.reminder_template and "Tu as les Hizb {hizb}" in settings.reminder_template:
        # Migration douce : anciennes installations qui avaient le modele
        # par defaut avant le passage a la terminologie جزء.
        settings.reminder_template = settings.reminder_template.replace(
            "Tu as les Hizb {hizb}.", "Tu as le {hizb}."
        )
        db.session.commit()
    return settings


def log_action(acteur_id, action, details=None):
    entry = ActivityLog(acteur_id=acteur_id, action=action, details=details)
    db.session.add(entry)


def get_active_cycle() -> Cycle | None:
    """Retourne le cycle en cours (le plus récent avec le statut 'actif')."""
    return (
        Cycle.query.filter_by(statut="actif")
        .order_by(Cycle.date_creation.desc())
        .first()
    )


def create_cycle(date_debut, date_fin, createur_id, total_hizb=30, notes=None):
    """
    Crée un nouveau cycle hebdomadaire.

    IMPORTANT : aucune attribution de جزء n'est faite automatiquement, quel
    que soit le nombre de membres actifs. Chaque membre commence le cycle
    avec "Aucun جزء attribué" ; c'est au responsable de décider, un par un,
    via "+ Attribuer un جزء", qui reçoit quel جزء. Ceci est une règle
    fondamentale de l'application : jamais d'attribution imposée par l'ordre
    d'ajout des membres ou par le système.

    - Ne supprime jamais les cycles précédents.
    """
    cycle = Cycle(date_debut=date_debut, date_fin=date_fin, createur_id=createur_id,
                  notes=notes, statut="actif")
    db.session.add(cycle)
    db.session.flush()  # pour obtenir cycle.id

    nb_membres_actifs = Member.query.filter_by(actif=True, role="member").count()

    log_action(createur_id, "creation_cycle",
               f"Cycle #{cycle.id} créé ({date_debut:%d/%m/%Y} → {date_fin:%d/%m/%Y}), "
               f"{nb_membres_actifs} membres actifs, aucune attribution automatique.")
    db.session.commit()
    return cycle


def validate_cycle_coverage(cycle: Cycle, total_hizb=30):
    """
    Vérifie que tous les أجزاء de 1 à total_hizb sont couverts au maximum
    une fois (la double-attribution est déjà bloquée à la source, ceci est
    une vérification de sécurité supplémentaire).
    Retourne une liste de messages d'erreur (vide si tout est correct).
    """
    erreurs = []
    couverture = {}
    for a in cycle.assignments:
        for h in range(a.hizb_debut, a.hizb_fin + 1):
            couverture.setdefault(h, []).append(a.member_id)

    for h in range(1, total_hizb + 1):
        proprietaires = couverture.get(h, [])
        if len(proprietaires) > 1:
            erreurs.append(f"⚠️ Le جزء {h} est attribué à plusieurs membres.")

    return erreurs


def close_cycle(cycle: Cycle, acteur_id):
    cycle.statut = "termine"
    log_action(acteur_id, "cloture_cycle", f"Cycle #{cycle.id} clôturé.")
    db.session.commit()


def get_or_create_current_cycle(acteur_id=None, total_hizb=30):
    """
    Retourne le cycle actif courant. Si le cycle actif est termine dans le
    temps (date_fin depassee) et que la recurrence automatique est activee
    (Settings.cycle_auto), cloture l'ancien cycle et en cree un nouveau
    automatiquement selon le calendrier jour_debut -> jour_debut+6
    (par defaut Vendredi -> Jeudi), sans jamais supprimer les donnees
    precedentes. Si la recurrence est desactivee, se comporte comme
    get_active_cycle() (creation manuelle par le gerant uniquement).
    """
    settings = get_settings()
    now = datetime.utcnow()
    active = get_active_cycle()

    if active and now <= active.date_fin:
        return active

    if not settings.cycle_auto:
        return active  # peut etre None ou un cycle expire non clos : le gerant gere manuellement

    if active and now > active.date_fin:
        close_cycle(active, acteur_id)

    jour_debut = settings.jour_debut  # 0=lundi ... 4=vendredi
    if active:
        # Semaine suivante immediate, pour ne jamais laisser de trou dans l'historique
        start = (active.date_fin + timedelta(seconds=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        jours_avant = (jour_debut - now.weekday()) % 7
        start = (now + timedelta(days=jours_avant)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    end = (start + timedelta(days=6)).replace(hour=23, minute=59, second=59)

    return create_cycle(start, end, acteur_id, total_hizb=total_hizb)

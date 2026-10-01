from __future__ import annotations

from datetime import datetime, timedelta

from database import db
from models import ActivityLog, Assignment, Confirmation, Cycle, Member, Reminder, StatusSignal


def log_action(acteur_id, action, details=None):
    entry = ActivityLog(acteur_id=acteur_id, action=action, details=details)
    db.session.add(entry)


def get_active_cycle(organization_id) -> Cycle | None:
    """Retourne le cycle en cours de cette amicale (le plus récent 'actif')."""
    return (
        Cycle.query.filter_by(statut="actif", organization_id=organization_id)
        .order_by(Cycle.date_creation.desc())
        .first()
    )


def create_cycle(organization_id, date_debut, date_fin, createur_id, notes=None):
    """
    Crée un nouveau cycle hebdomadaire pour cette amicale.

    IMPORTANT : aucune attribution de جزء n'est faite automatiquement, quel
    que soit le nombre de membres actifs. Chaque membre commence le cycle
    avec "Aucun جزء attribué" ; c'est au responsable de décider, un par un,
    via "+ Attribuer un جزء", qui reçoit quel جزء.

    - Ne supprime jamais les cycles précédents.
    """
    cycle = Cycle(organization_id=organization_id, date_debut=date_debut, date_fin=date_fin,
                  createur_id=createur_id, notes=notes, statut="actif")
    db.session.add(cycle)
    db.session.flush()  # pour obtenir cycle.id

    nb_membres_actifs = Member.query.filter_by(
        actif=True, role="member", organization_id=organization_id
    ).count()

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


def get_or_create_current_cycle(organization, acteur_id=None):
    """
    Retourne le cycle actif courant de cette amicale. Si le cycle actif est
    terminé dans le temps (date_fin dépassée) et que la récurrence
    automatique est activée pour cette amicale (organization.cycle_auto),
    clôture l'ancien cycle et en crée un nouveau automatiquement selon son
    propre calendrier (organization.jour_debut), sans jamais supprimer les
    données précédentes. Si la récurrence est désactivée, se comporte comme
    get_active_cycle() (création manuelle par le responsable uniquement).
    """
    now = datetime.utcnow()
    active = get_active_cycle(organization.id)

    if active and now <= active.date_fin:
        return active

    if not organization.cycle_auto:
        return active  # peut etre None ou un cycle expire non clos : le gerant gere manuellement

    if active and now > active.date_fin:
        close_cycle(active, acteur_id)

    jour_debut = organization.jour_debut  # 0=lundi ... 4=vendredi
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

    return create_cycle(organization.id, start, end, acteur_id)


def create_next_cycle_same_group(organization, cycle_actuel: Cycle, acteur_id) -> Cycle:
    """
    Crée le cycle suivant pour cette amicale en conservant le même groupe :
    chaque membre encore actif qui avait un جزء dans cycle_actuel reçoit par
    défaut le même جزء dans le nouveau cycle. Les membres devenus inactifs
    entre-temps ne sont pas reconduits (leur جزء redevient simplement
    disponible). Le nombre de membres est toujours recalculé dynamiquement.

    Les confirmations, retards et rappels repartent à zéro (nouveau cycle_id).
    Clôture cycle_actuel s'il est encore actif, sans jamais le supprimer.
    """
    if cycle_actuel.statut == "actif":
        close_cycle(cycle_actuel, acteur_id)

    duree_jours = (cycle_actuel.date_fin.date() - cycle_actuel.date_debut.date()).days
    debut = (cycle_actuel.date_fin + timedelta(seconds=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if organization.cycle_auto:
        jours_avant = (organization.jour_debut - debut.weekday()) % 7
        debut = debut + timedelta(days=jours_avant)
    fin = (debut + timedelta(days=duree_jours)).replace(hour=23, minute=59, second=59)

    nouveau_cycle = Cycle(organization_id=organization.id, date_debut=debut, date_fin=fin,
                           createur_id=acteur_id, statut="actif")
    db.session.add(nouveau_cycle)
    db.session.flush()

    membres_actifs_ids = {
        m.id for m in Member.query.filter_by(
            actif=True, role="member", organization_id=organization.id
        ).all()
    }
    nb_reconduits = 0
    for a in Assignment.query.filter_by(cycle_id=cycle_actuel.id).all():
        if a.member_id in membres_actifs_ids:
            db.session.add(Assignment(
                cycle_id=nouveau_cycle.id, member_id=a.member_id,
                hizb_debut=a.hizb_debut, hizb_fin=a.hizb_fin,
            ))
            nb_reconduits += 1

    log_action(
        acteur_id, "nouveau_cycle_meme_groupe",
        f"Cycle #{nouveau_cycle.id} créé à la suite du #{cycle_actuel.id} avec le même "
        f"groupe ({nb_reconduits} جزء reconduit(s) pour les membres encore actifs)."
    )
    db.session.commit()
    return nouveau_cycle


def est_cycle_complet(cycle: Cycle) -> bool:
    """
    Vrai si tous les membres actifs (de l'amicale du cycle) ayant un جزء
    attribué dans ce cycle ont confirmé leur lecture. Un cycle sans aucune
    attribution n'est jamais considéré comme complet.
    """
    assignments = Assignment.query.filter_by(cycle_id=cycle.id).all()
    if not assignments:
        return False

    membres_actifs_ids = {
        m.id for m in Member.query.filter_by(
            actif=True, role="member", organization_id=cycle.organization_id
        ).all()
    }
    assignments_actifs = [a for a in assignments if a.member_id in membres_actifs_ids]
    if not assignments_actifs:
        return False

    confirmes_ids = {
        c.member_id for c in Confirmation.query.filter_by(cycle_id=cycle.id).all()
    }
    return all(a.member_id in confirmes_ids for a in assignments_actifs)


def verifier_et_reconduire_si_complet(organization, cycle: Cycle, acteur_id):
    """
    A appeler juste apres l'enregistrement d'une confirmation. Si tous les
    membres actifs du cycle ont desormais termine, cree automatiquement le
    cycle suivant avec le meme groupe. Retourne le nouveau cycle si la
    reconduction a eu lieu, sinon None.
    """
    if cycle and cycle.statut == "actif" and est_cycle_complet(cycle):
        return create_next_cycle_same_group(organization, cycle, acteur_id)
    return None


def delete_cycle(cycle: Cycle, acteur_id):
    """Supprime définitivement un cycle réel et toutes les données qui lui
    sont rattachées (attributions, confirmations, rappels, signalements).
    Action irréversible, à utiliser uniquement après confirmation côté
    interface."""
    description = f"Cycle #{cycle.id} ({cycle.date_debut:%d/%m/%Y} → {cycle.date_fin:%d/%m/%Y})"
    Confirmation.query.filter_by(cycle_id=cycle.id).delete()
    StatusSignal.query.filter_by(cycle_id=cycle.id).delete()
    Reminder.query.filter_by(cycle_id=cycle.id).delete()
    Assignment.query.filter_by(cycle_id=cycle.id).delete()
    db.session.delete(cycle)
    log_action(acteur_id, "suppression_cycle", f"{description} supprimé définitivement.")
    db.session.commit()

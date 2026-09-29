from datetime import datetime

from models import Assignment, Confirmation, Cycle, Member, Reminder, StatusSignal


def get_members_without_assignment(cycle: Cycle):
    """Membres actifs qui n'ont pas encore de Hizb attribués pour ce cycle
    (ex: ajoutés après la création de la semaine)."""
    if not cycle:
        return []
    membres_avec_assignment = {
        a.member_id for a in Assignment.query.filter_by(cycle_id=cycle.id).all()
    }
    return (
        Member.query.filter_by(actif=True, role="member")
        .filter(~Member.id.in_(membres_avec_assignment))
        .order_by(Member.nom)
        .all()
    )


def get_cycle_progress(cycle: Cycle, total_hizb=30):
    """Calcule la progression réelle d'un cycle à partir de la base de données."""
    assignments = Assignment.query.filter_by(cycle_id=cycle.id).all()
    total_membres = len(assignments)

    confirmations = Confirmation.query.filter_by(cycle_id=cycle.id).all()
    membres_confirmes_ids = {c.member_id for c in confirmations}

    signaux = StatusSignal.query.filter_by(cycle_id=cycle.id).all()
    membres_signales_ids = {s.member_id: s for s in signaux}

    hizb_confirmes = 0
    for a in assignments:
        if a.member_id in membres_confirmes_ids:
            hizb_confirmes += a.nb_hizb

    en_retard = []
    en_attente = []
    pas_encore_termine = []
    maintenant = datetime.utcnow()
    for a in assignments:
        if a.member_id in membres_confirmes_ids:
            continue
        if maintenant > cycle.date_fin:
            en_retard.append(a)
        elif a.member_id in membres_signales_ids:
            pas_encore_termine.append(a)
        else:
            en_attente.append(a)

    pourcentage_membres = round(
        (len(membres_confirmes_ids) / total_membres) * 100
    ) if total_membres else 0

    return {
        "total_membres": total_membres,
        "membres_confirmes": len(membres_confirmes_ids),
        "pourcentage_membres": pourcentage_membres,
        "hizb_confirmes": hizb_confirmes,
        "total_hizb": total_hizb,
        "en_attente": en_attente,
        "en_retard": en_retard,
        "pas_encore_termine": pas_encore_termine,
        "nb_en_attente": len(en_attente),
        "nb_en_retard": len(en_retard),
        "nb_pas_encore_termine": len(pas_encore_termine),
        "signaux": membres_signales_ids,
    }


def get_member_status(cycle: Cycle, member: Member):
    """Statut d'un membre pour un cycle :
    termine | termine_apres_rappel | pas_encore_termine | retard | attente."""
    confirmation = Confirmation.query.filter_by(
        cycle_id=cycle.id, member_id=member.id
    ).first()

    if confirmation:
        return "termine_apres_rappel" if confirmation.apres_rappel else "termine"

    if datetime.utcnow() > cycle.date_fin:
        return "retard"

    signal = StatusSignal.query.filter_by(cycle_id=cycle.id, member_id=member.id).first()
    if signal:
        return "pas_encore_termine"

    return "attente"


def get_attention_list(cycle: Cycle):
    """Regroupe toutes les personnes necessitant une relance (attente, pas
    encore termine, en retard) avec les infos utiles pour agir vite."""
    progress = get_cycle_progress(cycle)
    concernes = progress["en_retard"] + progress["pas_encore_termine"] + progress["en_attente"]

    resultat = []
    for a in concernes:
        if a in progress["en_retard"]:
            statut = "retard"
        elif a in progress["pas_encore_termine"]:
            statut = "pas_encore_termine"
        else:
            statut = "attente"

        signal = progress["signaux"].get(a.member_id)
        dernier_rappel = (
            Reminder.query.filter_by(cycle_id=cycle.id, member_id=a.member_id)
            .order_by(Reminder.date_envoi.desc())
            .first()
        )

        resultat.append({
            "assignment": a,
            "membre": a.member,
            "statut": statut,
            "date_signal": signal.date_signal if signal else None,
            "dernier_rappel": dernier_rappel,
        })

    ordre = {"retard": 0, "pas_encore_termine": 1, "attente": 2}
    resultat.sort(key=lambda x: ordre[x["statut"]])
    return resultat


def get_dashboard_actions(cycle: Cycle):
    """Génère les actions recommandées pour le gérant à partir des vraies données."""
    progress = get_cycle_progress(cycle)
    actions = []

    if progress["nb_en_retard"] > 0:
        actions.append({
            "type": "retard",
            "message": f"🔴 {progress['nb_en_retard']} membre(s) en retard.",
            "cta": "Voir les retardataires",
        })

    if progress["nb_en_attente"] > 0:
        actions.append({
            "type": "attente",
            "message": f"🟠 {progress['nb_en_attente']} membre(s) n'ont pas encore confirmé.",
            "cta": "Relancer",
        })

    if progress["nb_pas_encore_termine"] > 0:
        actions.append({
            "type": "pas_encore_termine",
            "message": f"🟡 {progress['nb_pas_encore_termine']} membre(s) ont signalé ne pas avoir terminé.",
            "cta": "Relancer",
        })

    jours_restants = (cycle.date_fin - datetime.utcnow()).days
    if 0 <= jours_restants <= 1 and progress["nb_en_attente"] + progress["nb_en_retard"] > 0:
        actions.append({
            "type": "echeance",
            "message": "⏳ La semaine se termine bientôt.",
            "cta": "Vérifier les confirmations",
        })

    return actions


def get_history_stats(cycle: Cycle, total_hizb=30):
    """Statistiques d'un cycle clôturé, pour la page Historique."""
    progress = get_cycle_progress(cycle, total_hizb)
    nb_rappels = Reminder.query.filter_by(cycle_id=cycle.id).count()
    return {
        "cycle": cycle,
        "participants": progress["total_membres"],
        "confirmations": progress["membres_confirmes"],
        "retardataires": progress["nb_en_retard"],
        "hizb_confirmes": progress["hizb_confirmes"],
        "total_hizb": total_hizb,
        "rappels_envoyes": nb_rappels,
    }


def get_global_statistics():
    """Statistiques agrégées sur l'ensemble des cycles clôturés."""
    cycles = Cycle.query.filter(Cycle.statut != "actif").order_by(Cycle.date_debut.desc()).all()
    if not cycles:
        return {
            "nb_cycles": 0,
            "taux_moyen_confirmation": 0,
            "total_confirmations": 0,
            "moyenne_retardataires": 0,
            "total_rappels": 0,
        }

    taux = []
    total_confirmations = 0
    total_retardataires = 0
    total_rappels = 0

    for cycle in cycles:
        stats = get_history_stats(cycle)
        total_membres = stats["participants"] or 1
        taux.append(stats["confirmations"] / total_membres * 100)
        total_confirmations += stats["confirmations"]
        total_retardataires += stats["retardataires"]
        total_rappels += stats["rappels_envoyes"]

    return {
        "nb_cycles": len(cycles),
        "taux_moyen_confirmation": round(sum(taux) / len(taux)),
        "total_confirmations": total_confirmations,
        "moyenne_retardataires": round(total_retardataires / len(cycles), 1),
        "total_rappels": total_rappels,
    }

from database import db
from models import Assignment, juz_label
from services.cycle_service import log_action


def get_assignment_for_member(cycle_id, member_id):
    return Assignment.query.filter_by(cycle_id=cycle_id, member_id=member_id).first()


def _verifier_juz_disponible(cycle_id, juz_numero, exclure_assignment_id=None):
    """Leve une ValueError claire si ce جزء est deja attribue a quelqu'un
    d'autre dans ce cycle (regle : un جزء = un seul membre)."""
    query = Assignment.query.filter_by(
        cycle_id=cycle_id, hizb_debut=juz_numero, hizb_fin=juz_numero
    )
    if exclure_assignment_id:
        query = query.filter(Assignment.id != exclure_assignment_id)
    conflit = query.first()
    if conflit:
        raise ValueError(
            f"⚠️ Ce جزء est déjà attribué à un autre membre. "
            f"Il est actuellement attribué à {conflit.member.full_name}."
        )


def create_assignment(cycle_id, member_id, juz_numero, acteur_id, total_hizb=30):
    """Cree une nouvelle attribution : un seul جزء pour ce membre sur ce cycle.
    Un membre ne peut avoir qu'un جزء (regle 1), un جزء ne peut avoir qu'un
    membre (regle 2)."""
    if juz_numero < 1 or juz_numero > total_hizb:
        raise ValueError("Numéro de جزء invalide.")

    if get_assignment_for_member(cycle_id, member_id):
        raise ValueError(
            "Ce membre a déjà un جزء attribué. Utilise \"Modifier le جزء\" pour le changer."
        )

    _verifier_juz_disponible(cycle_id, juz_numero)

    assignment = Assignment(
        cycle_id=cycle_id, member_id=member_id,
        hizb_debut=juz_numero, hizb_fin=juz_numero,
    )
    db.session.add(assignment)
    db.session.flush()
    log_action(
        acteur_id, "attribution_juz",
        f"{juz_label(juz_numero)} attribué à {assignment.member.full_name} (cycle #{cycle_id})."
    )
    db.session.commit()
    return assignment


def update_assignment(assignment: Assignment, juz_numero, acteur_id, total_hizb=30):
    """Remplace le جزء d'une attribution existante (ne cree jamais une
    deuxieme attribution). L'ancien جزء redevient automatiquement disponible
    puisqu'il n'est plus reference par aucune ligne."""
    if juz_numero < 1 or juz_numero > total_hizb:
        raise ValueError("Numéro de جزء invalide.")

    _verifier_juz_disponible(assignment.cycle_id, juz_numero, exclure_assignment_id=assignment.id)

    ancien = assignment.hizb_label
    assignment.hizb_debut = juz_numero
    assignment.hizb_fin = juz_numero

    log_action(
        acteur_id,
        "modification_juz",
        f"جزء de {assignment.member.full_name} modifié : {ancien} → {assignment.hizb_label}",
    )
    db.session.commit()
    return assignment


def get_juz_options(cycle_id, exclure_assignment_id=None, total_hizb=30):
    """Retourne la liste des 30 options pour la liste deroulante, avec leur
    disponibilite (utilise pour griser/annoter les جزء deja pris)."""
    prises = {}
    query = Assignment.query.filter_by(cycle_id=cycle_id)
    if exclure_assignment_id:
        query = query.filter(Assignment.id != exclure_assignment_id)
    for a in query.all():
        if a.hizb_debut == a.hizb_fin:
            prises[a.hizb_debut] = a.member.full_name

    options = []
    for numero in range(1, total_hizb + 1):
        options.append({
            "numero": numero,
            "label": juz_label(numero),
            "disponible": numero not in prises,
            "attribue_a": prises.get(numero),
        })
    return options


def reassign_member(cycle_id, membre_source_id, membre_remplacant_id, acteur_id):
    """Réattribue le جزء d'un membre indisponible à un remplaçant."""
    assignment = get_assignment_for_member(cycle_id, membre_source_id)
    if assignment is None:
        raise ValueError("Aucune attribution trouvée pour ce membre sur ce cycle.")

    assignment.member_id = membre_remplacant_id
    log_action(
        acteur_id,
        "reattribution",
        f"{assignment.hizb_label} réattribué à un remplaçant (cycle #{cycle_id}).",
    )
    db.session.commit()
    return assignment

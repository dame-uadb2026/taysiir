from urllib.parse import quote

from flask import url_for

from database import db
from models import Confirmation, Cycle, Member, Reminder
from services.cycle_service import log_action

MESSAGES = {
    "doux": (
        "Assalamu alaykum {prenom} 🤲\n"
        "Petit rappel concernant ta lecture de cette semaine : {hizb}.\n"
        "La semaine se termine le {date_fin}.\n"
        "Qu'Allah nous facilite."
    ),
    "proche_echeance": (
        "Assalamu alaykum {prenom} 🤲\n"
        "La semaine se termine bientôt ({date_fin}) et ta lecture ({hizb}) n'est pas encore "
        "confirmée. Merci de la terminer dès que possible, qu'Allah te facilite."
    ),
    "retard": (
        "Assalamu alaykum {prenom} 🤲\n"
        "La date limite de la semaine ({date_fin}) est dépassée et ta lecture ({hizb}) n'a "
        "pas encore été confirmée. Merci de nous tenir informés dès que tu as terminé, "
        "qu'Allah te facilite."
    ),
}


def determine_reminder_type(cycle: Cycle):
    from datetime import datetime
    jours_restants = (cycle.date_fin - datetime.utcnow()).days
    if datetime.utcnow() > cycle.date_fin:
        return "retard"
    if jours_restants <= 1:
        return "proche_echeance"
    return "doux"


def build_whatsapp_message(member: Member, assignment, cycle: Cycle, template: str = None) -> str:
    """Construit le texte du rappel a partir du modele personnalisable de
    l'amicale (cycle.organization.reminder_template par defaut, ou un texte
    fourni explicitement si le gerant l'a modifie juste avant l'envoi)."""
    if template is None:
        template = cycle.organization.reminder_template

    valeurs = {
        "prenom": member.prenom,
        "hizb": assignment.hizb_label,
        "semaine": f"{cycle.date_debut.strftime('%d/%m')} au {cycle.date_fin.strftime('%d/%m/%Y')}",
        "date_debut": cycle.date_debut.strftime("%d/%m/%Y"),
        "date_fin": cycle.date_fin.strftime("%d/%m/%Y"),
        "lien": url_for("member_dashboard", _external=True),
    }
    resultat = template
    for cle, valeur in valeurs.items():
        resultat = resultat.replace("{" + cle + "}", str(valeur))
    return resultat


def build_whatsapp_link(member: Member, message: str) -> str:
    numero = "".join(ch for ch in member.whatsapp if ch.isdigit() or ch == "+")
    return f"https://wa.me/{numero.lstrip('+')}?text={quote(message)}"


def record_reminder(cycle: Cycle, member: Member, acteur_id):
    """Enregistre qu'un rappel a été envoyé (déclaré par le gérant après l'envoi WhatsApp)."""
    type_rappel = determine_reminder_type(cycle)
    nb_precedents = Reminder.query.filter_by(cycle_id=cycle.id, member_id=member.id).count()

    reminder = Reminder(
        cycle_id=cycle.id,
        member_id=member.id,
        type_rappel=type_rappel,
        numero_rappel=nb_precedents + 1,
    )
    db.session.add(reminder)
    log_action(acteur_id, "rappel_envoye",
               f"Rappel ({type_rappel}) envoyé à {member.full_name} pour le cycle #{cycle.id}.")
    db.session.commit()
    return reminder


def member_has_been_reminded(cycle_id, member_id) -> bool:
    return Reminder.query.filter_by(cycle_id=cycle_id, member_id=member_id).count() > 0

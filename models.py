from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from database import db


def normalize_whatsapp(raw: str) -> str:
    """Nettoie un numéro WhatsApp (espaces, tirets, points) pour un stockage
    et une comparaison cohérents, quel que soit le format saisi."""
    if not raw:
        return raw
    raw = raw.strip()
    cleaned = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    return cleaned


# Liste exacte et complète des 30 أجزاء, reprise telle quelle (ne pas modifier
# la formulation, l'ordre, ni le nombre d'éléments).
JUZ_NAMES = [
    "الجزء الأول (الجزء 1): الم (آلم)",
    "الجزء الثاني (الجزء 2): سيقول السفهاء",
    "الجزء الثالث (الجزء 3): تلك الرسل",
    "الجزء الرابع (الجزء 4): لن تنالوا البر",
    "الجزء الخامس (الجزء 5): والمحصنات",
    "الجزء السادس (الجزء 6): لا يحب الله",
    "الجزء السابع (الجزء 7): لتجدن / وإذا سمعوا",
    "الجزء الثامن (الجزء 8): ولو أننا نزلنا",
    "الجزء التاسع (الجزء 9): قال الملأ",
    "الجزء العاشر (الجزء 10): واعلموا",
    "الجزء الحادي عشر (الجزء 11): يعتذرون",
    "الجزء الثاني عشر (الجزء 12): وما من دابة",
    "الجزء الثالث عشر (الجزء 13): وما أبرئ نفسي",
    "الجزء الرابع عشر (الجزء 14): ربما",
    "الجزء الخامس عشر (الجزء 15): سبحان الذي",
    "الجزء السادس عشر (الجزء 16): قال ألم",
    "الجزء السابع عشر (الجزء 17): اقترب للناس",
    "الجزء الثامن عشر (الجزء 18): قد أفلح المؤمنون",
    "الجزء التاسع عشر (الجزء 19): وقال الذين لا يرجون",
    "الجزء العشرون (الجزء 20): فما كان جواب قومه",
    "الجزء الحادي والعشرون (الجزء 21): ولا تجادلوا / اتل ما أوحي",
    "الجزء الثاني والعشرون (الجزء 22): ومن يقنت",
    "الجزء الثالث والعشرون (الجزء 23): وما أنزلنا",
    "الجزء الرابع والعشرون (الجزء 24): فمن أظلم",
    "الجزء الخامس والعشرون (الجزء 25): إليه يرد",
    "الجزء السادس والعشرون (الجزء 26): حم (الأحقاف)",
    "الجزء السابع والعشرون (الجزء 27): قال فما خطبكم",
    "الجزء الثامن والعشرون (الجزء 28): قد سمع الله",
    "الجزء التاسع والعشرون (الجزء 29): تبارك (الملك)",
    "الجزء الثلاثون (الجزء 30): عم يتساءلون (النبأ)",
]


def juz_label(numero: int) -> str:
    """Texte complet d'un جزء a partir de son numero (1 a 30)."""
    if 1 <= numero <= len(JUZ_NAMES):
        return JUZ_NAMES[numero - 1]
    return f"جزء {numero}"


class Member(db.Model, UserMixin):
    __tablename__ = "members"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(80), nullable=False)
    prenom = db.Column(db.String(80), nullable=False)
    whatsapp = db.Column(db.String(30), unique=True, nullable=False)
    email = db.Column(db.String(120), nullable=True)
    role = db.Column(db.String(20), nullable=False, default="member")  # "member" | "manager"
    actif = db.Column(db.Boolean, default=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    date_ajout = db.Column(db.DateTime, default=datetime.utcnow)

    assignments = db.relationship("Assignment", backref="member", lazy=True)
    confirmations = db.relationship("Confirmation", backref="member", lazy=True)
    reminders = db.relationship("Reminder", backref="member", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_manager(self) -> bool:
        return self.role == "manager"

    @property
    def full_name(self) -> str:
        return f"{self.prenom} {self.nom}"


class Cycle(db.Model):
    __tablename__ = "cycles"

    id = db.Column(db.Integer, primary_key=True)
    date_debut = db.Column(db.DateTime, nullable=False)
    date_fin = db.Column(db.DateTime, nullable=False)
    statut = db.Column(db.String(20), nullable=False, default="actif")  # actif | termine | archive
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    createur_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    assignments = db.relationship(
        "Assignment", backref="cycle", lazy=True, cascade="all, delete-orphan"
    )
    confirmations = db.relationship(
        "Confirmation", backref="cycle", lazy=True, cascade="all, delete-orphan"
    )
    reminders = db.relationship(
        "Reminder", backref="cycle", lazy=True, cascade="all, delete-orphan"
    )

    @property
    def est_termine_dans_le_temps(self) -> bool:
        return datetime.utcnow() > self.date_fin


class Assignment(db.Model):
    __tablename__ = "assignments"

    id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey("cycles.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    hizb_debut = db.Column(db.Integer, nullable=False)
    hizb_fin = db.Column(db.Integer, nullable=False)
    date_attribution = db.Column(db.DateTime, default=datetime.utcnow)

    confirmation = db.relationship(
        "Confirmation", backref="assignment", uselist=False, lazy=True
    )

    @property
    def juz_numero(self) -> int:
        return self.hizb_debut

    @property
    def hizb_label(self) -> str:
        return juz_label(self.hizb_debut)

    @property
    def nb_hizb(self) -> int:
        return 1


class Confirmation(db.Model):
    __tablename__ = "confirmations"

    id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey("cycles.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False)
    date_confirmation = db.Column(db.DateTime, default=datetime.utcnow)
    apres_rappel = db.Column(db.Boolean, default=False)


class Reminder(db.Model):
    __tablename__ = "reminders"

    id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey("cycles.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    type_rappel = db.Column(db.String(20), nullable=False)  # doux | proche_echeance | retard
    date_envoi = db.Column(db.DateTime, default=datetime.utcnow)
    numero_rappel = db.Column(db.Integer, default=1)  # 1er, 2e, 3e rappel pour ce cycle/membre
    statut = db.Column(db.String(20), default="envoye")  # envoye (déclaré par le gérant)


class StatusSignal(db.Model):
    """Signalement explicite d'un membre : 'je n'ai pas encore termine'."""
    __tablename__ = "status_signals"

    id = db.Column(db.Integer, primary_key=True)
    cycle_id = db.Column(db.Integer, db.ForeignKey("cycles.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False)
    date_signal = db.Column(db.DateTime, default=datetime.utcnow)


class MemberDocument(db.Model):
    """Lien Google Drive rattache a la fiche d'un membre."""
    __tablename__ = "member_documents"

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    nom = db.Column(db.String(200), nullable=False)
    lien = db.Column(db.String(500), nullable=False)
    date_ajout = db.Column(db.DateTime, default=datetime.utcnow)

    member = db.relationship("Member", backref="documents")


class Settings(db.Model):
    """Ligne unique de parametres globaux de l'application."""
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    cycle_auto = db.Column(db.Boolean, default=True, nullable=False)
    jour_debut = db.Column(db.Integer, default=4, nullable=False)  # 4 = vendredi (lundi=0)
    reminder_template = db.Column(db.Text, default=(
        "Salam {prenom} 🌸\n\n"
        "Petit rappel concernant ta lecture de cette semaine.\n\n"
        "Tu as le {hizb}.\n\n"
        "Peux-tu nous confirmer lorsque tu auras terminé ?\n\n"
        "Qu'Allah accepte 🤲"
    ))


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    date_action = db.Column(db.DateTime, default=datetime.utcnow)
    acteur_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=True)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)

    acteur = db.relationship("Member", foreign_keys=[acteur_id])

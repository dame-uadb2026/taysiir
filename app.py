import os
from datetime import datetime

import click
from flask import (Flask, Response, abort, flash, redirect, render_template,
                    request, url_for)
from flask_login import (LoginManager, current_user, login_required, login_user,
                          logout_user)
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from database import db
from models import (Assignment, Confirmation, Cycle, DEFAULT_REMINDER_TEMPLATE, Member,
                     MemberDocument, Organization, PREVIOUS_DEFAULT_REMINDER_TEMPLATE,
                     Reminder, StatusSignal, normalize_whatsapp)
from services import cycle_service, reminder_service, statistics_service
from services.assignment_service import (create_assignment, get_assignment_for_member,
                                          get_juz_options, update_assignment)

MOIS_FR = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre",
    12: "décembre",
}

LOGO_MAX_BYTES = 2 * 1024 * 1024  # 2 Mo


def format_date_fr(value, avec_annee=False):
    if not value:
        return ""
    mois = MOIS_FR[value.month]
    if avec_annee:
        return f"{value.day} {mois} {value.year}"
    return f"{value.day} {mois}"


def format_datetime_fr(value):
    if not value:
        return ""
    return f"{format_date_fr(value)} à {value.strftime('%H:%M')}"


def _migrate_to_organizations(app):
    """Migration légère (sans Alembic) pour les installations créées avant
    l'introduction du multi-amicales : ajoute organization_id aux tables
    members/cycles si absent, crée une amicale par défaut, et y rattache
    les données déjà présentes. Ne fait rien sur une base neuve."""
    inspector = db.inspect(db.engine)
    if "members" not in inspector.get_table_names():
        return  # base neuve : db.create_all() a deja tout cree avec le bon schema

    colonnes = [c["name"] for c in inspector.get_columns("members")]
    if "organization_id" in colonnes:
        return  # deja migre

    with db.engine.connect() as conn:
        conn.execute(db.text("ALTER TABLE members ADD COLUMN organization_id INTEGER"))
        conn.execute(db.text("ALTER TABLE cycles ADD COLUMN organization_id INTEGER"))
        conn.commit()

    nom_defaut = os.environ.get("SEED_MANAGER_ORG_NOM", Config.ORG_NAME_MIGRATION_FALLBACK)
    amicale = Organization(nom=nom_defaut)

    # Reprend le logo statique existant s'il est present, pour ne rien perdre
    # visuellement lors de la migration d'une installation deja en place.
    logo_path = os.path.join(app.root_path, "static", "img", "logo_aertm.jpg")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            amicale.logo_data = f.read()
            amicale.logo_mimetype = "image/jpeg"

    db.session.add(amicale)
    db.session.flush()

    db.session.execute(
        db.text("UPDATE members SET organization_id = :oid WHERE organization_id IS NULL"),
        {"oid": amicale.id},
    )
    db.session.execute(
        db.text("UPDATE cycles SET organization_id = :oid WHERE organization_id IS NULL"),
        {"oid": amicale.id},
    )
    db.session.commit()


def _migrate_reminder_templates():
    """Met à jour automatiquement le modèle de rappel des amicales qui
    utilisent encore l'ancien modèle par défaut (sans lien direct vers
    l'application), sans jamais toucher à un message personnalisé par le
    gérant."""
    amicales = Organization.query.filter_by(
        reminder_template=PREVIOUS_DEFAULT_REMINDER_TEMPLATE
    ).all()
    for amicale in amicales:
        amicale.reminder_template = DEFAULT_REMINDER_TEMPLATE
    if amicales:
        db.session.commit()


def _seed_manager_from_env(app):
    """Crée le compte gérant par défaut (et son amicale par défaut si besoin)
    à partir des variables d'environnement SEED_MANAGER_*, uniquement si ce
    numéro n'existe pas déjà. Idempotent."""
    prenom = app.config.get("SEED_MANAGER_PRENOM")
    nom = app.config.get("SEED_MANAGER_NOM")
    whatsapp = app.config.get("SEED_MANAGER_WHATSAPP")
    password = app.config.get("SEED_MANAGER_PASSWORD")

    if not all([prenom, nom, whatsapp, password]):
        return  # variables non fournies : rien à faire (cas normal en local)

    whatsapp = normalize_whatsapp(whatsapp)

    if Member.query.filter_by(whatsapp=whatsapp).first():
        return  # déjà créé

    amicale = Organization.query.first()
    if not amicale:
        amicale = Organization(
            nom=os.environ.get("SEED_MANAGER_ORG_NOM", Config.ORG_NAME_MIGRATION_FALLBACK)
        )
        db.session.add(amicale)
        db.session.flush()

    gerant = Member(organization_id=amicale.id, prenom=prenom, nom=nom,
                     whatsapp=whatsapp, role="manager")
    gerant.set_password(password)
    db.session.add(gerant)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Derriere le proxy de Render (ou tout hebergeur similaire), sans ceci
    # les liens generes avec _external=True seraient en http:// au lieu de
    # https:// (Render termine le HTTPS puis transmet en interne).
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    db.init_app(app)
    CSRFProtect(app)

    app.jinja_env.filters["date_fr"] = format_date_fr
    app.jinja_env.filters["datetime_fr"] = format_datetime_fr

    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.login_message = "Merci de vous connecter pour accéder à l'application."
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return Member.query.get(int(user_id))

    with app.app_context():
        db.create_all()
        _migrate_to_organizations(app)
        _migrate_reminder_templates()
        _seed_manager_from_env(app)

    # ---------------------------------------------------------------------
    # AUTHENTIFICATION
    # ---------------------------------------------------------------------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        if request.method == "POST":
            whatsapp = normalize_whatsapp(request.form.get("whatsapp", ""))
            password = request.form.get("password", "")
            membre = Member.query.filter_by(whatsapp=whatsapp).first()
            if membre and membre.actif and membre.check_password(password):
                login_user(membre)
                return redirect(url_for("index"))
            flash("Numéro ou mot de passe incorrect.", "error")

        return render_template("login.html", config=Config)

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def index():
        if current_user.is_manager:
            return redirect(url_for("manager_dashboard"))
        return redirect(url_for("member_dashboard"))

    # ---------------------------------------------------------------------
    # AMICALES (multi-tenant)
    # ---------------------------------------------------------------------
    @app.route("/creer-amicale", methods=["GET", "POST"])
    def create_organization():
        if not Config.ALLOW_ORG_SIGNUP:
            # Cette version de l'application est réservée à une seule amicale ;
            # la création publique de nouvelles amicales est désactivée.
            abort(404)

        if current_user.is_authenticated:
            return redirect(url_for("index"))

        if request.method == "POST":
            nom_amicale = request.form.get("nom_amicale", "").strip()
            prenom = request.form.get("prenom", "").strip()
            nom = request.form.get("nom", "").strip()
            whatsapp = normalize_whatsapp(request.form.get("whatsapp", ""))
            password = request.form.get("password", "")

            if not nom_amicale or not prenom or not nom or not whatsapp or not password:
                flash("Tous les champs sont obligatoires.", "error")
                return render_template("create_organization.html", config=Config)

            if Member.query.filter_by(whatsapp=whatsapp).first():
                flash("Ce numéro WhatsApp est déjà utilisé par un compte existant.", "error")
                return render_template("create_organization.html", config=Config)

            amicale = Organization(nom=nom_amicale)

            logo = request.files.get("logo")
            if logo and logo.filename:
                donnees = logo.read()
                if len(donnees) > LOGO_MAX_BYTES:
                    flash("Le logo est trop volumineux (2 Mo maximum).", "error")
                    return render_template("create_organization.html", config=Config)
                amicale.logo_data = donnees
                amicale.logo_mimetype = logo.mimetype

            db.session.add(amicale)
            db.session.flush()

            gerant = Member(organization_id=amicale.id, prenom=prenom, nom=nom,
                             whatsapp=whatsapp, role="manager")
            gerant.set_password(password)
            db.session.add(gerant)
            cycle_service.log_action(
                None, "creation_amicale",
                f"Amicale « {amicale.nom} » créée avec {gerant.full_name} comme gérant."
            )
            db.session.commit()

            login_user(gerant)
            flash(f"Bienvenue ! L'amicale « {amicale.nom} » a été créée.", "success")
            return redirect(url_for("index"))

        return render_template("create_organization.html", config=Config)

    @app.route("/logo/<int:organization_id>")
    def organization_logo(organization_id):
        amicale = Organization.query.get_or_404(organization_id)
        if not amicale.logo_data:
            abort(404)
        return Response(amicale.logo_data, mimetype=amicale.logo_mimetype or "image/jpeg")

    # ---------------------------------------------------------------------
    # ESPACE MEMBRE
    # ---------------------------------------------------------------------
    @app.route("/membre")
    @login_required
    def member_dashboard():
        cycle = cycle_service.get_or_create_current_cycle(current_user.organization, current_user.id)
        assignment = None
        confirmation = None
        signal = None
        if cycle:
            assignment = get_assignment_for_member(cycle.id, current_user.id)
            if assignment:
                confirmation = Confirmation.query.filter_by(
                    assignment_id=assignment.id
                ).first()
                signal = StatusSignal.query.filter_by(
                    cycle_id=cycle.id, member_id=current_user.id
                ).first()

        return render_template(
            "member_dashboard.html",
            config=Config,
            cycle=cycle,
            assignment=assignment,
            confirmation=confirmation,
            signal=signal,
        )

    @app.route("/membre/pas-termine", methods=["POST"])
    @login_required
    def member_not_done():
        cycle = cycle_service.get_or_create_current_cycle(current_user.organization, current_user.id)
        if not cycle:
            flash("Aucun cycle actif pour le moment.", "error")
            return redirect(url_for("member_dashboard"))

        assignment = get_assignment_for_member(cycle.id, current_user.id)
        if not assignment:
            flash("Vous n'avez pas d'attribution pour ce cycle.", "error")
            return redirect(url_for("member_dashboard"))

        if Confirmation.query.filter_by(assignment_id=assignment.id).first():
            flash("Votre lecture est déjà confirmée.", "info")
            return redirect(url_for("member_dashboard"))

        existant = StatusSignal.query.filter_by(
            cycle_id=cycle.id, member_id=current_user.id
        ).first()
        if existant:
            existant.date_signal = datetime.utcnow()
        else:
            db.session.add(StatusSignal(
                cycle_id=cycle.id, member_id=current_user.id, assignment_id=assignment.id,
            ))
        db.session.commit()
        flash("C'est noté, merci de nous avoir prévenus 🤲", "info")
        return redirect(url_for("member_dashboard"))

    @app.route("/membre/confirmer", methods=["POST"])
    @login_required
    def member_confirm():
        cycle = cycle_service.get_or_create_current_cycle(current_user.organization, current_user.id)
        if not cycle:
            flash("Aucun cycle actif pour le moment.", "error")
            return redirect(url_for("member_dashboard"))

        assignment = get_assignment_for_member(cycle.id, current_user.id)
        if not assignment:
            flash("Vous n'avez pas d'attribution pour ce cycle.", "error")
            return redirect(url_for("member_dashboard"))

        deja = Confirmation.query.filter_by(assignment_id=assignment.id).first()
        if deja:
            flash("Votre lecture est déjà confirmée.", "info")
            return redirect(url_for("member_dashboard"))

        apres_rappel = reminder_service.member_has_been_reminded(cycle.id, current_user.id)
        confirmation = Confirmation(
            cycle_id=cycle.id,
            member_id=current_user.id,
            assignment_id=assignment.id,
            apres_rappel=apres_rappel,
        )
        db.session.add(confirmation)
        cycle_service.log_action(
            current_user.id, "confirmation_lecture",
            f"{current_user.full_name} a confirmé {assignment.hizb_label} (cycle #{cycle.id})."
        )
        db.session.commit()
        cycle_service.verifier_et_reconduire_si_complet(current_user.organization, cycle, current_user.id)
        flash("Alhamdoulillah 🤲 Votre lecture est enregistrée.", "success")
        return redirect(url_for("member_dashboard"))

    @app.route("/compte", methods=["GET", "POST"])
    @login_required
    def account():
        if request.method == "POST":
            ancien = request.form.get("ancien_mdp", "")
            nouveau = request.form.get("nouveau_mdp", "")
            confirmation = request.form.get("confirmation_mdp", "")

            if not current_user.check_password(ancien):
                flash("Ancien mot de passe incorrect.", "error")
            elif len(nouveau) < 4:
                flash("Le nouveau mot de passe doit contenir au moins 4 caractères.", "error")
            elif nouveau != confirmation:
                flash("La confirmation ne correspond pas au nouveau mot de passe.", "error")
            else:
                current_user.set_password(nouveau)
                cycle_service.log_action(current_user.id, "changement_mot_de_passe",
                                          f"{current_user.full_name} a changé son mot de passe.")
                db.session.commit()
                flash("Mot de passe mis à jour avec succès.", "success")

        return render_template("account.html", config=Config)

    # ---------------------------------------------------------------------
    # ESPACE GÉRANT
    # ---------------------------------------------------------------------
    def manager_required():
        if not current_user.is_manager:
            abort(403)

    def get_member_or_404(member_id):
        """Récupère un membre en s'assurant qu'il appartient bien à
        l'amicale du gérant connecté (isolation entre amicales)."""
        return Member.query.filter_by(
            id=member_id, organization_id=current_user.organization_id
        ).first_or_404()

    @app.route("/gerant")
    @login_required
    def manager_dashboard():
        manager_required()
        cycle = cycle_service.get_or_create_current_cycle(current_user.organization, current_user.id)
        progress = statistics_service.get_cycle_progress(cycle, Config.TOTAL_HIZB) if cycle else None
        actions = statistics_service.get_dashboard_actions(cycle) if cycle else []
        erreurs = cycle_service.validate_cycle_coverage(cycle, Config.TOTAL_HIZB) if cycle else []
        sans_hizb = statistics_service.get_members_without_assignment(cycle) if cycle else []

        return render_template(
            "manager_dashboard.html",
            config=Config,
            cycle=cycle,
            progress=progress,
            actions=actions,
            erreurs=erreurs,
            settings=current_user.organization,
            sans_hizb=sans_hizb,
        )

    @app.route("/gerant/cycles/nouveau", methods=["GET", "POST"])
    @login_required
    def new_cycle():
        manager_required()
        if request.method == "POST":
            date_debut = datetime.strptime(request.form["date_debut"], "%Y-%m-%d")
            date_fin = datetime.strptime(request.form["date_fin"], "%Y-%m-%d")
            date_fin = date_fin.replace(hour=23, minute=59, second=59)
            ancien = cycle_service.get_active_cycle(current_user.organization_id)
            if ancien:
                cycle_service.close_cycle(ancien, current_user.id)
            cycle_service.create_cycle(current_user.organization_id, date_debut, date_fin,
                                        current_user.id)
            flash("Nouvelle semaine créée. Pense à attribuer les أجزاء aux membres.", "success")
            return redirect(url_for("manager_dashboard"))

        return render_template("cycle_new.html", config=Config)

    @app.route("/gerant/cycles/nouveau-meme-groupe", methods=["POST"])
    @login_required
    def new_cycle_same_group():
        manager_required()
        actuel = cycle_service.get_active_cycle(current_user.organization_id)
        if not actuel:
            flash("Aucun cycle actif à reconduire. Crée d'abord une semaine.", "error")
            return redirect(url_for("manager_dashboard"))

        cycle_service.create_next_cycle_same_group(current_user.organization, actuel, current_user.id)
        flash("Nouveau cycle lancé avec le même groupe et les mêmes أجزاء.", "success")
        return redirect(url_for("manager_dashboard"))

    @app.route("/gerant/cycles/<int:cycle_id>/supprimer", methods=["POST"])
    @login_required
    def delete_cycle(cycle_id):
        manager_required()
        cycle = Cycle.query.filter_by(
            id=cycle_id, organization_id=current_user.organization_id
        ).first_or_404()
        cycle_service.delete_cycle(cycle, current_user.id)
        flash("Cycle supprimé définitivement.", "success")
        if request.referrer and "historique" in request.referrer:
            return redirect(url_for("manager_history"))
        return redirect(url_for("manager_dashboard"))

    @app.route("/gerant/membres/ajout-rapide", methods=["POST"])
    @login_required
    def add_members_bulk():
        manager_required()
        texte = request.form.get("liste", "")
        lignes = [l.strip() for l in texte.splitlines() if l.strip()]

        crees, ignores, erreurs = 0, 0, []
        for ligne in lignes:
            separateur = "," if "," in ligne else ("\t" if "\t" in ligne else None)
            if separateur:
                parties = [p.strip() for p in ligne.split(separateur, 1)]
            else:
                parties = ligne.rsplit(" ", 1)

            if len(parties) != 2 or not parties[0] or not parties[1]:
                erreurs.append(ligne)
                ignores += 1
                continue

            nom_complet, whatsapp = parties
            whatsapp = normalize_whatsapp(whatsapp)
            if not whatsapp:
                erreurs.append(ligne)
                ignores += 1
                continue

            if Member.query.filter_by(whatsapp=whatsapp).first():
                ignores += 1
                continue

            mots = nom_complet.split(" ", 1)
            prenom = mots[0]
            nom = mots[1] if len(mots) > 1 else mots[0]

            membre = Member(organization_id=current_user.organization_id, prenom=prenom,
                             nom=nom, whatsapp=whatsapp, role="member")
            membre.set_password("taysir123")
            db.session.add(membre)
            crees += 1

        db.session.commit()
        if crees:
            cycle_service.log_action(current_user.id, "ajout_rapide_membres",
                                      f"{crees} membre(s) ajoute(s) en une fois.")
            db.session.commit()

        message = f"{crees} membre(s) ajouté(s)."
        if ignores:
            message += f" {ignores} ligne(s) ignorée(s) (doublon ou format incorrect)."
        flash(message, "success" if crees else "error")
        if erreurs:
            flash("Lignes non reconnues : " + " | ".join(erreurs[:5]), "error")
        return redirect(url_for("manager_members"))

    @app.route("/gerant/membres/<int:member_id>/attribuer", methods=["GET", "POST"])
    @login_required
    def assign_hizb(member_id):
        manager_required()
        membre = get_member_or_404(member_id)
        cycle = cycle_service.get_or_create_current_cycle(current_user.organization, current_user.id)
        if not cycle:
            flash("Aucun cycle actif pour le moment.", "error")
            return redirect(url_for("member_detail", member_id=member_id))

        assignment = get_assignment_for_member(cycle.id, member_id)

        if request.method == "POST":
            try:
                juz_numero = int(request.form["juz_numero"])
                if assignment:
                    update_assignment(assignment, juz_numero, current_user.id,
                                       total_hizb=Config.TOTAL_HIZB)
                    flash("جزء modifié.", "success")
                else:
                    create_assignment(cycle.id, member_id, juz_numero,
                                       current_user.id, total_hizb=Config.TOTAL_HIZB)
                    flash("جزء attribué avec succès.", "success")
                return redirect(url_for("member_detail", member_id=member_id))
            except ValueError as e:
                flash(str(e), "error")

        options = get_juz_options(
            cycle.id,
            exclure_assignment_id=assignment.id if assignment else None,
            total_hizb=Config.TOTAL_HIZB,
        )
        return render_template(
            "assign_hizb.html", config=Config, membre=membre, cycle=cycle,
            assignment=assignment, options=options,
        )

    @app.route("/gerant/membres/<int:member_id>")
    @login_required
    def member_detail(member_id):
        manager_required()
        membre = get_member_or_404(member_id)
        cycle = cycle_service.get_or_create_current_cycle(current_user.organization, current_user.id)
        assignment = get_assignment_for_member(cycle.id, member_id) if cycle else None
        statut = statistics_service.get_member_status(cycle, membre) if cycle else "n/a"
        documents = MemberDocument.query.filter_by(member_id=member_id).order_by(
            MemberDocument.date_ajout.desc()
        ).all()
        return render_template(
            "member_detail.html", config=Config, membre=membre, cycle=cycle,
            assignment=assignment, statut=statut, documents=documents,
        )

    @app.route("/gerant/membres/<int:member_id>/documents/ajouter", methods=["POST"])
    @login_required
    def add_document(member_id):
        manager_required()
        get_member_or_404(member_id)
        nom = request.form.get("nom", "").strip()
        lien = request.form.get("lien", "").strip()
        if not nom or not lien:
            flash("Le nom du document et le lien sont obligatoires.", "error")
        else:
            db.session.add(MemberDocument(member_id=member_id, nom=nom, lien=lien))
            cycle_service.log_action(current_user.id, "ajout_document",
                                      f"Document '{nom}' ajouté pour le membre #{member_id}.")
            db.session.commit()
            flash("Document ajouté.", "success")
        return redirect(url_for("member_detail", member_id=member_id))

    @app.route("/gerant/documents/<int:document_id>/supprimer", methods=["POST"])
    @login_required
    def delete_document(document_id):
        manager_required()
        document = MemberDocument.query.get_or_404(document_id)
        if document.member.organization_id != current_user.organization_id:
            abort(404)
        member_id = document.member_id
        db.session.delete(document)
        db.session.commit()
        flash("Document supprimé.", "success")
        return redirect(url_for("member_detail", member_id=member_id))

    @app.route("/gerant/membres/<int:member_id>/retirer-juz", methods=["POST"])
    @login_required
    def remove_juz(member_id):
        manager_required()
        membre = get_member_or_404(member_id)
        cycle = cycle_service.get_or_create_current_cycle(current_user.organization, current_user.id)
        if cycle:
            assignment = get_assignment_for_member(cycle.id, member_id)
            if assignment:
                juz = assignment.hizb_label
                Confirmation.query.filter_by(assignment_id=assignment.id).delete()
                StatusSignal.query.filter_by(assignment_id=assignment.id).delete()
                db.session.delete(assignment)
                cycle_service.log_action(current_user.id, "retrait_juz",
                                          f"{juz} retiré à {membre.full_name} (cycle #{cycle.id}), "
                                          f"redevenu disponible.")
                db.session.commit()
                flash("جزء retiré, il est de nouveau disponible pour un autre membre.", "success")
            else:
                flash("Ce membre n'avait pas de جزء attribué.", "info")
        return redirect(url_for("member_detail", member_id=member_id))

    @app.route("/gerant/membres/<int:member_id>/modifier", methods=["GET", "POST"])
    @login_required
    def edit_member(member_id):
        manager_required()
        membre = get_member_or_404(member_id)

        if request.method == "POST":
            nouveau_whatsapp = normalize_whatsapp(request.form.get("whatsapp", ""))
            prenom = request.form.get("prenom", "").strip()
            nom = request.form.get("nom", "").strip()
            email = request.form.get("email", "").strip() or None

            if not prenom or not nom or not nouveau_whatsapp:
                flash("Le prénom, le nom et le numéro WhatsApp sont obligatoires.", "error")
            elif Member.query.filter(Member.whatsapp == nouveau_whatsapp,
                                      Member.id != member_id).first():
                flash(f"Un autre membre utilise déjà le numéro {nouveau_whatsapp}.", "error")
            else:
                membre.prenom = prenom
                membre.nom = nom
                membre.whatsapp = nouveau_whatsapp
                membre.email = email
                cycle_service.log_action(current_user.id, "modification_membre",
                                          f"Fiche de {membre.full_name} modifiée.")
                db.session.commit()
                flash("Membre modifié.", "success")
                return redirect(url_for("member_detail", member_id=member_id))

        return render_template("edit_member.html", config=Config, membre=membre)

    @app.route("/gerant/membres/<int:member_id>/supprimer", methods=["POST"])
    @login_required
    def delete_member(member_id):
        manager_required()
        membre = get_member_or_404(member_id)
        nom_complet = membre.full_name

        Confirmation.query.filter_by(member_id=member_id).delete()
        StatusSignal.query.filter_by(member_id=member_id).delete()
        Assignment.query.filter_by(member_id=member_id).delete()
        Reminder.query.filter_by(member_id=member_id).delete()
        MemberDocument.query.filter_by(member_id=member_id).delete()
        db.session.delete(membre)

        cycle_service.log_action(current_user.id, "suppression_membre",
                                  f"{nom_complet} supprimé (son جزء, s'il en avait un, "
                                  f"est redevenu disponible).")
        db.session.commit()
        flash(f"{nom_complet} a été supprimé.", "success")
        return redirect(url_for("manager_members"))

    @app.route("/gerant/parametres", methods=["GET", "POST"])
    @login_required
    def manager_settings():
        manager_required()
        amicale = current_user.organization

        if request.method == "POST":
            nouveau_nom = request.form.get("nom_amicale", "").strip()
            if nouveau_nom:
                amicale.nom = nouveau_nom

            logo = request.files.get("logo")
            if logo and logo.filename:
                donnees = logo.read()
                if len(donnees) > LOGO_MAX_BYTES:
                    flash("Le logo est trop volumineux (2 Mo maximum).", "error")
                    return redirect(url_for("manager_settings"))
                amicale.logo_data = donnees
                amicale.logo_mimetype = logo.mimetype

            amicale.cycle_auto = request.form.get("cycle_auto") == "on"
            nouveau_template = request.form.get("reminder_template", "").strip()
            if nouveau_template:
                amicale.reminder_template = nouveau_template
            db.session.commit()
            flash("Paramètres mis à jour.", "success")
            return redirect(url_for("manager_settings"))

        return render_template("settings.html", config=Config, settings=amicale, amicale=amicale)

    @app.route("/gerant/membres")
    @login_required
    def manager_members():
        manager_required()
        statut = request.args.get("statut", "tous")
        recherche = request.args.get("q", "").strip()

        query = Member.query.filter_by(role="member", organization_id=current_user.organization_id)
        if recherche:
            like = f"%{recherche}%"
            query = query.filter(db.or_(Member.nom.ilike(like), Member.prenom.ilike(like)))
        membres = query.order_by(Member.nom).all()

        cycle = cycle_service.get_or_create_current_cycle(current_user.organization, current_user.id)
        membres_avec_statut = []
        for m in membres:
            statut_m = statistics_service.get_member_status(cycle, m) if cycle else "n/a"
            if statut != "tous" and statut_m != statut:
                continue
            assignment = get_assignment_for_member(cycle.id, m.id) if cycle else None
            membres_avec_statut.append({"membre": m, "statut": statut_m, "assignment": assignment})

        return render_template(
            "members.html", config=Config, membres=membres_avec_statut,
            cycle=cycle, statut_filtre=statut, recherche=recherche,
        )

    @app.route("/gerant/membres/ajouter", methods=["POST"])
    @login_required
    def add_member():
        manager_required()
        whatsapp = normalize_whatsapp(request.form["whatsapp"])

        if Member.query.filter_by(whatsapp=whatsapp).first():
            flash(f"Un membre existe déjà avec le numéro {whatsapp}.", "error")
            return redirect(url_for("manager_members"))

        membre = Member(
            organization_id=current_user.organization_id,
            nom=request.form["nom"].strip(),
            prenom=request.form["prenom"].strip(),
            whatsapp=whatsapp,
            email=request.form.get("email", "").strip() or None,
            role="member",
        )
        membre.set_password(request.form.get("password") or "taysir123")
        db.session.add(membre)
        cycle_service.log_action(current_user.id, "ajout_membre", f"{membre.full_name} ajouté.")
        db.session.commit()
        flash(f"{membre.full_name} a été ajouté.", "success")
        return redirect(url_for("manager_members"))

    @app.route("/gerant/membres/<int:member_id>/toggle", methods=["POST"])
    @login_required
    def toggle_member(member_id):
        manager_required()
        membre = get_member_or_404(member_id)
        membre.actif = not membre.actif
        cycle_service.log_action(
            current_user.id, "statut_membre",
            f"{membre.full_name} {'réactivé' if membre.actif else 'désactivé'}."
        )
        db.session.commit()
        flash(f"{membre.full_name} {'réactivé' if membre.actif else 'désactivé'}.", "success")
        return redirect(url_for("manager_members"))

    @app.route("/gerant/rappel/<int:member_id>", methods=["POST"])
    @login_required
    def send_reminder(member_id):
        manager_required()
        cycle = cycle_service.get_or_create_current_cycle(current_user.organization, current_user.id)
        membre = get_member_or_404(member_id)
        if not cycle:
            abort(404)
        assignment = get_assignment_for_member(cycle.id, member_id)
        if not assignment:
            abort(404)
        message_modifie = request.form.get("message", "").strip()
        message = message_modifie or reminder_service.build_whatsapp_message(membre, assignment, cycle)
        lien = reminder_service.build_whatsapp_link(membre, message)
        reminder_service.record_reminder(cycle, membre, current_user.id)
        return redirect(lien)

    @app.route("/gerant/relances")
    @login_required
    def manager_relances():
        manager_required()
        cycle = cycle_service.get_or_create_current_cycle(current_user.organization, current_user.id)
        concernes = statistics_service.get_attention_list(cycle) if cycle else []
        apercus = {}
        if cycle:
            for item in concernes:
                apercus[item["assignment"].id] = reminder_service.build_whatsapp_message(
                    item["membre"], item["assignment"], cycle
                )
        return render_template(
            "relances.html", config=Config, cycle=cycle, concernes=concernes, apercus=apercus,
        )

    @app.route("/gerant/historique")
    @login_required
    def manager_history():
        manager_required()
        cycles = Cycle.query.filter(
            Cycle.statut != "actif", Cycle.organization_id == current_user.organization_id
        ).order_by(Cycle.date_debut.desc()).all()
        historique = [statistics_service.get_history_stats(c, Config.TOTAL_HIZB) for c in cycles]
        stats_globales = statistics_service.get_global_statistics(current_user.organization_id)
        return render_template(
            "history.html", config=Config, historique=historique, stats=stats_globales,
        )

    # ---------------------------------------------------------------------
    # COMMANDES CLI (initialisation)
    # ---------------------------------------------------------------------
    @app.cli.command("init-db")
    def init_db():
        """Crée les tables de la base de données."""
        db.create_all()
        click.echo("Base de données initialisée.")

    @app.cli.command("seed-manager")
    @click.argument("prenom")
    @click.argument("nom")
    @click.argument("whatsapp")
    @click.argument("password")
    @click.argument("nom_amicale", required=False)
    def seed_manager(prenom, nom, whatsapp, password, nom_amicale):
        """Crée un compte gérant (et son amicale si elle n'existe pas). Exemple :
        flask seed-manager Amadou Diop +221771234567 monmotdepasse "Mon Amicale"
        """
        whatsapp = normalize_whatsapp(whatsapp)
        if Member.query.filter_by(whatsapp=whatsapp).first():
            click.echo("Ce numéro existe déjà.")
            return

        amicale = None
        if nom_amicale:
            amicale = Organization.query.filter_by(nom=nom_amicale).first()
        if not amicale:
            amicale = Organization.query.first()
        if not amicale:
            amicale = Organization(nom=nom_amicale or "Mon amicale")
            db.session.add(amicale)
            db.session.flush()

        gerant = Member(organization_id=amicale.id, prenom=prenom, nom=nom,
                         whatsapp=whatsapp, role="manager")
        gerant.set_password(password)
        db.session.add(gerant)
        db.session.commit()
        click.echo(f"Gérant {gerant.full_name} créé pour l'amicale « {amicale.nom} ».")

    @app.cli.command("import-members")
    @click.argument("fichier_csv")
    @click.argument("whatsapp_gerant")
    def import_members(fichier_csv, whatsapp_gerant):
        """Importe plusieurs membres d'un coup depuis un fichier CSV, dans
        l'amicale du gérant indiqué.

        Le fichier doit avoir les colonnes : prenom,nom,whatsapp,email (email optionnel).
        Exemple : flask import-members membres.csv +221771234567
        """
        import csv as csv_module

        if not os.path.exists(fichier_csv):
            click.echo(f"Fichier introuvable : {fichier_csv}")
            return

        gerant = Member.query.filter_by(whatsapp=normalize_whatsapp(whatsapp_gerant)).first()
        if not gerant:
            click.echo("Gérant introuvable pour ce numéro.")
            return
        organization_id = gerant.organization_id

        crees, ignores = 0, 0
        with open(fichier_csv, newline="", encoding="utf-8-sig") as f:
            lecteur = csv_module.DictReader(f)
            for ligne in lecteur:
                prenom = (ligne.get("prenom") or "").strip()
                nom = (ligne.get("nom") or "").strip()
                whatsapp = normalize_whatsapp(ligne.get("whatsapp") or "")
                email = (ligne.get("email") or "").strip() or None

                if not prenom or not nom or not whatsapp:
                    click.echo(f"Ligne ignoree (donnees manquantes) : {ligne}")
                    ignores += 1
                    continue

                if Member.query.filter_by(whatsapp=whatsapp).first():
                    click.echo(f"Deja existant, ignore : {prenom} {nom} ({whatsapp})")
                    ignores += 1
                    continue

                membre = Member(organization_id=organization_id, prenom=prenom, nom=nom,
                                 whatsapp=whatsapp, email=email, role="member")
                membre.set_password("taysir123")
                db.session.add(membre)
                crees += 1

        db.session.commit()
        click.echo(f"Termine : {crees} membre(s) cree(s), {ignores} ignore(s).")
        click.echo("Mot de passe par defaut de tous les nouveaux membres : taysir123")

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app = create_app()
    app.run(host="0.0.0.0", port=port, debug=False)

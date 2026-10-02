# تيسير العسير — AERTM

Assistant numérique pour la gestion de la lecture collective hebdomadaire du Coran
(répartition des 30 أجزاء, confirmations, rappels, historique, statistiques).

## Installation

```bash
python3 -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## Initialisation de la base de données

```bash
export FLASK_APP=app:create_app
flask init-db
```

## Créer le premier compte gérant

Un compte gérant **par défaut** est créé automatiquement au premier démarrage
(local ou sur Render) :

- Numéro WhatsApp : `+221700000000`
- Mot de passe : `aertm2026`

**Change ce mot de passe dès ta première connexion**, via le menu
**Mon compte**. Tu peux aussi définir tes propres identifiants avant le tout
premier lancement, via les variables d'environnement `SEED_MANAGER_PRENOM`,
`SEED_MANAGER_NOM`, `SEED_MANAGER_WHATSAPP`, `SEED_MANAGER_PASSWORD` (voir
`DEPLOIEMENT.md` pour Render).

Pour créer un compte gérant supplémentaire en local, la commande CLI reste
disponible :

```bash
flask seed-manager Amadou Diop +221771234567 monmotdepasse
```

## Lancer l'application

```bash
flask run
# ou : python app.py
```

Ouvrez ensuite http://127.0.0.1:5000 et connectez-vous avec le compte gérant créé
ci-dessus. Depuis l'espace gérant : **Membres → Ajouter un membre**, puis
**Tableau de bord → Créer une nouvelle semaine** pour générer automatiquement la
répartition des أجزاء (1 par membre).

## Ce qui est déjà fonctionnel (V1)

- Base de données réelle (SQLite via SQLAlchemy) : `Member`, `Cycle`, `Assignment`,
  `Confirmation`, `Reminder`, `ActivityLog` — aucune donnée n'est codée en dur.
- Répartition automatique des 30 أجزاء (1 par membre) entre les membres actifs, avec
  vérification qu'un جزء ne soit jamais attribué à deux membres.
- Espace membre minimaliste : voir son attribution, confirmer sa lecture
  (écrit réellement en base, persiste après rafraîchissement).
- Espace gérant complet : tableau de bord avec progression réelle
  (X/Y membres, X/Y أجزاء), actions recommandées, filtres par statut, recherche.
- Statuts calculés dynamiquement : 🟢 Terminé, 🟠 En attente, 🔴 En retard,
  🟡 Confirmé après rappel.
- Rappels : génère un message WhatsApp adapté (doux / proche échéance / retard)
  et ouvre `wa.me` avec le numéro du membre ; le rappel est journalisé (pas de
  lecture automatique du groupe WhatsApp — impossible sans API officielle).
- Historique des cycles clôturés + statistiques globales (taux moyen, pas de
  classement individuel).
- Journal des actions (`ActivityLog`) pour tracer les modifications sensibles.
- Authentification par numéro WhatsApp + mot de passe (Flask-Login), séparation
  stricte des rôles membre / gérant.
- Protection CSRF (Flask-WTF) sur tous les formulaires — nécessaire puisque
  l'application est accessible publiquement une fois déployée.

## Pistes d'évolution (V2)

- Gestion des absences avec réattribution guidée (le service
  `reassign_member` existe déjà, il manque l'écran dédié).
- Écran de modification visuelle de la répartition (le service
  `update_assignment` existe déjà).
- Passage à PostgreSQL en production (changer `DATABASE_URL`, le code ORM ne
  change pas).
- Export CSV/PDF de l'historique.
- Notifications programmées (cron / Celery) au lieu du déclenchement manuel du
  rappel WhatsApp.

## Structure

```
taysir_alasir/
├── app.py                  # Routes Flask
├── config.py
├── database.py
├── models.py                # Entités : Member, Cycle, Assignment, Confirmation, Reminder, ActivityLog
├── services/
│   ├── cycle_service.py       # Création de cycle, répartition, validation
│   ├── assignment_service.py  # Attribution, modification et vérification des أجزاء
│   ├── reminder_service.py    # Messages et liens WhatsApp, journalisation
│   └── statistics_service.py  # Progression, statuts, dashboard, historique
├── templates/
└── static/
```

## Nouvelles fonctionnalités (v2)

- **Cycle automatique Vendredi → Jeudi** : plus besoin de créer chaque semaine
  manuellement. Désactivable dans **Paramètres** si besoin.
- **Statut "Pas encore terminé"** : un membre peut signaler explicitement
  qu'il n'a pas fini, distinct du silence total.
- **Page Relances** groupant tous les membres à contacter (en retard, pas
  encore terminé, aucune confirmation), avec message pré-rempli et modifiable
  avant l'envoi WhatsApp.
- **Message de rappel personnalisable** (menu Paramètres), avec variables
  `{prenom}` `{hizb}` `{semaine}` `{date_debut}` `{date_fin}`.
- **Ajout rapide de plusieurs membres** en une fois (liste collée, une
  personne par ligne) depuis la page Membres.
- **Fiche détaillée d'un membre** avec documents Google Drive liés (nom + lien).

## Multi-amicales (v3)

L'application est désormais une plateforme : plusieurs amicales peuvent
l'utiliser en même temps, chacune avec :

- ses propres membres, cycles, attributions, confirmations et historique ;
- son propre nom et son propre logo (page **Créer une amicale**, accessible
  depuis la page de connexion) ;
- ses propres paramètres (cycle automatique, modèle de message de rappel).

Les données d'une amicale ne sont jamais visibles par une autre. La
connexion (numéro WhatsApp + mot de passe) reste unique sur toute la
plateforme : une fois connecté, on accède automatiquement à sa propre amicale.

**Installations existantes** : au premier démarrage après cette mise à jour,
une migration automatique crée une amicale par défaut et y rattache toutes
les données déjà présentes (membres, cycles, historique) — rien n'est perdu.
Le logo déjà utilisé est repris automatiquement si possible. Renomme
l'amicale et change son logo à volonté depuis **Paramètres**.

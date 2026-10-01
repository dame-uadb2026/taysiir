# Déployer تيسير العسير sur Render (avec GitHub + Neon)

Render (gratuit) n'a pas de disque persistant : SQLite serait donc effacé à
chaque redémarrage. On utilise donc une vraie base PostgreSQL gratuite et
permanente via **Neon**, et Render pour héberger l'application Flask.

## Étape 1 — Mettre le projet sur GitHub

1. Crée un nouveau dépôt sur https://github.com/new (par exemple `taysir-alasir`).
2. Dans le dossier du projet, en local :
   ```bash
   git init
   git add .
   git commit -m "Premiere version"
   git branch -M main
   git remote add origin https://github.com/TON-COMPTE/taysir-alasir.git
   git push -u origin main
   ```

## Étape 2 — Créer la base de données (Neon, gratuit et permanent)

1. Va sur https://neon.tech et crée un compte (gratuit).
2. Crée un nouveau projet Postgres.
3. Copie la **chaîne de connexion** proposée (elle commence par
   `postgresql://...`). Garde-la de côté, tu en auras besoin à l'étape 4.

## Étape 3 — Créer le service Web sur Render

1. Va sur https://render.com et connecte-toi avec GitHub.
2. Clique sur **New +** → **Web Service**.
3. Sélectionne ton dépôt `taysir-alasir`.
4. Render doit détecter le fichier `render.yaml` et proposer de créer le
   service automatiquement (option "Apply"). Sinon, configure manuellement :
   - **Build Command** : `pip install -r requirements-prod.txt`
   - **Start Command** : `gunicorn wsgi:app`
   - **Plan** : Free

## Étape 4 — Configurer les variables d'environnement (optionnel)

L'application fonctionne **dès le déploiement**, même sans configurer les
variables ci-dessous : un compte gérant par défaut est créé automatiquement
(numéro `+221700000000`, mot de passe `aertm2026`). **Change ce mot de passe
dès ta première connexion**, via le menu "Mon compte".

Si tu préfères définir tes propres identifiants dès le départ, ajoute ces
variables dans l'onglet **Environment** du service Render avant le premier
déploiement :

| Variable | Valeur |
|---|---|
| `SECRET_KEY` | une valeur aléatoire (Render peut la générer automatiquement) |
| `DATABASE_URL` | la chaîne de connexion Neon copiée à l'étape 2 |
| `SEED_MANAGER_PRENOM` | ton prénom (ex: `Amadou`) |
| `SEED_MANAGER_NOM` | ton nom (ex: `Diop`) |
| `SEED_MANAGER_WHATSAPP` | ton numéro (ex: `+221771234567`) |
| `SEED_MANAGER_PASSWORD` | le mot de passe que tu veux utiliser |

Dans tous les cas, `DATABASE_URL` doit être configurée avec la chaîne Neon de
l'étape 2, sinon l'application utilisera une base SQLite qui sera effacée à
chaque redémarrage.

## Étape 5 — Déployer

Clique sur **Create Web Service** (ou **Deploy**). Render installe les
dépendances, lance `gunicorn`, crée les tables et ton compte gérant
automatiquement. Au bout de 1 à 2 minutes, une URL du type
`https://taysir-alasir.onrender.com` est disponible.

Connecte-toi avec le numéro WhatsApp et le mot de passe définis à l'étape 4.

## À savoir sur le plan gratuit Render

- Le service **se met en veille après 15 minutes d'inactivité** ; la première
  requête suivante prend environ 1 minute à répondre (normal, pas un bug).
- 750 heures gratuites par mois, largement suffisant pour un usage
  hebdomadaire par une amicale.
- La base Neon (gratuite) est permanente, contrairement à la base Postgres
  gratuite de Render qui expire après 30 jours — c'est pour ça qu'on utilise
  Neon plutôt que la base Render.

## Mettre à jour l'application après une modification

```bash
git add .
git commit -m "Description du changement"
git push
```

Render redéploie automatiquement à chaque `push` sur `main`.

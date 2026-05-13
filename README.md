# ❄️ Snowflake Agentic AI

Système d'agents IA autonomes connectés à Snowflake — **Text-to-SQL**, **analyse de données**, **ingestion automatique** et **orchestration multi-agents** via Google Gemini.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│           Streamlit UI (port 8501)           │
│   💬 Chat Data │ 📥 Ingestion │ 📊 Explorer  │
└──────────────────────┬──────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────┐
│           FastAPI REST API (port 8000)       │
│  /ask  /ingest  /tables  /history  /health  │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│                 Orchestrator                 │
│         (classification d'intention)         │
└──────┬──────────────┬───────────────┬───────┘
       │              │               │
┌──────▼───┐   ┌──────▼──────┐  ┌────▼──────┐
│ SQLAgent │   │AnalystAgent │  │Ingestion  │
│Text-to-  │   │ Insights +  │  │Agent      │
│SQL auto- │   │ Plotly code │  │CSV / API  │
│correction│   └──────┬──────┘  └────┬──────┘
└──────┬───┘          │              │
       └──────────────┼──────────────┘
                      │
┌─────────────────────▼──────────────────────┐
│              Snowflake                      │
│  AGENTIC_DB / RAW / ANALYTICS               │
│  CUSTOMERS │ PRODUCTS │ SALES               │
└────────────────────────────────────────────┘
```

---

## Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| **Text-to-SQL** | Pose une question en français → SQL Snowflake généré et exécuté automatiquement |
| **Auto-correction** | Si le SQL échoue, l'agent analyse l'erreur et corrige (jusqu'à 3 essais) |
| **Analyse IA** | L'agent analyste génère des insights, tendances et code Plotly |
| **Ingestion CSV** | Upload d'un fichier CSV → détection schéma → création table → insertion |
| **Ingestion API** | URL JSON externe → même pipeline d'ingestion automatique |
| **Mémoire sémantique** | ChromaDB stocke les interactions pour contextualisation future |
| **Historique** | Toutes les questions/réponses loggées en JSON local |
| **Explorer SQL** | Interface pour requêtes SQL libres avec export CSV |

---

## Prérequis

- **Python 3.11** (recommandé — Snowpark non compatible Python 3.13)
- **Compte Snowflake** actif (tier gratuit suffisant)
- **Clé API Google** depuis [aistudio.google.com](https://aistudio.google.com) ← obligatoire (pas Google Cloud Console)

---

## Installation

```bash
# 1. Cloner le projet
git clone <repo-url>
cd snowflake-agentic-ai

# 2. Créer l'environnement virtuel Python 3.11
py -3.11 -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Installer le projet en mode éditable
pip install -e .

# 5. Configurer les variables d'environnement
copy .env.example .env   # Windows
cp .env.example .env     # macOS/Linux
# → Éditer .env avec vos credentials
```

---

## Configuration

Édite le fichier `.env` (ne jamais committer ce fichier) :

```env
# Snowflake
SNOWFLAKE_ACCOUNT=abc12345.us-east-1   # Format : orgname-accountname
SNOWFLAKE_USER=mon_utilisateur
SNOWFLAKE_PASSWORD=mon_mot_de_passe
SNOWFLAKE_DATABASE=AGENTIC_DB
SNOWFLAKE_SCHEMA=RAW
SNOWFLAKE_WAREHOUSE=AGENTIC_WH
SNOWFLAKE_ROLE=AGENTIC_ROLE

# Google Gemini — clé depuis aistudio.google.com
GOOGLE_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-2.0-flash
```

### Trouver son SNOWFLAKE_ACCOUNT

Dans l'URL Snowflake `https://abc12345.us-east-1.snowflakecomputing.com` → l'account est `abc12345.us-east-1`.

### Obtenir une clé Google gratuite

1. Aller sur [aistudio.google.com](https://aistudio.google.com)
2. Cliquer **"Get API key"** → **"Create API key"**
3. Quota gratuit : **15 requêtes/minute**, **1 million de tokens/jour**

> ⚠️ Une clé créée depuis Google Cloud Console (console.cloud.google.com) n'a pas de quota gratuit.

---

## Setup Snowflake (une seule fois)

Dans Snowflake UI → **Worksheets**, exécuter dans l'ordre :

```sql
-- 1. Créer database, schemas, warehouse, rôle, tables, vues
-- Contenu de : infra/snowflake_setup.sql

-- 2. Insérer les données de test (30 clients, 25 produits, 60 ventes)
-- Contenu de : infra/sample_data.sql
```

> Connexion requise en tant qu'**ACCOUNTADMIN** pour le premier script.

---

## Lancement

```bash
# Terminal 1 — API REST
py -3.11 -m uvicorn src.api.main:app --reload --port 8000

# Terminal 2 — Interface Streamlit
py -3.11 -m streamlit run src/ui/app.py
```

- **Interface** : http://localhost:8501
- **API docs** : http://localhost:8000/docs
- **API redoc** : http://localhost:8000/redoc

---

## API REST

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Statut connexion Snowflake |
| `POST` | `/ask` | Question en langage naturel |
| `POST` | `/ingest/csv` | Upload et ingestion d'un fichier CSV |
| `POST` | `/ingest/url` | Ingestion depuis une URL API JSON |
| `GET` | `/tables?schema=RAW` | Liste des tables d'un schéma |
| `GET` | `/tables/{schema}/{table}/schema` | Schéma d'une table |
| `GET` | `/history?limit=20` | Historique des interactions |
| `POST` | `/sql` | Exécution SQL directe |

### Exemples cURL

```bash
# Poser une question
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Quels sont les 5 clients qui ont le plus dépensé ?"}'

# Vérifier la santé
curl http://localhost:8000/health

# Lister les tables
curl http://localhost:8000/tables?schema=RAW
```

---

## Exemples de questions

Dans l'onglet **💬 Chat Data** de l'interface :

```
Quels sont les 5 clients avec le plus de commandes ?
Quel est le CA total par catégorie de produit ?
Quels produits ont un stock inférieur à 50 unités ?
Donne-moi l'évolution mensuelle des ventes en 2024
Quels clients Premium n'ont pas commandé depuis 60 jours ?
Quel est le produit le plus rentable (marge la plus élevée) ?
```

---

## Structure du projet

```
snowflake-agentic-ai/
├── .env                      ← Variables d'environnement (gitignore)
├── .env.example              ← Template de configuration
├── .gitignore
├── CLAUDE.md                 ← Guide pour Claude Code
├── README.md
├── requirements.txt
├── setup.py
│
├── infra/
│   ├── snowflake_setup.sql   ← DDL : database, schemas, warehouse, rôle, tables, vues
│   └── sample_data.sql       ← Données de test (30 clients, 25 produits, 60 ventes)
│
├── src/
│   ├── config.py             ← Singleton settings (pydantic-settings)
│   ├── snowflake_client.py   ← Client Snowflake thread-safe avec retry
│   │
│   ├── agents/
│   │   ├── base_agent.py     ← Boucle Gemini agentique (max 15 itérations)
│   │   ├── sql_agent.py      ← Text-to-SQL + enrichissement schéma + auto-correction
│   │   ├── analyst_agent.py  ← Insights Markdown + code Plotly
│   │   ├── ingestion_agent.py← CSV/API → DDL → INSERT batch 1000 lignes
│   │   └── orchestrator.py   ← Classification intention + routage + chaînage agents
│   │
│   ├── tools/
│   │   ├── snowflake_tools.py← execute_sql, get_table_schema, list_tables
│   │   ├── data_tools.py     ← fetch_csv, call_external_api
│   │   └── memory_tools.py   ← ChromaDB + JSON state + historique
│   │
│   ├── api/
│   │   ├── main.py           ← FastAPI app + CORS + lifespan
│   │   └── routes.py         ← Tous les endpoints REST
│   │
│   └── ui/
│       └── app.py            ← Interface Streamlit 3 onglets
│
└── tests/
    ├── test_snowflake.py     ← Tests connexion et requêtes (nécessite Snowflake)
    └── test_agents.py        ← Tests agents avec mocks Gemini et Snowflake
```

---

## Tests

```bash
# Tous les tests
py -3.11 -m pytest tests/ -v

# Tests agents uniquement (pas besoin de Snowflake)
py -3.11 -m pytest tests/test_agents.py -v

# Tests Snowflake (nécessite .env configuré)
py -3.11 -m pytest tests/test_snowflake.py -v
```

---

## Dépannage

### ❌ Non connecté (Snowflake)

```
Role 'AGENTIC_ROLE' is not granted to this user
```
→ Exécuter dans Snowflake en tant qu'ACCOUNTADMIN :
```sql
GRANT ROLE AGENTIC_ROLE TO USER <votre_user>;
```

### ❌ 429 RESOURCE_EXHAUSTED (Gemini)

```
limit: 0, model: gemini-2.0-flash
```
→ Ta clé vient de Google Cloud Console (pas de quota gratuit).
Crée une nouvelle clé sur [aistudio.google.com](https://aistudio.google.com).

### ❌ ModuleNotFoundError: No module named 'google'

→ Tu utilises `python` (3.13) au lieu de `py -3.11`. Les packages sont installés pour Python 3.11 :
```bash
py -3.11 -m uvicorn src.api.main:app --reload --port 8000
```

### ❌ ValidationError: Extra inputs are not permitted

→ Ajouter `"extra": "ignore"` dans le `model_config` de chaque classe `BaseSettings` dans `src/config.py`.

---

## Technologies utilisées

| Technologie | Version | Rôle |
|---|---|---|
| Python | 3.11 | Runtime |
| google-genai | 1.16.0 | LLM (Gemini) |
| snowflake-connector-python | 4.5.0 | Connexion Snowflake |
| chromadb | 0.6.3 | Mémoire sémantique vectorielle |
| fastapi | 0.115.6 | API REST |
| uvicorn | 0.32.1 | Serveur ASGI |
| streamlit | 1.41.1 | Interface utilisateur |
| pandas | 2.2.3 | Manipulation de données |
| pydantic-settings | 2.7.0 | Gestion configuration |
| tenacity | 9.0.0 | Retry automatique |

---

## Licence

MIT

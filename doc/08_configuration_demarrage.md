# 08 — Configuration et démarrage

## Le fichier `.env`

C'est le seul fichier que tu dois créer manuellement à la racine du projet. Il contient toutes les clés secrètes.

```bash
# ──────────────────────────────────────────
# SNOWFLAKE
# ──────────────────────────────────────────
SNOWFLAKE_ACCOUNT=abc12345.us-east-1
# Format : identifiant_compte.region
# PAS l'URL complète ! PAS "abc12345.us-east-1.snowflakecomputing.com"
# Juste "abc12345.us-east-1"

SNOWFLAKE_USER=mon_utilisateur
SNOWFLAKE_PASSWORD=mon_mot_de_passe

SNOWFLAKE_DATABASE=AGENTIC_DB
SNOWFLAKE_SCHEMA=RAW
SNOWFLAKE_WAREHOUSE=AGENTIC_WH
SNOWFLAKE_ROLE=AGENTIC_ROLE

# ──────────────────────────────────────────
# GOOGLE AI
# ──────────────────────────────────────────
GOOGLE_API_KEY=AIza...
# IMPORTANT : prend la clé sur aistudio.google.com (PAS Google Cloud Console)
# La clé Google Cloud n'a pas le quota gratuit de 15 req/min

GEMINI_MODEL=gemini-2.0-flash

# ──────────────────────────────────────────
# APP (optionnel — valeurs par défaut utilisées si absent)
# ──────────────────────────────────────────
APP_ENV=development
LOG_LEVEL=INFO
API_PORT=8000
UI_PORT=8501
CHROMA_PERSIST_DIR=./data/chroma
AGENT_STATE_DIR=./data/agent_states
```

---

## Comment trouver ton SNOWFLAKE_ACCOUNT

1. Connecte-toi sur app.snowflake.com
2. En bas à gauche, clique sur ton nom de compte
3. Tu vois quelque chose comme `abc12345.us-east-1`
4. C'est exactement ça que tu mets dans `SNOWFLAKE_ACCOUNT`

---

## Comment obtenir la clé Google AI

1. Va sur **aistudio.google.com** (pas console.cloud.google.com)
2. Clique "Get API Key" → "Create API key"
3. Copie la clé (commence par `AIza`)
4. Mets-la dans `GOOGLE_API_KEY`

Le quota gratuit : **15 requêtes/minute**, ce qui est suffisant pour un usage normal.

---

## Setup Snowflake (à faire une seule fois)

Si tu pars de zéro, voici le SQL à exécuter dans Snowflake avec un rôle ACCOUNTADMIN :

```sql
-- Créer le warehouse
CREATE WAREHOUSE IF NOT EXISTS AGENTIC_WH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE;

-- Créer la base de données
CREATE DATABASE IF NOT EXISTS AGENTIC_DB;

-- Créer les schémas
CREATE SCHEMA IF NOT EXISTS AGENTIC_DB.RAW;
CREATE SCHEMA IF NOT EXISTS AGENTIC_DB.ANALYTICS;

-- Créer le rôle
CREATE ROLE IF NOT EXISTS AGENTIC_ROLE;

-- Donner les droits au rôle
GRANT USAGE ON WAREHOUSE AGENTIC_WH TO ROLE AGENTIC_ROLE;
GRANT USAGE ON DATABASE AGENTIC_DB TO ROLE AGENTIC_ROLE;
GRANT ALL ON SCHEMA AGENTIC_DB.RAW TO ROLE AGENTIC_ROLE;
GRANT ALL ON SCHEMA AGENTIC_DB.ANALYTICS TO ROLE AGENTIC_ROLE;
GRANT ALL ON ALL TABLES IN SCHEMA AGENTIC_DB.RAW TO ROLE AGENTIC_ROLE;
GRANT ALL ON FUTURE TABLES IN SCHEMA AGENTIC_DB.RAW TO ROLE AGENTIC_ROLE;

-- Assigner le rôle à ton utilisateur
GRANT ROLE AGENTIC_ROLE TO USER ton_utilisateur;

-- Créer les tables de données
USE SCHEMA AGENTIC_DB.RAW;

CREATE TABLE IF NOT EXISTS CUSTOMERS (
    CUSTOMER_ID NUMBER PRIMARY KEY,
    FIRST_NAME VARCHAR(100),
    LAST_NAME VARCHAR(100),
    EMAIL VARCHAR(200),
    SEGMENT VARCHAR(50),
    CITY VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS PRODUCTS (
    PRODUCT_ID NUMBER PRIMARY KEY,
    PRODUCT_NAME VARCHAR(200),
    CATEGORY VARCHAR(100),
    UNIT_PRICE NUMBER(10,2),
    STOCK_QTY NUMBER
);

CREATE TABLE IF NOT EXISTS SALES (
    SALE_ID NUMBER PRIMARY KEY,
    CUSTOMER_ID NUMBER,
    PRODUCT_ID NUMBER,
    QUANTITY NUMBER,
    TOTAL_AMOUNT NUMBER(12,2),
    SALE_DATE DATE,
    CHANNEL VARCHAR(50),
    STATUS VARCHAR(50)
);

-- Vues analytiques
USE SCHEMA AGENTIC_DB.ANALYTICS;

CREATE OR REPLACE VIEW SALES_SUMMARY AS
    SELECT
        s.SALE_DATE,
        p.CATEGORY,
        COUNT(*) AS NB_TRANSACTIONS,
        SUM(s.TOTAL_AMOUNT) AS TOTAL_REVENUE
    FROM AGENTIC_DB.RAW.SALES s
    JOIN AGENTIC_DB.RAW.PRODUCTS p ON s.PRODUCT_ID = p.PRODUCT_ID
    GROUP BY 1, 2;

CREATE OR REPLACE VIEW CUSTOMER_LTV AS
    SELECT
        c.CUSTOMER_ID,
        c.FIRST_NAME || ' ' || c.LAST_NAME AS FULL_NAME,
        c.SEGMENT,
        SUM(s.TOTAL_AMOUNT) AS LIFETIME_VALUE
    FROM AGENTIC_DB.RAW.CUSTOMERS c
    LEFT JOIN AGENTIC_DB.RAW.SALES s ON c.CUSTOMER_ID = s.CUSTOMER_ID
    GROUP BY 1, 2, 3;
```

---

## Installation Python

```bash
# Vérifier la version Python disponible
py -3.11 --version
# Doit afficher : Python 3.11.x

# Créer un environnement virtuel
py -3.11 -m venv .venv

# Activer l'environnement (PowerShell Windows)
.venv\Scripts\Activate.ps1

# Installer les dépendances
py -3.11 -m pip install -r requirements.txt
```

### Pourquoi `py -3.11` et pas `python` ?

Sur cette machine, `python` pointe vers Python 3.13. Or `snowflake-connector-python` n'est pas encore compatible Python 3.13. On spécifie donc explicitement `py -3.11`.

---

## Vérifier que tout fonctionne

```bash
# 1. Vérifier la config (lit le .env)
py -3.11 -c "from src.config import settings; print('Account:', settings.snowflake.account)"

# 2. Vérifier la connexion Snowflake
py -3.11 -c "from src.snowflake_client import get_client; c = get_client(); print('Connecté:', c.is_healthy())"

# 3. Lancer les tests
py -3.11 -m pytest tests/ -v
```

---

## Lancer l'application

### UI Streamlit (recommandée)

```bash
py -3.11 -m streamlit run src/ui/app.py
# → http://localhost:8501
```

### API FastAPI

```bash
py -3.11 -m uvicorn src.api.main:app --reload --port 8000
# → http://localhost:8000
# → http://localhost:8000/docs (Swagger UI)
```

`--reload` fait que le serveur redémarre automatiquement quand tu modifies un fichier Python (mode développement uniquement).

---

## Variables d'environnement — correspondance complète

| Variable .env | Classe Python | Valeur par défaut |
|---|---|---|
| `SNOWFLAKE_ACCOUNT` | `settings.snowflake.account` | (obligatoire) |
| `SNOWFLAKE_USER` | `settings.snowflake.user` | (obligatoire) |
| `SNOWFLAKE_PASSWORD` | `settings.snowflake.password` | (obligatoire) |
| `SNOWFLAKE_DATABASE` | `settings.snowflake.database` | `AGENTIC_DB` |
| `SNOWFLAKE_SCHEMA` | `settings.snowflake.schema_` | `RAW` |
| `SNOWFLAKE_WAREHOUSE` | `settings.snowflake.warehouse` | `AGENTIC_WH` |
| `SNOWFLAKE_ROLE` | `settings.snowflake.role` | `AGENTIC_ROLE` |
| `GOOGLE_API_KEY` | `settings.google.api_key` | (obligatoire) |
| `GEMINI_MODEL` | `settings.google.model` | `gemini-2.0-flash` |
| `APP_ENV` | `settings.app.env` | `development` |
| `LOG_LEVEL` | `settings.app.log_level` | `INFO` |
| `API_PORT` | `settings.app.api_port` | `8000` |
| `UI_PORT` | `settings.app.ui_port` | `8501` |
| `CHROMA_PERSIST_DIR` | `settings.app.chroma_persist_dir` | `./data/chroma` |
| `AGENT_STATE_DIR` | `settings.app.agent_state_dir` | `./data/agent_states` |

---

## Erreurs courantes et solutions

| Erreur | Cause | Solution |
|---|---|---|
| `ValidationError: SNOWFLAKE_ACCOUNT missing` | Le `.env` n'est pas chargé | Vérifier que `.env` existe à la racine |
| `250001: Failed to connect to DB` | Mauvais format d'account | Utiliser `abc12345.us-east-1` (sans `.snowflakecomputing.com`) |
| `Role AGENTIC_ROLE not found` | Le rôle n'a pas été granted | Exécuter le SQL de setup sous ACCOUNTADMIN |
| `google.api_core.exceptions.PermissionDenied` | Mauvaise clé Google | Utiliser aistudio.google.com, pas Google Cloud |
| `ModuleNotFoundError: No module named 'src'` | Script lancé depuis le mauvais dossier | Se mettre à la racine du projet |
| `extra fields not allowed` | `extra="ignore"` manquant | Ajouter à chaque `BaseSettings` |

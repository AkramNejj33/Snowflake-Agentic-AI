# CLAUDE.md — Snowflake Agentic AI

## Vue d'ensemble

Système multi-agents IA connecté à Snowflake. Les agents utilisent Google Gemini (via `google-genai`) avec tool calling natif pour répondre à des questions en langage naturel, ingérer des données et produire des analyses.

## Stack technique

- **Python 3.11** (pas 3.13 — utiliser `py -3.11` sur cette machine)
- **LLM** : Google Gemini 2.0 Flash via `google-genai`
- **Backend data** : Snowflake (connector natif, pas Snowpark)
- **Mémoire** : ChromaDB (sémantique) + JSON (état agents + historique)
- **API** : FastAPI + Uvicorn port 8000
- **UI** : Streamlit port 8501

## Commandes essentielles

```bash
# API
py -3.11 -m uvicorn src.api.main:app --reload --port 8000

# UI
py -3.11 -m streamlit run src/ui/app.py

# Tests
py -3.11 -m pytest tests/ -v

# Vérifier imports
py -3.11 -c "from src.config import settings; print(settings.snowflake.account)"
```

## Architecture des agents

```
Orchestrator
├── SQLAgent       → Text-to-SQL + auto-correction (3 essais max)
├── AnalystAgent   → Insights Markdown + code Plotly
└── IngestionAgent → CSV/API → DDL Snowflake → INSERT batch 1000
```

Tous héritent de `BaseAgent` (`src/agents/base_agent.py`) qui gère la boucle Gemini :
- Max 15 itérations par `run()`
- Tool calls via `types.Content` / `types.Part` / `types.FunctionResponse`
- Les tools sont des **fonctions Python** passées directement à Gemini (pas de JSON schema)

## Fichiers critiques

| Fichier | Rôle |
|---------|------|
| `src/config.py` | Singleton `settings` — toujours `extra="ignore"` sur chaque BaseSettings |
| `src/snowflake_client.py` | Singleton thread-safe, retry via tenacity, 3 essais max |
| `src/agents/base_agent.py` | Boucle Gemini avec function calling |
| `src/tools/snowflake_tools.py` | `SNOWFLAKE_TOOL_FUNCTIONS` = liste de callables Python |
| `src/tools/memory_tools.py` | ChromaDB + JSON state + `MEMORY_TOOL_FUNCTIONS` |

## Schéma Snowflake

- **Database** : `AGENTIC_DB`
- **Schema RAW** : `CUSTOMERS`, `PRODUCTS`, `SALES`
- **Schema ANALYTICS** : vues `SALES_SUMMARY`, `CUSTOMER_LTV`
- **Warehouse** : `AGENTIC_WH` (X-SMALL, auto-suspend 60s)
- **Role** : `AGENTIC_ROLE` (doit être assigné à l'utilisateur)

## Variables d'environnement requises

```
SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
SNOWFLAKE_DATABASE=AGENTIC_DB, SNOWFLAKE_SCHEMA=RAW
SNOWFLAKE_WAREHOUSE=AGENTIC_WH, SNOWFLAKE_ROLE=AGENTIC_ROLE
GOOGLE_API_KEY   ← depuis aistudio.google.com (pas Google Cloud Console)
GEMINI_MODEL=gemini-2.0-flash
```

## Points d'attention

- La clé Google doit venir de **aistudio.google.com** pour avoir le quota gratuit (15 req/min)
- `SNOWFLAKE_ACCOUNT` format : `abc12345.us-east-1` (pas l'URL complète)
- Le rôle `AGENTIC_ROLE` doit être granted à l'utilisateur via ACCOUNTADMIN
- Les données de ChromaDB sont dans `data/chroma/` (gitignore)
- L'historique des interactions est dans `data/agent_states/interaction_history.json`

## Pièges connus

- Ne pas utiliser `python` seul sur cette machine (pointe vers 3.13), toujours `py -3.11`
- `pydantic_settings` : chaque `BaseSettings` doit avoir `"extra": "ignore"` sinon crash au démarrage
- Snowpark (`snowflake-snowpark-python`) n'est pas compatible Python 3.13 — retiré du projet
- Les tools Gemini sont des fonctions Python (pas des JSON schema Anthropic)

# 01 — Vue d'ensemble du projet

## C'est quoi ce projet ?

**Snowflake Agentic AI** est un système d'intelligence artificielle multi-agents qui te permet de parler à ta base de données Snowflake en **langage naturel** (français).

Au lieu d'écrire du SQL à la main, tu poses une question comme :
> "Quels sont les 5 clients qui ont dépensé le plus ce trimestre ?"

Et le système :
1. Comprend l'intention (question de données)
2. Génère le SQL correspondant
3. Exécute la requête sur Snowflake
4. Te répond en français avec les résultats + un tableau

---

## Cas d'usage concrets

| Ce que tu peux faire | Comment |
|---|---|
| Poser une question en français sur les données | Interface chat Streamlit |
| Demander une analyse avec graphiques | Même interface, le système détecte |
| Importer un fichier CSV dans Snowflake | Onglet "Ingestion" |
| Connecter une API externe et charger ses données | Onglet "Ingestion" |
| Explorer les tables Snowflake visuellement | Onglet "Explorer" |
| Intégrer via API REST | FastAPI sur le port 8000 |

---

## Stack technique résumée

| Composant | Technologie | Pourquoi ce choix |
|---|---|---|
| **LLM (cerveau)** | Google Gemini 2.0 Flash | Gratuit (15 req/min sur aistudio.google.com), puissant, supporte le function calling natif |
| **Base de données** | Snowflake | Data warehouse cloud scalable |
| **Mémoire sémantique** | ChromaDB | Base vectorielle locale pour chercher des souvenirs par sens |
| **Historique** | Fichier JSON | Simple, rapide, pas besoin de base SQL pour ça |
| **API REST** | FastAPI | Rapide, validation automatique, docs Swagger auto-générées |
| **Interface web** | Streamlit | Interface data en Python pur, très rapide à coder |
| **Python** | 3.11 | 3.13 n'est pas compatible avec snowflake-connector |

---

## Structure des dossiers

```
snowflake-agentic-ai/
│
├── src/                          ← Tout le code source
│   ├── config.py                 ← Singleton de configuration (lit le .env)
│   ├── snowflake_client.py       ← Client Snowflake thread-safe (singleton)
│   │
│   ├── agents/                   ← Les 4 agents IA
│   │   ├── base_agent.py         ← Classe abstraite : boucle Gemini générique
│   │   ├── orchestrator.py       ← Chef d'orchestre : classe l'intention, route
│   │   ├── sql_agent.py          ← Convertit questions → SQL → résultats
│   │   ├── analyst_agent.py      ← Génère insights Markdown + code Plotly
│   │   └── ingestion_agent.py    ← Charge CSV/API → DDL → INSERT Snowflake
│   │
│   ├── tools/                    ← Fonctions Python appelées par Gemini
│   │   ├── snowflake_tools.py    ← execute_sql, get_table_schema, list_tables
│   │   ├── memory_tools.py       ← save_memory, recall_memory + historique JSON
│   │   └── data_tools.py         ← fetch_csv, call_external_api
│   │
│   ├── api/                      ← API REST FastAPI
│   │   ├── main.py               ← App FastAPI + CORS + lifespan
│   │   └── routes.py             ← Tous les endpoints (/ask, /ingest, /tables…)
│   │
│   └── ui/                       ← Interface Streamlit
│       └── app.py                ← 3 onglets : Chat, Ingestion, Explorer
│
├── data/                         ← Données persistées (gitignorées)
│   ├── chroma/                   ← Base vectorielle ChromaDB
│   └── agent_states/             ← États agents + interaction_history.json
│
├── tests/                        ← Tests pytest
├── .env                          ← Variables d'environnement (NON committé)
├── requirements.txt              ← Dépendances Python
└── doc/                          ← Ce dossier de documentation
```

---

## Les 5 fichiers les plus importants

| Fichier | Ce qu'il fait | Pourquoi c'est critique |
|---|---|---|
| `src/config.py` | Lit le `.env`, crée le singleton `settings` | Tout le projet en dépend |
| `src/snowflake_client.py` | Connexion Snowflake singleton + retry | Sans lui, aucune requête ne fonctionne |
| `src/agents/base_agent.py` | Boucle Gemini avec tool calling | C'est le moteur de TOUS les agents |
| `src/agents/orchestrator.py` | Route les requêtes vers le bon agent | Point d'entrée unique du système |
| `src/tools/snowflake_tools.py` | `execute_sql`, `get_table_schema`, `list_tables` | Les "mains" du SQLAgent |

---

## Schéma Snowflake attendu

Le projet suppose que tu as créé ces objets dans Snowflake :

```
Database  : AGENTIC_DB
├── Schema RAW
│   ├── Table CUSTOMERS    (CUSTOMER_ID, FIRST_NAME, LAST_NAME, EMAIL, SEGMENT, CITY)
│   ├── Table PRODUCTS     (PRODUCT_ID, PRODUCT_NAME, CATEGORY, UNIT_PRICE, STOCK_QTY)
│   └── Table SALES        (SALE_ID, CUSTOMER_ID, PRODUCT_ID, QUANTITY, TOTAL_AMOUNT, SALE_DATE, CHANNEL, STATUS)
│
└── Schema ANALYTICS
    ├── View SALES_SUMMARY  (SALE_DATE, CATEGORY, NB_TRANSACTIONS, TOTAL_REVENUE)
    └── View CUSTOMER_LTV   (CUSTOMER_ID, FULL_NAME, SEGMENT, LIFETIME_VALUE)

Warehouse : AGENTIC_WH   (X-SMALL, auto-suspend 60s)
Role      : AGENTIC_ROLE  (doit être granted à ton user)
```

---

## Lancer le projet

```bash
# 1. Créer le .env avec tes credentials (voir doc/08_configuration.md)

# 2. Installer les dépendances
py -3.11 -m pip install -r requirements.txt

# 3. Lancer l'UI
py -3.11 -m streamlit run src/ui/app.py

# 4. (Optionnel) Lancer l'API
py -3.11 -m uvicorn src.api.main:app --reload --port 8000
```

---

Voir les autres fichiers de ce dossier pour les détails de chaque composant.

# 10 — Dépendances et leur rôle

Détail de chaque package dans `requirements.txt`.

---

## Connexion Snowflake

### `snowflake-connector-python==4.5.0`

Le connecteur officiel Snowflake. Il fournit :
- `snowflake.connector.connect()` — ouvre la connexion
- `DictCursor` — retourne les rows comme dicts `{"COL": value}`
- `ProgrammingError` — erreur SQL (syntaxe, table inexistante)
- `OperationalError` — erreur réseau/connexion

Note : Snowpark (l'autre client Snowflake plus puissant) a été retiré car incompatible Python 3.13.

---

## LLM

### `google-genai==1.16.0`

La librairie officielle Google pour Gemini. Elle fournit :
- `genai.Client` — client principal
- `client.models.generate_content()` — appel au modèle
- `types.GenerateContentConfig` — configuration (system prompt, temperature, tools)
- `types.Content` / `types.Part` — structure des messages
- `types.FunctionResponse` — réponse d'un outil à Gemini

---

## Base de données vectorielle

### `chromadb==0.6.3`

Base de données vectorielle locale. Elle fournit :
- `chromadb.PersistentClient` — client avec stockage sur disque
- `.get_or_create_collection()` — crée ou récupère une collection
- `.upsert()` — insert ou update
- `.query()` — recherche sémantique par similarité cosinus

ChromaDB utilise en interne un modèle d'embedding (sentence-transformers) pour convertir le texte en vecteurs.

---

## API REST

### `fastapi==0.115.6`

Framework web Python asynchrone. Il fournit :
- `FastAPI()` — application principale
- `APIRouter` — groupe d'endpoints
- `BaseModel` — modèles Pydantic pour valider les requêtes/réponses
- `@router.get()` / `@router.post()` — décorateurs d'endpoints
- Documentation Swagger auto-générée sur `/docs`

### `uvicorn[standard]==0.32.1`

Serveur ASGI (Asynchronous Server Gateway Interface) qui fait tourner FastAPI. Le `[standard]` installe des extras pour de meilleures performances (websockets, etc.).

```bash
py -3.11 -m uvicorn src.api.main:app --reload --port 8000
#                     ┬──────────────┬
#                     │              └─ L'objet FastAPI dans main.py
#                     └─ Module Python src/api/main.py
```

### `httpx==0.28.1`

Client HTTP asynchone/synchrone. Utilisé pour :
- `IngestionAgent.ingest_api()` — récupère des données depuis une URL
- `data_tools.call_external_api()` — appelle des APIs externes
- UI Streamlit — teste les APIs JSON

### `python-multipart==0.0.20`

Requis par FastAPI pour gérer l'upload de fichiers (`UploadFile`). Sans lui, `/ingest/csv` ne fonctionne pas.

---

## Interface utilisateur

### `streamlit==1.41.1`

Framework UI Python. Il fournit :
- `st.chat_input()` — zone de saisie style chat
- `st.chat_message()` — bulle de message
- `st.dataframe()` — tableau interactif
- `st.file_uploader()` — upload de fichiers
- `st.expander()` — section accordéon
- `st.session_state` — état persistant entre les reruns
- `@st.cache_resource` — cache pour les ressources (connexions, clients)
- `st.spinner()` — indicateur de chargement
- `st.download_button()` — bouton de téléchargement

---

## Manipulation de données

### `pandas==2.2.3`

La librairie data Python incontournable. Utilisée pour :
- Convertir les rows Snowflake en DataFrame (`pd.DataFrame(rows)`)
- Afficher les données dans Streamlit (`st.dataframe(df)`)
- Lire les CSV (`pd.read_csv()`)
- Normaliser les données avant insertion (`df.dtypes`, `df.columns`)

### `numpy==2.2.1`

Dépendance de pandas pour les calculs numériques. Utilisée indirectement.

---

## Utilitaires

### `python-dotenv==1.0.1`

Charge le fichier `.env` dans les variables d'environnement :
```python
load_dotenv(_root / ".env")
```

### `pydantic==2.10.4`

Validation de données Python. Utilisé pour :
- Valider les modèles de requêtes/réponses FastAPI (`BaseModel`)
- Typer et valider les settings

### `pydantic-settings==2.7.0`

Extension de Pydantic pour lire des settings depuis l'environnement :
```python
class SnowflakeSettings(BaseSettings):
    account: str = Field(..., alias="SNOWFLAKE_ACCOUNT")
```

### `tenacity==9.0.0`

Librairie de retry avec backoff exponentiel. Utilisée pour les retries Snowflake :
```python
@retry(
    retry=retry_if_exception_type(OperationalError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
)
```

---

## Tests

### `pytest==8.3.4`

Framework de tests Python.

### `pytest-asyncio==0.24.0`

Plugin pytest pour tester du code async (FastAPI utilise async).

### `pytest-mock==3.14.0`

Plugin pytest pour mocker des fonctions/classes dans les tests (`mocker.patch()`).

---

## Tableau récapitulatif

| Package | Catégorie | Qui l'utilise |
|---|---|---|
| snowflake-connector-python | Data | SnowflakeClient |
| google-genai | LLM | BaseAgent, Orchestrator |
| chromadb | Mémoire | memory_tools |
| fastapi | API | src/api/ |
| uvicorn | Serveur | CLI startup |
| httpx | HTTP | data_tools, ingestion_agent |
| python-multipart | Upload | FastAPI file upload |
| streamlit | UI | src/ui/ |
| pandas | Data | Tous les agents, UI |
| numpy | Calcul | pandas (indirect) |
| python-dotenv | Config | config.py |
| pydantic | Validation | config.py, routes.py |
| pydantic-settings | Config | config.py |
| tenacity | Retry | snowflake_client.py |
| pytest | Tests | tests/ |
| pytest-asyncio | Tests | tests/ |
| pytest-mock | Tests | tests/ |

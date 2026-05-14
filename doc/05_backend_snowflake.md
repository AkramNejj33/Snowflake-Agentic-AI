# 05 — Backend : FastAPI + Client Snowflake

## A. Le client Snowflake

**Fichier :** `src/snowflake_client.py`

### Pattern Singleton thread-safe

Il ne doit exister qu'**une seule connexion Snowflake** dans tout le processus. Le pattern Singleton garantit ça :

```python
class SnowflakeClient:
    _instance: "SnowflakeClient | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "SnowflakeClient":
        if cls._instance is None:
            with cls._lock:                  # Verrou pour thread safety
                if cls._instance is None:    # Double-check (évite race condition)
                    obj = object.__new__(cls)
                    obj._conn = None
                    cls._instance = obj
        return cls._instance
```

Peu importe combien de fois tu appelles `SnowflakeClient()` ou `get_client()`, tu récupères toujours la même instance.

Pourquoi c'est important ? Snowflake facture par connexion active. Avec un Singleton, on ouvre la connexion une fois et on la réutilise.

### Reconnexion automatique

La méthode `_ensure_connected()` est appelée avant chaque requête. Si la connexion est fermée (timeout, restart), elle se reconnecte :

```python
def _ensure_connected(self) -> None:
    if self._conn is None or self._conn.is_closed():
        self._connect()
```

### Les paramètres de connexion

```python
self._conn = snowflake.connector.connect(
    account=sf.account,      # "abc12345.us-east-1"
    user=sf.user,
    password=sf.password,
    database=sf.database,    # "AGENTIC_DB"
    schema=sf.schema_,       # "RAW"
    warehouse=sf.warehouse,  # "AGENTIC_WH"
    role=sf.role,            # "AGENTIC_ROLE"
    session_parameters={"QUERY_TAG": "agentic-ai"},  # Tag pour monitoring Snowflake
)
```

Le `QUERY_TAG` permet de retrouver dans Snowflake toutes les requêtes générées par ce système (dans Query History).

### Retry automatique avec Tenacity

```python
@retry(
    retry=retry_if_exception_type(OperationalError),  # Seulement sur erreurs réseau
    stop=stop_after_attempt(3),                         # Max 3 tentatives
    wait=wait_exponential(multiplier=1, min=1, max=8),  # Attente : 1s, 2s, 4s, 8s
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,  # Si toujours en échec, relance l'exception
)
def execute_query(self, sql: str, params=None) -> pd.DataFrame:
```

La distinction importante :
- `OperationalError` (erreur réseau, connexion coupée) → **retried**
- `ProgrammingError` (SQL invalide, table inexistante) → **pas retried** (inutile, le SQL est mauvais)

### `execute_query()` — Le cœur du client

```python
def execute_query(self, sql: str, params=None) -> pd.DataFrame:
    self._ensure_connected()
    with self._conn.cursor(DictCursor) as cur:  # DictCursor = rows comme dicts
        cur.execute(sql, params)
        rows = cur.fetchall()
        if rows:
            return pd.DataFrame(rows)   # Liste de dicts → DataFrame
        # DDL/DML : pas de rows retournées
        if cur.description:
            return pd.DataFrame(columns=[d.name for d in cur.description])
        return pd.DataFrame()           # Empty DataFrame
```

Le `DictCursor` fait que chaque row est un dict `{"COLUMN_NAME": value}` au lieu d'un tuple, ce qui permet de créer directement un DataFrame nommé.

### Introspection du schéma

`get_schema(table_name, schema)` interroge `INFORMATION_SCHEMA.COLUMNS` pour récupérer les métadonnées :

```sql
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, ...
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = %(schema)s
  AND TABLE_NAME = %(table)s
ORDER BY ORDINAL_POSITION
```

`list_tables(schema)` interroge `INFORMATION_SCHEMA.TABLES` :

```sql
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = %(schema)s
  AND TABLE_TYPE IN ('BASE TABLE', 'VIEW')
ORDER BY TABLE_NAME
```

`get_all_schemas_info(schemas)` combine les deux pour générer un texte formaté utilisable dans un prompt LLM :

```
Table: RAW.CUSTOMERS
  - CUSTOMER_ID (NUMBER, NOT NULL)
  - FIRST_NAME (VARCHAR, NULL)
  - EMAIL (VARCHAR, NULL)

Table: RAW.SALES
  - SALE_ID (NUMBER, NOT NULL)
  - CUSTOMER_ID (NUMBER, NULL)
  ...
```

---

## B. L'API FastAPI

**Fichiers :** `src/api/main.py` + `src/api/routes.py`

### Démarrage de l'application

```python
# main.py
app = FastAPI(
    title="Snowflake Agentic AI",
    docs_url="/docs",    # Swagger UI accessible sur http://localhost:8000/docs
    redoc_url="/redoc",  # ReDoc alternative
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
app.include_router(router)
```

Le **lifespan** gère les événements de démarrage/arrêt :

```python
@asynccontextmanager
async def lifespan(app):
    logger.info("Démarrage de l'API")
    yield                        # L'app tourne ici
    logger.info("Arrêt de l'API")
    get_client().close()         # Ferme proprement la connexion Snowflake
```

### Les endpoints

#### `GET /health` — Vérification de l'état

```
GET http://localhost:8000/health

Réponse :
{
    "status": "ok",
    "snowflake_connected": true,
    "database": "AGENTIC_DB",
    "warehouse": "AGENTIC_WH"
}
```

Utile pour monitorer si l'app est en vie et connectée à Snowflake.

#### `POST /ask` — Question en langage naturel

```
POST http://localhost:8000/ask
Content-Type: application/json

{
    "question": "Quels sont les 5 clients avec le plus de commandes ?",
    "with_analysis": false
}

Réponse :
{
    "intent": "sql_question",
    "question": "Quels sont les 5 clients...",
    "answer": "Les 5 clients les plus actifs sont...",
    "sql": "SELECT customer_id, COUNT(*) as nb FROM RAW.SALES GROUP BY 1 ORDER BY 2 DESC LIMIT 5",
    "data": [{"CUSTOMER_ID": 42, "NB": 87}, ...],
    "analysis": null,
    "error": null
}
```

Si `with_analysis: true`, le préfixe `[ANALYSE]` est ajouté pour forcer l'AnalystAgent :

```python
if request.with_analysis:
    user_input = f"[ANALYSE] {user_input}"
```

#### `POST /ingest/csv` — Upload CSV

```
POST http://localhost:8000/ingest/csv?table_name=MY_TABLE
Content-Type: multipart/form-data
file: [binary CSV content]
```

Le fichier est écrit dans un fichier temporaire, ingéré, puis le temp file est supprimé.

#### `POST /ingest/url` — Ingestion depuis une API

```
POST http://localhost:8000/ingest/url
{
    "url": "https://api.example.com/products",
    "table_name": "PRODUCTS_API",
    "json_key": "results"   // optionnel : extraire data["results"]
}
```

#### `GET /tables?schema=RAW` — Liste des tables

#### `GET /tables/{schema}/{table}/schema` — Schéma d'une table

#### `GET /history?limit=20` — Historique des interactions

#### `POST /sql` — SQL brut (pour debug)

```
POST http://localhost:8000/sql
{"query": "SELECT COUNT(*) FROM RAW.SALES"}
```

### Swagger UI automatique

FastAPI génère automatiquement une interface Swagger sur `http://localhost:8000/docs` où tu peux tester tous les endpoints depuis le navigateur.

### Singleton de l'Orchestrator dans l'API

L'API garde un seul Orchestrator pour toute la durée du processus (même logique que le Singleton Snowflake) :

```python
_orchestrator: Orchestrator | None = None

def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
```

---

## C. La configuration (`src/config.py`)

### Architecture en 3 groupes de settings

```python
class SnowflakeSettings(BaseSettings):  # Variables SNOWFLAKE_*
class GoogleSettings(BaseSettings):    # Variables GOOGLE_* / GEMINI_*
class AppSettings(BaseSettings):       # Variables APP_* + chemins data/

class Settings:                        # Agrège les 3
    def __init__(self):
        self.snowflake = SnowflakeSettings()
        self.google    = GoogleSettings()
        self.app       = AppSettings()
        # Crée les dossiers data/ au démarrage
        for d in [self.app.chroma_persist_dir, self.app.agent_state_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)

settings = Settings()  # Singleton module-level
```

### Le `extra="ignore"` obligatoire

```python
model_config = {"populate_by_name": True, "extra": "ignore", ...}
```

Si un fichier `.env` contient des variables non définies dans la classe (ex: tu as `DEBUG=true` mais pas de champ `debug` dans `AppSettings`), Pydantic plante sans `extra="ignore"`. Ce flag dit "ignore silencieusement les variables inconnues".

### Lecture du .env

```python
_root = Path(__file__).parent.parent  # Racine du projet
load_dotenv(_root / ".env")           # Charge le .env avant que Pydantic lise les variables
```

Pydantic Settings cherche les valeurs dans cet ordre :
1. Variables d'environnement système
2. Fichier `.env`
3. Valeurs par défaut dans `Field()`

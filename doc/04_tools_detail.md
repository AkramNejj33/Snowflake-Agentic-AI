# 04 — Les outils (Tools) — les "mains" des agents

## C'est quoi un "tool" dans ce projet ?

Un **tool** est une **fonction Python ordinaire** que Gemini peut décider d'appeler pendant la boucle agentique.

La grosse différence avec l'approche classique (ex: Anthropic/OpenAI) : ici, on passe **directement la fonction Python** à Gemini. Il lit automatiquement :
- Le nom de la fonction → nom de l'outil
- La docstring → description de ce que fait l'outil
- Les type hints des paramètres → types attendus
- Les `Args:` dans la docstring → description de chaque paramètre

```python
# Tu passes ça à Gemini :
def execute_sql(query: str) -> str:
    """Execute a SQL query on Snowflake.
    Args:
        query: Valid Snowflake SQL statement to execute.
    Returns:
        JSON string with keys: success, rows, row_count.
    """
    ...

# Gemini comprend automatiquement :
# - Outil "execute_sql" qui prend un paramètre string "query"
# - Description : "Execute a SQL query on Snowflake"
```

---

## Les 3 fichiers de tools

### `src/tools/snowflake_tools.py` — Outils du SQLAgent

#### `execute_sql(query: str) → str`

Exécute une requête SQL sur Snowflake et retourne les résultats.

```python
# Ce que Gemini envoie :
execute_sql(query="SELECT customer_id, COUNT(*) as nb FROM RAW.SALES GROUP BY 1 LIMIT 10")

# Ce que la fonction retourne (JSON string) :
{
    "success": true,
    "rows": [
        {"CUSTOMER_ID": 1, "NB": 42},
        {"CUSTOMER_ID": 7, "NB": 38}
    ],
    "row_count": 2
}

# Si erreur SQL :
{
    "success": false,
    "error": "SQL compilation error: table 'CUSTOMERS' does not exist"
}
```

La fonction gère automatiquement la conversion des types non-JSON-sérialisables (dates, Decimal) via `_json_safe()` :
- `datetime.date` → string ISO `"2024-01-15"`
- `decimal.Decimal` → `float`

#### `get_table_schema(table_name: str, schema: str = "RAW") → str`

Retourne les colonnes d'une table Snowflake. Utilisé par Gemini **avant** d'écrire une requête SQL pour vérifier les noms exacts des colonnes.

```python
get_table_schema(table_name="CUSTOMERS", schema="RAW")

# Retourne :
{
    "success": true,
    "table": "CUSTOMERS",
    "schema": "RAW",
    "columns": [
        {"name": "CUSTOMER_ID", "type": "NUMBER", "nullable": false},
        {"name": "FIRST_NAME", "type": "VARCHAR", "nullable": true},
        {"name": "EMAIL", "type": "VARCHAR", "nullable": true}
    ]
}
```

#### `list_tables(schema: str = "RAW") → str`

Liste toutes les tables d'un schéma. Utile quand Gemini ne sait pas quelle table chercher.

```python
list_tables(schema="ANALYTICS")

# Retourne :
{
    "success": true,
    "schema": "ANALYTICS",
    "tables": ["CUSTOMER_LTV", "SALES_SUMMARY"]
}
```

#### `SNOWFLAKE_TOOL_FUNCTIONS`

La liste passée à Gemini :
```python
SNOWFLAKE_TOOL_FUNCTIONS = [execute_sql, get_table_schema, list_tables]
```

#### `dispatch_snowflake_tool(tool_name, tool_input)` — Le routeur

Quand Gemini dit "appelle `execute_sql` avec `{"query": "..."}`", c'est `_execute_tool()` de SQLAgent qui appelle `dispatch_snowflake_tool()` :

```python
def dispatch_snowflake_tool(tool_name, tool_input):
    handlers = {
        "execute_sql":      lambda i: execute_sql(i["query"]),
        "get_table_schema": lambda i: get_table_schema(i["table_name"], i.get("schema", "RAW")),
        "list_tables":      lambda i: list_tables(i.get("schema", "RAW")),
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"})
    return handler(tool_input)
```

---

### `src/tools/memory_tools.py` — Outils mémoire + historique JSON

Ce fichier gère deux types de persistance :
1. **ChromaDB** — mémoire sémantique (embeddings vectoriels)
2. **JSON** — état des agents + historique des interactions

#### ChromaDB (mémoire sémantique)

ChromaDB est une **base de données vectorielle** locale. Quand tu sauvegardes du texte, ChromaDB le transforme en vecteur (embedding) et le stocke. Ensuite, quand tu cherches, ChromaDB trouve les textes **sémantiquement similaires** (pas juste par mots-clés).

**`save_to_memory(key, content, metadata)` (fonction interne)**
```python
save_to_memory(
    key="q_1234567890",
    content="Q: Quels sont les top clients ? A: Les 5 premiers sont...",
    metadata={"type": "interaction", "intent": "sql_question"}
)
```
Stocké dans `data/chroma/` (dossier local persistant).

**`search_memory(query, n_results)` (fonction interne)**
```python
results = search_memory("clients qui achètent le plus", n_results=3)
# Retourne les 3 interactions passées les plus proches sémantiquement
```

#### Fonctions outils exposées à Gemini

```python
def save_memory(key: str, content: str) -> str:
    """Save text content to semantic memory (ChromaDB) for future retrieval."""
    return save_to_memory(key, content)

def recall_memory(query: str, n_results: int = 5) -> str:
    """Search semantic memory for information relevant to the query."""
    return search_memory(query, n_results)

MEMORY_TOOL_FUNCTIONS = [save_memory, recall_memory]
```

AnalystAgent peut appeler ces outils pendant son analyse pour :
- Sauvegarder un insight important : `save_memory("insight_top_clients", "Les clients premium génèrent 73% du CA")`
- Rechercher des analyses passées : `recall_memory("tendance ventes Q3")` → retrouve les analyses similaires

#### Persistance JSON — historique des interactions

Chaque interaction est loggée dans `data/agent_states/interaction_history.json` :

```python
def save_interaction(question, answer, sql=None, agent="unknown"):
    entry = {
        "id": "uuid-...",
        "timestamp": "2024-01-15T14:30:00Z",
        "agent": "sql_question",
        "question": "Quels sont les top clients ?",
        "sql": "SELECT customer_id, COUNT(*) FROM RAW.SALES...",
        "answer": "Les 5 clients les plus actifs sont..."
    }
    # Garde les 200 dernières entrées
    history.append(entry)
    history = history[-200:]
```

#### Persistance JSON — état des agents

```python
def save_agent_state(agent_name, state_dict):
    # Sauvegarde dans data/agent_states/{agent_name}.json
    payload = {
        "agent_name": "SQLAgent",
        "updated_at": "2024-01-15T14:30:00Z",
        "state": {"dernière_table_utilisée": "SALES", ...}
    }

def load_agent_state(agent_name):
    # Charge le fichier ou retourne {} si inexistant
```

---

### `src/tools/data_tools.py` — Outils de l'IngestionAgent

#### `fetch_csv(file_path, separator, encoding) → str`

Lit un CSV et retourne une analyse complète (sans l'ingérer) :

```python
fetch_csv(file_path="/tmp/ventes.csv")

# Retourne :
{
    "success": true,
    "file_path": "/tmp/ventes.csv",
    "row_count": 5000,
    "column_count": 8,
    "columns": ["id", "nom", "montant", "date"],
    "dtypes": {"id": "int64", "montant": "float64", "date": "object"},
    "preview": [{"id": 1, "nom": "Alice", ...}, ...],  # 5 premières lignes
    "null_counts": {"id": 0, "nom": 2, "montant": 0},  # Valeurs manquantes
    "stats": {
        "id": {"mean": 2500.0, "min": 1, "max": 5000},
        "montant": {"mean": 149.90, "min": 5.0, "max": 9999.0}
    }
}
```

Gemini utilise ces infos pour décider comment mapper les types Python → Snowflake.

#### `call_external_api(url, method) → str`

Appelle une API HTTP externe et retourne le JSON brut :

```python
call_external_api(url="https://jsonplaceholder.typicode.com/users")

# Retourne :
{
    "success": true,
    "status_code": 200,
    "data": [{"id": 1, "name": "Leanne Graham", ...}, ...]
}
```

#### `DATA_TOOL_FUNCTIONS`

```python
DATA_TOOL_FUNCTIONS = [fetch_csv, call_external_api]
```

---

## Comment un tool passe de Python à Gemini

Voici le flux complet pour un appel d'outil :

```
1. Tu passes [execute_sql, get_table_schema] à Gemini
   via : config = GenerateContentConfig(tools=[execute_sql, get_table_schema])

2. Gemini lit les signatures et génère en interne :
   {
     "name": "execute_sql",
     "description": "Execute a SQL query on Snowflake...",
     "parameters": {
       "type": "object",
       "properties": {
         "query": {"type": "string", "description": "Valid Snowflake SQL..."}
       }
     }
   }

3. Gemini décide d'appeler l'outil et retourne :
   FunctionCall(name="execute_sql", args={"query": "SELECT..."})

4. BaseAgent intercepte ce FunctionCall :
   result = self._execute_tool("execute_sql", {"query": "SELECT..."})

5. SQLAgent._execute_tool() appelle dispatch_snowflake_tool()

6. dispatch_snowflake_tool() appelle execute_sql("SELECT...")

7. execute_sql() appelle SnowflakeClient.execute_query()

8. Le résultat JSON est renvoyé à Gemini comme FunctionResponse :
   FunctionResponse(name="execute_sql", response={"result": '{"success":true,...}'})

9. Gemini lit le résultat et décide de la suite
```

---

## Pourquoi les tools retournent des JSON strings ?

Tous les tools retournent des `str` (JSON encodé), pas des objets Python. C'est parce que :
1. Le protocole de function calling de Gemini transmet des strings dans `FunctionResponse`
2. Gemini peut lire et interpréter du JSON dans ses réponses
3. Ça standardise la gestion des erreurs (toujours `{"success": false, "error": "..."}`)

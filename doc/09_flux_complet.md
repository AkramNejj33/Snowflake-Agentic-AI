# 09 — Trace complète d'une requête, de A à Z

Ce fichier retrace exactement ce qui se passe dans le code quand tu poses une question.

---

## Question : "Quels sont les 3 produits les plus vendus ce mois ?"

---

### Étape 1 — L'utilisateur envoie la question

**Via Streamlit** (`src/ui/app.py:109`) :
```python
if prompt := st.chat_input("..."):
    # prompt = "Quels sont les 3 produits les plus vendus ce mois ?"
    orchestrator = _get_orchestrator()
    result = orchestrator.handle_request(prompt)
```

---

### Étape 2 — L'Orchestrator reçoit la question

**`src/agents/orchestrator.py:75`** — `handle_request()`

```python
def handle_request(self, user_input: str) -> dict:
    intent = self._classify_intent(user_input)   # ← Étape 3
```

---

### Étape 3 — Classification de l'intention

**`src/agents/orchestrator.py:195`** — `_classify_intent()`

Gemini est appelé avec temperature=0.0 et max_tokens=20 :
```
System: "Classe l'intention parmi sql_question / analysis / ingestion / general"
User:   "Quels sont les 3 produits les plus vendus ce mois ?"
Gemini: "sql_question"
```

→ `intent = "sql_question"`

---

### Étape 4 — Routing vers le handler data

**`src/agents/orchestrator.py:104`** :
```python
elif intent in ("sql_question", "analysis"):
    with_analysis = False  # "sql_question" ne force pas l'analyse
    response = self._handle_data_question(user_input, response, with_analysis=False)
```

---

### Étape 5 — SQLAgent.run() est appelé

**`src/agents/orchestrator.py:140`** :
```python
def _handle_data_question(self, user_input, response, with_analysis):
    sql_raw = self.sql_agent.run(user_input)   # ← SQLAgent entre en jeu
```

**`src/agents/sql_agent.py:53`** — `run()` avec retry loop :
```python
for attempt in range(1, 4):   # 3 essais max
    result = super().run(user_message)   # BaseAgent.run()
```

---

### Étape 6 — BaseAgent.run() — Iteration 1

**`src/agents/base_agent.py:59`** :

L'historique est initialisé avec le message utilisateur :
```python
conversation_history = [
    Content(role="user", parts=[Part(text="Quels sont les 3 produits les plus vendus ce mois ?")])
]
```

Gemini est appelé avec le system prompt du SQLAgent (qui contient le schéma Snowflake) et les 3 outils.

**Réponse Gemini (iteration 1)** :
```
Gemini décide d'appeler get_table_schema pour vérifier les colonnes de PRODUCTS et SALES.
→ function_call: get_table_schema(table_name="PRODUCTS", schema="RAW")
→ function_call: get_table_schema(table_name="SALES", schema="RAW")
```

---

### Étape 7 — Exécution des tools (iteration 1)

**`src/agents/base_agent.py:102`** :
```python
for part in fc_parts:
    result = self._execute_tool(fc.name, dict(fc.args))
```

**`src/agents/sql_agent.py:94`** :
```python
def _execute_tool(self, tool_name, tool_input):
    return dispatch_snowflake_tool(tool_name, tool_input)
```

**`src/tools/snowflake_tools.py:43`** — `get_table_schema()` :
```python
client = get_client()
info = client.get_schema("PRODUCTS", schema="RAW")
# Requête SQL : SELECT COLUMN_NAME, DATA_TYPE... FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='PRODUCTS'
return json.dumps({
    "success": True,
    "columns": [
        {"name": "PRODUCT_ID", "type": "NUMBER", "nullable": False},
        {"name": "PRODUCT_NAME", "type": "VARCHAR", "nullable": True},
        {"name": "CATEGORY", "type": "VARCHAR", "nullable": True},
        {"name": "UNIT_PRICE", "type": "NUMBER", "nullable": True},
        {"name": "STOCK_QTY", "type": "NUMBER", "nullable": True}
    ]
})
```

Les résultats des 2 tools sont ajoutés à l'historique :
```python
conversation_history.append(Content(role="user", parts=[
    Part(function_response=FunctionResponse(name="get_table_schema", response={"result": "..."})),
    Part(function_response=FunctionResponse(name="get_table_schema", response={"result": "..."})),
]))
```

---

### Étape 8 — BaseAgent.run() — Iteration 2

Gemini est rappelé avec le nouvel historique (il connaît maintenant les colonnes).

**Réponse Gemini (iteration 2)** :
```
Gemini génère le SQL et décide d'appeler execute_sql :
→ function_call: execute_sql(query="
    SELECT 
        p.PRODUCT_NAME,
        p.CATEGORY,
        SUM(s.QUANTITY) AS TOTAL_VENDU,
        SUM(s.TOTAL_AMOUNT) AS CHIFFRE_AFFAIRES
    FROM RAW.SALES s
    JOIN RAW.PRODUCTS p ON s.PRODUCT_ID = p.PRODUCT_ID
    WHERE DATE_TRUNC('MONTH', s.SALE_DATE) = DATE_TRUNC('MONTH', CURRENT_DATE())
    GROUP BY 1, 2
    ORDER BY TOTAL_VENDU DESC
    LIMIT 3
")
```

---

### Étape 9 — Exécution du SQL sur Snowflake

**`src/tools/snowflake_tools.py:20`** — `execute_sql()` :
```python
client = get_client()
df = client.execute_query(sql)
rows = df.to_dict(orient="records")
return json.dumps({"success": True, "rows": rows, "row_count": 3})
```

**`src/snowflake_client.py:90`** — `execute_query()` :
- `_ensure_connected()` vérifie que la connexion est active
- `cursor(DictCursor).execute(sql)` → Snowflake exécute la requête
- `fetchall()` → retourne les rows comme dicts

Snowflake retourne :
```python
[
    {"PRODUCT_NAME": "Laptop Pro", "CATEGORY": "Electronics", "TOTAL_VENDU": 42, "CHIFFRE_AFFAIRES": 62790.00},
    {"PRODUCT_NAME": "Chaise Ergonomique", "CATEGORY": "Furniture", "TOTAL_VENDU": 38, "CHIFFRE_AFFAIRES": 11020.00},
    {"PRODUCT_NAME": "Écran 4K", "CATEGORY": "Electronics", "TOTAL_VENDU": 31, "CHIFFRE_AFFAIRES": 24800.00}
]
```

---

### Étape 10 — BaseAgent.run() — Iteration 3

Gemini reçoit les résultats SQL et génère sa réponse finale (plus de function_call) :

```json
{
    "sql": "SELECT p.PRODUCT_NAME, p.CATEGORY, SUM(s.QUANTITY) AS TOTAL_VENDU...",
    "results": [
        {"PRODUCT_NAME": "Laptop Pro", "TOTAL_VENDU": 42, "CHIFFRE_AFFAIRES": 62790.0},
        {"PRODUCT_NAME": "Chaise Ergonomique", "TOTAL_VENDU": 38, "CHIFFRE_AFFAIRES": 11020.0},
        {"PRODUCT_NAME": "Écran 4K", "TOTAL_VENDU": 31, "CHIFFRE_AFFAIRES": 24800.0}
    ],
    "explanation": "Ce mois-ci, les 3 produits les plus vendus sont le Laptop Pro (42 unités, CA 62 790€), suivi de la Chaise Ergonomique (38 unités, CA 11 020€) et de l'Écran 4K (31 unités, CA 24 800€). L'électronique domine largement avec 73% du chiffre d'affaires."
}
```

`BaseAgent.run()` retourne ce JSON string → `SQLAgent.run()` le reçoit.

---

### Étape 11 — SQLAgent valide le résultat

**`src/agents/sql_agent.py:67`** :
```python
parsed = _try_parse_json(result)   # Parse le JSON
if "error" not in parsed:
    return json.dumps(parsed)      # Pas d'erreur → retour direct (pas de retry)
```

---

### Étape 12 — Orchestrator assemble la réponse

**`src/agents/orchestrator.py:140`** :
```python
sql_result = _parse_sql_result(sql_raw)
response["sql"]    = "SELECT p.PRODUCT_NAME..."
response["data"]   = [{"PRODUCT_NAME": "Laptop Pro", ...}, ...]
response["answer"] = "Ce mois-ci, les 3 produits les plus vendus sont..."

# with_analysis=False → AnalystAgent n'est pas appelé
```

---

### Étape 13 — Persistance de l'interaction

**`src/agents/orchestrator.py:112`** :
```python
# Historique JSON
save_interaction(
    question="Quels sont les 3 produits les plus vendus ce mois ?",
    answer="Ce mois-ci, les 3 produits...",
    sql="SELECT p.PRODUCT_NAME...",
    agent="sql_question"
)

# ChromaDB sémantique
save_to_memory(
    key="q_8372918374",
    content="Q: Quels sont les 3 produits les plus vendus ce mois ?\nA: Ce mois-ci...",
    metadata={"type": "interaction", "intent": "sql_question"}
)
```

---

### Étape 14 — Affichage dans Streamlit

**`src/ui/app.py:129`** — `_render_assistant_message(result)` :

```
┌─────────────────────────────────────────────────┐
│ assistant                                        │
│                                                  │
│ Ce mois-ci, les 3 produits les plus vendus      │
│ sont le Laptop Pro (42 unités)...               │
│                                                  │
│ ▼ SQL généré                                     │
│   SELECT p.PRODUCT_NAME, p.CATEGORY...          │
│                                                  │
│ ▼ Résultats (3 lignes)                           │
│   PRODUCT_NAME     | TOTAL_VENDU | CA            │
│   Laptop Pro       | 42          | 62790.0       │
│   Chaise Ergo.     | 38          | 11020.0       │
│   Écran 4K         | 31          | 24800.0       │
└─────────────────────────────────────────────────┘
```

---

## Résumé des appels

```
Utilisateur
    ↓ question
Streamlit
    ↓ handle_request()
Orchestrator
    ↓ _classify_intent()
    Gemini (1 appel, temperature=0.0) → "sql_question"
    ↓ sql_agent.run()
SQLAgent (extends BaseAgent)
    ↓ Iteration 1
    Gemini → function_call: get_table_schema(PRODUCTS)
                             get_table_schema(SALES)
    ↓ dispatch_snowflake_tool()
    SnowflakeClient.execute_query() × 2
    ↓ Iteration 2
    Gemini → function_call: execute_sql("SELECT...")
    ↓ dispatch_snowflake_tool()
    SnowflakeClient.execute_query() × 1
    ↓ Iteration 3
    Gemini → texte JSON final
    ↓ parse + return
Orchestrator
    ↓ save_interaction() + save_to_memory()
    interaction_history.json + ChromaDB
    ↓ retourne le dict unifié
Streamlit
    ↓ affiche réponse + SQL + tableau
Utilisateur voit la réponse
```

**Nombre total d'appels Gemini : 2**  
(1 pour la classification d'intention + 3 iterations pour SQLAgent = mais les 3 iterations sont un seul "run" avec 3 appels Gemini)

**Nombre total de requêtes Snowflake : 3**  
(2 get_schema + 1 execute_sql)

**Durée typique : 3-8 secondes**

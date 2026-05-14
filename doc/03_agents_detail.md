# 03 — Détail de chaque agent

## Vue d'ensemble des 4 agents

```
                    ┌──────────────────────────────────┐
                    │           Orchestrator            │
                    │  (classe l'intention + route)     │
                    └────────────┬─────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
        ┌──────────┐      ┌──────────┐      ┌──────────────┐
        │ SQLAgent │      │ Analyst  │      │  Ingestion   │
        │          │      │  Agent   │      │    Agent     │
        └──────────┘      └──────────┘      └──────────────┘
        Outils:            Outils:           Outils:
        execute_sql        save_memory       fetch_csv
        get_table_schema   recall_memory     call_external_api
        list_tables
```

---

## 1. L'Orchestrator

**Fichier :** `src/agents/orchestrator.py`

L'Orchestrator n'hérite PAS de `BaseAgent`. Il utilise Gemini directement (sans boucle agentique) uniquement pour **classifier l'intention**. C'est le point d'entrée unique du système.

### Rôle
- Recevoir la question de l'utilisateur
- Classifier l'intention (sql / analyse / ingestion / général)
- Router vers le bon agent
- Sauvegarder l'interaction en mémoire
- Retourner une réponse unifiée

### Classification d'intention

```python
_CLASSIFIER_PROMPT = """Classe l'intention de l'utilisateur parmi :
- "sql_question" : question sur des données (ventes, clients, stats)
- "analysis"     : analyse, insights, tendances, recommandations
- "ingestion"    : importer, charger des données (CSV, API)
- "general"      : toute autre question
Réponds UNIQUEMENT avec le mot-clé."""
```

Gemini reçoit ce prompt + la question, et répond avec un seul mot : `sql_question`, `analysis`, `ingestion` ou `general`.

```python
resp = self._genai_client.models.generate_content(
    model=settings.google.model,
    contents=user_input,
    config=types.GenerateContentConfig(
        system_instruction=_CLASSIFIER_PROMPT,
        temperature=0.0,       # Totalement déterministe
        max_output_tokens=20,  # Juste un mot, pas plus
    ),
)
```

### Routing des requêtes

```python
def handle_request(self, user_input: str) -> dict:
    intent = self._classify_intent(user_input)

    if intent == "ingestion":
        → self._handle_ingestion()        → IngestionAgent

    elif intent in ("sql_question", "analysis"):
        → self._handle_data_question()    → SQLAgent [+ AnalystAgent si "analysis"]

    else:
        → self._general_answer()          → Gemini directement (pas d'agent)
```

### La réponse unifiée

Peu importe quel agent a répondu, l'Orchestrator retourne toujours le même format :

```python
{
    "intent": "sql_question",
    "question": "Quels sont les top clients ?",
    "answer": "Les 5 clients les plus actifs sont...",
    "sql": "SELECT customer_id, COUNT(*) FROM RAW.SALES...",
    "data": [{"CUSTOMER_ID": 1, "NB_ORDERS": 42}, ...],
    "analysis": None,   # Rempli seulement si analyse demandée
    "error": None,
}
```

### Instanciation lazy des agents

Les agents sont créés **uniquement quand on en a besoin** (pas au démarrage) :

```python
@property
def sql_agent(self) -> SQLAgent:
    if self._sql_agent is None:
        self._sql_agent = SQLAgent()   # Créé au premier appel
    return self._sql_agent
```

Pourquoi ? Parce que `SQLAgent.__init__()` se connecte à Snowflake pour récupérer le schéma. Si Snowflake est lent, ça ne bloque pas le démarrage de l'application.

### Extraction des paramètres d'ingestion

Quand l'intent est "ingestion", l'Orchestrator extrait les paramètres par regex (pas d'IA ici, c'est du parsing simple) :

```python
# Trouve un fichier .csv dans le texte
csv_match = re.search(r'(["\']?)([^\s"\']+\.csv)\1', user_input)
# Trouve une URL http(s)
url_match = re.search(r"https?://[^\s\"']+", user_input)
# Trouve un nom de table
table_match = re.search(r"(?:table|dans|vers|into)\s+([A-Za-z_][A-Za-z0-9_]*)", user_input)
```

---

## 2. SQLAgent

**Fichier :** `src/agents/sql_agent.py`

C'est l'agent le plus important. Il traduit une question en langage naturel en SQL Snowflake, exécute la requête, et retourne les résultats.

### Initialisation — injection du schéma live

Au démarrage, SQLAgent se connecte à Snowflake pour récupérer le schéma actuel de toutes les tables et l'injecter dans son system prompt :

```python
def __init__(self):
    schema_context = self._fetch_schema_context()
    # schema_context = """
    # Table: RAW.CUSTOMERS
    #   - CUSTOMER_ID (NUMBER, NOT NULL)
    #   - EMAIL (VARCHAR, NULL)
    # Table: RAW.SALES
    #   ...
    # """
    
    system_prompt = _BASE_SYSTEM.format(schema_context=schema_context)
    super().__init__(name="SQLAgent", system_prompt=system_prompt, tools=SNOWFLAKE_TOOL_FUNCTIONS)
```

Si Snowflake est indisponible au démarrage, un schéma statique (hardcodé) est utilisé comme fallback.

### Le system prompt du SQLAgent

```
Tu es un expert SQL Snowflake.

RÈGLES IMPÉRATIVES :
1. Toujours utiliser des noms qualifiés : RAW.SALES, ANALYTICS.SALES_SUMMARY
2. Avant d'écrire une requête, utilise get_table_schema si tu as un doute
3. Ajouter LIMIT 100 par défaut
4. Si erreur → analyse et corrige (max 3 tentatives)
5. Réponse TOUJOURS en JSON : {"sql": "...", "results": [...], "explanation": "..."}
6. Éviter les SELECT *
7. Dates au format DATE (YYYY-MM-DD)

SCHÉMA DISPONIBLE :
[schéma injecté dynamiquement depuis Snowflake]
```

### Auto-correction sur erreur SQL (3 essais)

SQLAgent surcharge `run()` pour ajouter un mécanisme de retry intelligent :

```python
def run(self, user_message: str) -> str:
    for attempt in range(1, 4):  # 3 essais max
        result = super().run(user_message)  # Appel BaseAgent.run()
        parsed = _try_parse_json(result)
        
        if "error" not in parsed:
            return json.dumps(parsed)   # Succès !
        
        if attempt < 3:
            # Réinjecte l'erreur dans la prochaine question
            user_message = (
                f"La requête a échoué avec l'erreur : {parsed['error']}\n"
                f"Corrige le SQL et réessaie."
            )
        # attempt 3 → retourne quand même (avec l'erreur)
```

Exemple concret :
- Essai 1 : Gemini génère `SELECT * FROM CUSTOMERS` → erreur "table CUSTOMERS doesn't exist"
- Essai 2 : Gemini reçoit l'erreur, génère `SELECT * FROM RAW.CUSTOMERS LIMIT 100` → succès

### Les 3 outils du SQLAgent

```
execute_sql(query)           → Exécute du SQL, retourne les rows en JSON
get_table_schema(table, schema) → Retourne les colonnes d'une table
list_tables(schema)          → Liste toutes les tables d'un schéma
```

---

## 3. AnalystAgent

**Fichier :** `src/agents/analyst_agent.py`

Cet agent reçoit des **données déjà récupérées** (résultats du SQLAgent) et produit une analyse textuelle structurée en Markdown + du code Plotly.

### Différence avec SQLAgent

- SQLAgent : question → SQL → données
- AnalystAgent : données → analyse narrative

AnalystAgent n'exécute **pas** de SQL. Il analyse des données qu'on lui passe.

### Méthode d'entrée : `analyse()`

```python
def analyse(self, data, question="", context="") -> str:
    # Normalise les données en liste de records
    if isinstance(data, pd.DataFrame):
        records = data.to_dict(orient="records")
    elif isinstance(data, dict):
        records = [data]
    else:
        records = list(data)
    
    # Limite à 500 records pour ne pas dépasser la fenêtre contextuelle
    json_data = json.dumps(records[:500], ...)
    
    # Construit le prompt avec les données
    prompt = f"""
    Question : {question}
    Volume : {len(records)} enregistrements
    
    Données :
    ```json
    {json_data}
    ```
    """
    
    self.reset()          # Efface l'historique (chaque analyse est indépendante)
    return self.run(prompt)
```

### La structure de réponse imposée

Le system prompt force Gemini à répondre avec cette structure Markdown exacte :

```markdown
## 📊 Résumé exécutif
[2-3 phrases]

## 🔍 Insights clés
[3-5 points avec des chiffres]

## 📈 Tendances et anomalies
[patterns, valeurs aberrantes]

## 💡 Recommandations
[2-3 actions concrètes]

## 📉 Code de visualisation
```python
import plotly.express as px
# code fonctionnel
```
```

### Les outils de l'AnalystAgent

AnalystAgent utilise les **outils mémoire** (pas Snowflake) :
- `save_memory(key, content)` → peut sauvegarder des insights importants
- `recall_memory(query)` → peut chercher dans les analyses passées pour comparer

---

## 4. IngestionAgent

**Fichier :** `src/agents/ingestion_agent.py`

Cet agent charge des données externes (CSV ou API) dans Snowflake.

### Deux points d'entrée publics

```python
agent.ingest_csv(file_path="data.csv", table_name="MY_TABLE")
agent.ingest_api(url="https://api.example.com/data", table_name="API_DATA", json_key="results")
```

### Workflow interne (méthode `_ingest_dataframe`)

```
1. Nettoyage des noms de colonnes
   "first name" → "FIRST_NAME"  (majuscules, caractères spéciaux → _)

2. Génération du DDL Snowflake
   pandas dtype → type Snowflake :
   int64    → NUMBER(18,0)
   float64  → NUMBER(18,4)
   object   → VARCHAR(500)
   datetime → TIMESTAMP_NTZ
   + colonne INGESTED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()

3. Création de la table
   CREATE TABLE IF NOT EXISTS RAW.MY_TABLE (...)

4. Insertion par batch de 1000 lignes
   INSERT INTO RAW.MY_TABLE (COL1, COL2) VALUES (%s, %s)
   → executemany() pour les performances

5. Rapport de résultat
   {
     "source": "data.csv",
     "table": "RAW.MY_TABLE",
     "total_rows": 5000,
     "rows_inserted": 5000,
     "rows_failed": 0,
     "errors": [],
     "ddl": "CREATE TABLE IF NOT EXISTS...",
     "success": true
   }
```

### Exemple de DDL généré automatiquement

Pour un CSV avec les colonnes `first_name (object)`, `age (int64)`, `revenue (float64)` :

```sql
CREATE TABLE IF NOT EXISTS RAW.MY_TABLE (
    FIRST_NAME VARCHAR(500) NULL,
    AGE NUMBER(18,0) NULL,
    REVENUE NUMBER(18,4) NULL,
    INGESTED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```

### Les outils de l'IngestionAgent

```
fetch_csv(file_path)           → Lit le CSV, retourne colonnes + stats + preview
call_external_api(url, method) → Appelle une API HTTP, retourne le JSON
```

Ces outils sont utilisés par Gemini pendant la boucle agentique pour **inspecter** les données avant de décider quoi faire.

---

## Tableau comparatif des 4 agents

| Aspect | Orchestrator | SQLAgent | AnalystAgent | IngestionAgent |
|---|---|---|---|---|
| Hérite de BaseAgent ? | Non | Oui | Oui | Oui |
| Utilise la boucle agentique ? | Non (1 appel Gemini) | Oui | Oui | Oui |
| Outils disponibles | Aucun | execute_sql, get_schema, list_tables | save_memory, recall_memory | fetch_csv, call_api |
| Accès Snowflake ? | Non | Oui (lecture) | Non | Oui (lecture + écriture) |
| Format de sortie | dict Python | JSON string | Markdown | dict Python |
| Retries ? | Non | 3 essais auto | Non | Non |

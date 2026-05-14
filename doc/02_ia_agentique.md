# 02 — L'IA Agentique : Gemini + la boucle agentique

## C'est quoi un agent IA ?

Un **agent IA** c'est un LLM (Large Language Model) qui ne se contente pas de répondre du texte — il peut **appeler des outils** (fonctions Python), **observer les résultats**, et **décider quoi faire ensuite**.

Contrairement à un simple chatbot qui répond directement, un agent suit ce cycle :

```
Utilisateur pose une question
        ↓
Gemini réfléchit : "Dois-je appeler un outil ?"
        ↓
    OUI → appelle l'outil (ex: execute_sql)
        ↓
    Reçoit le résultat de l'outil
        ↓
    Réfléchit encore : "Ai-je assez d'infos ?"
        ↓
    NON → appelle un autre outil
    OUI → génère la réponse finale
```

Ce cycle peut se répéter jusqu'à **15 fois** (configuré dans `base_agent.py`).

---

## Google Gemini et le "function calling"

Le projet utilise **Google Gemini 2.0 Flash** via la librairie `google-genai`.

### Pourquoi Gemini ?
- Gratuit jusqu'à 15 requêtes/minute (quota aistudio.google.com)
- Supporte le **function calling natif** : Gemini peut décider d'appeler une fonction Python
- Comprend très bien le français

### Comment Gemini connaît les outils disponibles ?

C'est la partie magique : tu passes **directement des fonctions Python** à Gemini. Il lit automatiquement :
- Le **nom** de la fonction
- Les **type hints** des paramètres (`str`, `int`, etc.)
- La **docstring** (description + `Args:`)

Et il génère lui-même le schéma JSON en interne.

```python
# Exemple : tu passes juste la fonction Python
def execute_sql(query: str) -> str:
    """Execute a SQL query on Snowflake and return results as JSON.
    
    Args:
        query: Valid Snowflake SQL statement to execute.
    """
    ...

# Gemini sait que cet outil existe, ce qu'il fait, et comment l'appeler
SNOWFLAKE_TOOL_FUNCTIONS = [execute_sql, get_table_schema, list_tables]
```

---

## La classe BaseAgent — le moteur de tout

**Fichier :** `src/agents/base_agent.py`

C'est la classe abstraite dont héritent TOUS les agents (SQL, Analyst, Ingestion). Elle contient la boucle agentique complète.

### Attributs

```python
class BaseAgent(ABC):
    def __init__(self, name, system_prompt, tools):
        self.name = name                    # Nom pour les logs
        self.system_prompt = system_prompt  # Instructions données à Gemini
        self.tools = tools                  # Liste de fonctions Python
        self.client = genai.Client(...)     # Client Google Gemini
        self.model = "gemini-2.0-flash"     # Modèle utilisé
        self.conversation_history = []      # Historique de la conversation
```

### La méthode `run()` — le cœur de l'agent

```python
def run(self, user_message: str) -> str:
```

Voici ce qui se passe étape par étape quand tu appelles `run()` :

#### Étape 1 : Ajouter le message utilisateur à l'historique

```python
self.conversation_history.append(
    types.Content(role="user", parts=[types.Part(text=user_message)])
)
```

L'historique garde toute la conversation : questions, réponses Gemini, résultats d'outils. C'est ce qui permet à Gemini d'avoir du contexte.

#### Étape 2 : Boucle sur 15 itérations max

```python
for iteration in range(15):  # _MAX_ITERATIONS = 15
    config = types.GenerateContentConfig(
        system_instruction=self.system_prompt,  # Rôle de l'agent
        temperature=0.1,                         # Peu de créativité (déterministe)
        max_output_tokens=4096,
        tools=self.tools,                        # Les fonctions Python disponibles
    )
    
    response = self.client.models.generate_content(
        model=self.model,
        contents=self.conversation_history,
        config=config,
    )
```

#### Étape 3 : Analyser la réponse de Gemini

Gemini peut répondre de deux façons :

**Cas A : Gemini veut appeler un outil**
```python
fc_parts = [p for p in candidate.content.parts 
            if hasattr(p, "function_call") and p.function_call is not None]

# fc_parts = [FunctionCall(name="execute_sql", args={"query": "SELECT..."})]
```

**Cas B : Gemini a la réponse finale**
```python
if not fc_parts:
    return _extract_text(candidate.content)  # Retourne le texte final
```

#### Étape 4 : Exécuter les outils et renvoyer les résultats

```python
for part in fc_parts:
    fc = part.function_call
    result = self._execute_tool(fc.name, dict(fc.args))  # Appel Python réel
    
    fr_parts.append(types.Part(
        function_response=types.FunctionResponse(
            name=fc.name,
            response={"result": result},  # Résultat renvoyé à Gemini
        )
    ))

# Ajout des résultats à l'historique
self.conversation_history.append(
    types.Content(role="user", parts=fr_parts)
)
# → retour au début de la boucle
```

### Schéma de la boucle complète

```
run("Quels sont les top clients ?")
    │
    ▼
[Iteration 1]
  Gemini → function_call: get_table_schema("CUSTOMERS")
  Python → {"columns": ["CUSTOMER_ID", "EMAIL", ...]}
  Gemini reçoit le schéma
    │
    ▼
[Iteration 2]
  Gemini → function_call: execute_sql("SELECT ... FROM RAW.CUSTOMERS LIMIT 5")
  Python → {"rows": [{...}, {...}], "row_count": 5}
  Gemini reçoit les données
    │
    ▼
[Iteration 3]
  Gemini → texte final : {"sql": "...", "results": [...], "explanation": "..."}
  → return ce texte
```

### La méthode abstraite `_execute_tool()`

Chaque agent surcharge cette méthode pour router les appels vers ses propres outils :

```python
@abstractmethod
def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
    """Dispatch l'appel d'outil vers la fonction Python correspondante."""
```

---

## Temperature 0.1 — pourquoi ?

La `temperature` contrôle la créativité/aléatoire de Gemini :
- `0.0` = totalement déterministe (même entrée → même sortie)
- `1.0` = très créatif / aléatoire

Pour la génération de SQL, on veut `0.1` : **peu aléatoire**, pour que Gemini génère des requêtes correctes et reproductibles. L'orchestrateur utilise `0.0` pour la classification d'intention.

---

## Pourquoi 15 itérations max ?

Pour éviter les boucles infinies. Si un agent appelle des outils 15 fois de suite sans donner de réponse finale, c'est probablement qu'il est perdu. On coupe et on retourne un message d'erreur :

```python
return f"[{self.name}] Nombre maximum d'itérations atteint sans réponse finale."
```

En pratique, les agents répondent en 2-3 itérations.

---

## L'historique de conversation (`conversation_history`)

C'est une liste de `types.Content` qui représente toute la conversation :

```python
[
  Content(role="user",  parts=[Part(text="Question utilisateur")]),
  Content(role="model", parts=[Part(function_call=FunctionCall(...))]),
  Content(role="user",  parts=[Part(function_response=FunctionResponse(...))]),
  Content(role="model", parts=[Part(text="Réponse finale")]),
]
```

Gemini voit TOUT cet historique à chaque appel. C'est ce qui lui permet de comprendre le contexte et de ne pas répéter les mêmes appels d'outils.

La méthode `reset()` efface cet historique entre deux questions indépendantes.

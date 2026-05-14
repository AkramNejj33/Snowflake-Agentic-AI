# 07 — Mémoire et persistance

Le projet a **3 niveaux de persistance**, chacun avec un rôle différent.

---

## Niveau 1 — Mémoire à court terme : `conversation_history`

**Où :** Dans l'objet `BaseAgent` en mémoire RAM  
**Durée :** Le temps d'un seul `run()` (une question)  
**Fichier :** `src/agents/base_agent.py`

```python
self.conversation_history: list[types.Content] = []
```

C'est la liste des messages échangés entre l'agent et Gemini pendant une seule exécution. Elle permet à Gemini de se souvenir qu'il a déjà appelé `get_table_schema` et qu'il a reçu les colonnes, sans avoir à le refaire.

Elle est **effacée** via `self.reset()` entre deux questions indépendantes (AnalystAgent le fait systématiquement dans `analyse()`).

---

## Niveau 2 — Mémoire sémantique : ChromaDB

**Où :** `data/chroma/` (dossier local sur disque)  
**Durée :** Permanente (survit aux redémarrages)  
**Fichier :** `src/tools/memory_tools.py`

### C'est quoi ChromaDB ?

ChromaDB est une **base de données vectorielle**. Au lieu de stocker des données sous forme de lignes/colonnes comme SQL, elle stocke des **vecteurs de nombres** qui représentent le sens d'un texte.

Quand tu sauvegardes "Les ventes ont augmenté de 23% en Q3", ChromaDB convertit ce texte en un vecteur de 768 nombres (un point dans un espace à 768 dimensions). Quand tu cherches "croissance des revenus", la recherche trouve les textes dont le vecteur est **proche** de celui de ta requête.

C'est ce qu'on appelle une **recherche sémantique** : elle comprend le sens, pas juste les mots-clés.

### Structure du client ChromaDB

```python
# Singleton lazy — créé au premier appel
_chroma_client: chromadb.ClientAPI | None = None

def _get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path="./data/chroma",              # Dossier local de stockage
            settings=ChromaSettings(anonymized_telemetry=False)
        )
    return _chroma_client

def _get_collection(name="agent_memory"):
    client = _get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},  # Similarité cosinus pour la recherche
    )
```

### `save_to_memory(key, content, metadata)`

```python
collection.upsert(
    ids=[key],           # Identifiant unique (ex: "q_1234567890")
    documents=[content], # Texte à embedder et stocker
    metadatas=[{
        "key": key,
        "timestamp": "2024-01-15T14:30:00Z",
        "type": "interaction",
        "intent": "sql_question"
    }]
)
```

`upsert` = insert OR update : si la clé existe déjà, on écrase. Sinon, on insère.

### `search_memory(query, n_results=5)`

```python
results = collection.query(
    query_texts=[query],   # Texte de recherche → converti en vecteur
    n_results=n,
    include=["documents", "metadatas", "distances"]
)

# Résultat :
{
    "results": [
        {
            "content": "Q: top clients ? A: Les 5 premiers...",
            "key": "q_1234567890",
            "distance": 0.0823,    # 0 = identique, 2 = opposé
            "metadata": {...}
        }
    ]
}
```

### Qui utilise ChromaDB ?

1. **L'Orchestrator** : sauvegarde chaque interaction après réponse
   ```python
   save_to_memory(
       key=f"q_{abs(hash(user_input))}",
       content=f"Q: {user_input}\nA: {response['answer'][:500]}",
       metadata={"type": "interaction", "intent": intent}
   )
   ```

2. **L'AnalystAgent** : peut utiliser `save_memory` et `recall_memory` pendant son analyse pour chercher des insights passés similaires

---

## Niveau 3 — Historique JSON

**Où :** `data/agent_states/interaction_history.json`  
**Durée :** Permanente (max 200 entrées, les plus anciennes sont supprimées)  
**Fichier :** `src/tools/memory_tools.py`

### Structure d'une entrée

```json
{
    "id": "a1b2c3d4-...",
    "timestamp": "2024-01-15T14:30:00.000Z",
    "agent": "sql_question",
    "question": "Quels sont les 5 clients avec le plus de commandes ?",
    "sql": "SELECT customer_id, COUNT(*) as nb FROM RAW.SALES GROUP BY 1 ORDER BY 2 DESC LIMIT 5",
    "answer": "Les 5 clients les plus actifs sont..."
}
```

### Gestion du fichier

```python
def save_interaction(question, answer, sql=None, agent="unknown"):
    history_path = Path("./data/agent_states/interaction_history.json")
    
    # Lire l'historique existant
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    
    # Ajouter l'entrée
    history.append(entry)
    
    # Garder seulement les 200 dernières
    history = history[-200:]
    
    # Réécrire le fichier
    history_path.write_text(json.dumps(history, indent=2))
```

Cet historique est exposé via l'API FastAPI (`GET /history`) et affiché dans l'UI Streamlit si tu veux consulter les interactions passées.

---

## Niveau 4 — État des agents JSON

**Où :** `data/agent_states/{agent_name}.json`  
**Durée :** Permanente

Chaque agent peut sauvegarder son "état" (informations à retenir entre les sessions). Actuellement peu utilisé dans le code, mais l'infrastructure est en place :

```python
save_agent_state("SQLAgent", {
    "dernière_table_utilisée": "SALES",
    "nb_requêtes_exécutées": 42
})

state = load_agent_state("SQLAgent")
# → {"dernière_table_utilisée": "SALES", "nb_requêtes_exécutées": 42}
```

---

## Récapitulatif des 3 niveaux

| Niveau | Technologie | Durée | Données stockées | Qui l'utilise |
|---|---|---|---|---|
| Court terme | RAM (Python list) | 1 run | Messages Gemini | BaseAgent (tous les agents) |
| Sémantique | ChromaDB vectoriel | Permanent | Q&A en embedded | Orchestrator + AnalystAgent |
| Historique | JSON sur disque | Permanent (max 200) | Q&A brut | Orchestrator |
| État agent | JSON sur disque | Permanent | État custom | Tout agent |

---

## Pourquoi deux systèmes de mémoire (ChromaDB + JSON) ?

- **JSON** = simple, rapide, lisible à l'oeil nu, parfait pour l'historique brut
- **ChromaDB** = recherche par sens, parfait pour retrouver "toutes les questions sur les ventes" sans chercher le mot exact "ventes"

Les deux se complètent : JSON garde l'historique complet dans l'ordre chronologique, ChromaDB permet de retrouver des interactions similaires sémantiquement.

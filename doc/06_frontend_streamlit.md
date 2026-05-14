# 06 — Frontend : Interface Streamlit

**Fichier :** `src/ui/app.py`

## C'est quoi Streamlit ?

Streamlit est un framework Python qui permet de créer des interfaces web data **sans écrire de HTML/CSS/JavaScript**. Tout se code en Python pur. À chaque interaction utilisateur (bouton cliqué, texte saisi), Streamlit **rerun le script Python de A à Z**.

---

## Architecture de l'UI

L'interface est divisée en :
- 1 **sidebar** (panneau latéral) — toujours visible
- 3 **onglets** (tabs) — contenu principal

```
┌─────────────────────────────────────────────────────────┐
│ SIDEBAR              │ TAB 1 : 💬 Chat Data             │
│                      │ TAB 2 : 📥 Ingestion             │
│ ❄️ Snowflake AI      │ TAB 3 : 📊 Explorer              │
│                      │                                  │
│ Statut Snowflake: ✅ │ [contenu de l'onglet actif]      │
│                      │                                  │
│ Schéma : [RAW ▼]    │                                  │
│                      │                                  │
│ Exemples de ques...  │                                  │
└─────────────────────────────────────────────────────────┘
```

---

## La Sidebar

```python
def _render_sidebar() -> str:
    with st.sidebar:
        st.title("❄️ Snowflake Agentic AI")
        
        # Statut de connexion Snowflake (live)
        client = _get_client()
        if client.is_healthy():
            st.success("Connecté", icon="✅")
        else:
            st.error("Non connecté", icon="❌")
        
        # Sélecteur de schéma (RAW ou ANALYTICS)
        schema = st.selectbox("Schéma Snowflake", ["RAW", "ANALYTICS"])
        
        # Exemples de questions
        with st.expander("Exemples de questions"):
            st.markdown("- Quels sont les 5 clients...")
    
    return schema  # Schéma sélectionné = état partagé entre les onglets
```

---

## Tab 1 — Chat Data (`_tab_chat`)

C'est l'onglet principal. C'est ici que tu poses tes questions.

### Gestion de l'historique de chat

Streamlit rerun le script à chaque interaction, donc on garde l'historique dans `st.session_state` (mémoire persistante entre les reruns) :

```python
if "messages" not in st.session_state:
    st.session_state.messages = []   # Initialisation au premier chargement

# Affiche tous les messages passés
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):  # "user" ou "assistant"
        _render_assistant_message(msg)
```

### Traitement d'une nouvelle question

```python
if prompt := st.chat_input("Ex: Quels sont les 10 produits les plus vendus ?"):
    # 1. Sauvegarder et afficher la question
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # 2. Appeler l'Orchestrator
    with st.spinner("Analyse en cours..."):
        orchestrator = _get_orchestrator()
        result = orchestrator.handle_request(prompt)
    
    # 3. Afficher la réponse
    _render_assistant_message(result)
    
    # 4. Sauvegarder la réponse dans l'historique
    st.session_state.messages.append({**result, "role": "assistant"})
```

### Affichage d'une réponse agent (`_render_assistant_message`)

La réponse de l'Orchestrator est un dict avec plusieurs champs. Chaque champ s'affiche différemment :

```python
def _render_assistant_message(msg):
    answer   = msg.get("answer", "")
    sql      = msg.get("sql")
    data     = msg.get("data", [])
    analysis = msg.get("analysis")
    error    = msg.get("error")

    if error:
        st.error(f"Erreur : {error}")
        return

    # Réponse principale (Markdown rendu)
    st.markdown(answer)

    # SQL en accordéon (plié par défaut)
    if sql:
        with st.expander("SQL généré", expanded=False):
            st.code(sql, language="sql")    # Coloration syntaxique SQL

    # Tableau de données (ouvert par défaut)
    if data:
        df = pd.DataFrame(data)
        with st.expander(f"Résultats ({len(df)} lignes)", expanded=True):
            st.dataframe(df, use_container_width=True)

    # Analyse détaillée (en accordéon)
    if analysis and analysis != answer:
        with st.expander("Analyse détaillée", expanded=False):
            st.markdown(analysis)
```

L'interface différencie visuellement :
- Le texte de réponse (Markdown libre)
- Le SQL généré (bloc de code avec coloration)
- Les données (tableau interactif triable/filtrable)
- L'analyse (Markdown structuré)

---

## Tab 2 — Ingestion (`_tab_ingestion`)

L'onglet est divisé en **2 colonnes** : CSV à gauche, API à droite.

### Colonne gauche — Upload CSV

```python
uploaded = st.file_uploader("Glissez un fichier CSV", type=["csv"])
table_name_csv = st.text_input("Nom de la table cible")

if uploaded:
    # Aperçu du CSV avant ingestion
    df_preview = pd.read_csv(uploaded)
    st.info(f"{len(df_preview)} lignes × {len(df_preview.columns)} colonnes")
    st.dataframe(df_preview.head(10))
    
    if st.button("Ingérer dans Snowflake"):
        # Écrire le fichier uploadé dans un temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        
        # Lancer l'ingestion
        report = orchestrator.ingestion_agent.ingest_csv(
            file_path=tmp_path,
            table_name=table_name_csv or Path(uploaded.name).stem.upper()
        )
        
        # Supprimer le temp file
        Path(tmp_path).unlink(missing_ok=True)
        
        # Afficher le rapport
        _render_ingestion_report(report)
```

Pourquoi un fichier temporaire ? Streamlit donne accès au contenu binaire du fichier uploadé, mais `IngestionAgent.ingest_csv()` attend un chemin de fichier. On écrit donc le contenu dans un fichier temporaire, on l'ingère, puis on le supprime.

### Colonne droite — API JSON

```python
api_url = st.text_input("URL de l'API")
table_name_api = st.text_input("Nom de la table cible")
json_key = st.text_input("Clé JSON (optionnel)")

# Bouton de test (n'ingère pas, juste vérifie l'API)
if st.button("Tester l'API"):
    resp = httpx.get(api_url, timeout=10)
    st.json(resp.json()[:3])    # Affiche les 3 premières entrées

# Bouton d'ingestion réelle
if st.button("Ingérer depuis l'API"):
    report = orchestrator.ingestion_agent.ingest_api(
        url=api_url,
        table_name=table_name_api,
        json_key=json_key or None
    )
    _render_ingestion_report(report)
```

### Rapport d'ingestion (`_render_ingestion_report`)

```python
def _render_ingestion_report(report):
    if report.get("success"):
        st.success(f"✅ {report['rows_inserted']} lignes ingérées dans {report['table']}")
    else:
        st.warning("⚠️ Ingestion partielle ou échouée")

    # 3 métriques côte à côte
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Lignes insérées", report["rows_inserted"])
    col_b.metric("Lignes échouées", report["rows_failed"])
    col_c.metric("Total", report["total_rows"])

    # DDL généré (optionnel)
    if report.get("ddl"):
        with st.expander("DDL créé"):
            st.code(report["ddl"], language="sql")
```

---

## Tab 3 — Explorer (`_tab_explorer`)

Interface pour explorer les tables Snowflake et lancer du SQL libre.

### Colonne gauche — Navigation dans les tables

```python
client = _get_client()
tables = client.list_tables(schema)  # ["CUSTOMERS", "PRODUCTS", "SALES"]

selected_table = st.selectbox("Sélectionner une table", tables)

if selected_table:
    schema_info = client.get_schema(selected_table, schema=schema)
    schema_df = pd.DataFrame(schema_info["columns"])
    st.dataframe(schema_df, use_container_width=True, hide_index=True)
    # Affiche : COLUMN_NAME | DATA_TYPE | NULLABLE
```

### Colonne droite — Éditeur SQL libre

```python
sql_query = st.text_area("SQL", value=f"SELECT * FROM {schema}.{selected_table} LIMIT 20", height=150)

if st.button("Exécuter"):
    df = client.execute_query(sql_query)
    st.success(f"{len(df)} lignes retournées")
    st.dataframe(df)
    
    # Bouton de téléchargement CSV
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Télécharger CSV", data=csv, file_name="query_results.csv")
```

---

## Cache Streamlit — `@st.cache_resource`

```python
@st.cache_resource(show_spinner="Connexion à Snowflake...")
def _get_client():
    from src.snowflake_client import get_client
    return get_client()

@st.cache_resource(show_spinner="Chargement des agents...")
def _get_orchestrator():
    from src.agents.orchestrator import Orchestrator
    return Orchestrator()
```

`@st.cache_resource` = la fonction n'est exécutée **qu'une seule fois** pour toute la durée de la session Streamlit, même si le script est rerun des dizaines de fois. C'est essentiel pour ne pas recréer une connexion Snowflake ou un Orchestrator à chaque interaction.

La différence avec `@st.cache_data` :
- `@st.cache_resource` : pour les ressources partagées (connexions, clients, modèles IA)
- `@st.cache_data` : pour les résultats de fonctions (données retournées)

---

## Lancer l'UI

```bash
py -3.11 -m streamlit run src/ui/app.py
# Accessible sur http://localhost:8501
```

Streamlit utilise le port **8501** par défaut.

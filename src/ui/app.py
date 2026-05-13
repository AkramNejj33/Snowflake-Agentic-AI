"""Streamlit UI — Chat, Ingestion, and Explorer tabs."""

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

# Ensure project root is on the Python path when running directly
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ------------------------------------------------------------------
# Page configuration (must be first Streamlit call)
# ------------------------------------------------------------------
st.set_page_config(
    page_title="Snowflake Agentic AI",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ------------------------------------------------------------------
# Lazy imports (avoid slow startup)
# ------------------------------------------------------------------
@st.cache_resource(show_spinner="Connexion à Snowflake...")
def _get_client():
    from src.snowflake_client import get_client
    return get_client()


@st.cache_resource(show_spinner="Chargement des agents...")
def _get_orchestrator():
    from src.agents.orchestrator import Orchestrator
    return Orchestrator()


# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
def _render_sidebar() -> str:
    """Render sidebar and return the selected schema."""
    with st.sidebar:
        st.title("❄️ Snowflake Agentic AI")
        st.divider()

        # Connection status
        st.subheader("Statut Snowflake")
        try:
            client = _get_client()
            healthy = client.is_healthy()
            if healthy:
                st.success("Connecté", icon="✅")
            else:
                st.error("Non connecté", icon="❌")
        except Exception as exc:
            st.error(f"Erreur : {exc}", icon="❌")

        st.divider()

        # Schema selector
        st.subheader("Schéma actif")
        schema = st.selectbox("Schéma Snowflake", ["RAW", "ANALYTICS"], index=0)

        st.divider()

        # Quick help
        with st.expander("Exemples de questions"):
            st.markdown(
                """
- Quels sont les 5 clients avec le plus de commandes ?
- Quelle est la catégorie de produit la plus vendue ce trimestre ?
- Donne-moi le CA mensuel des 6 derniers mois
- Combien de clients ont dépensé plus de 1000€ ?
- Quels produits ont un stock inférieur à 50 unités ?
                """
            )

        st.divider()
        st.caption("Propulsé par Claude Sonnet & Snowflake")

    return schema


# ------------------------------------------------------------------
# Tab 1 — Chat Data
# ------------------------------------------------------------------
def _tab_chat(schema: str) -> None:
    st.header("Posez vos questions sur les données")

    # Session state initialisation
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Render chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                _render_assistant_message(msg)
            else:
                st.write(msg["content"])

    # Chat input
    if prompt := st.chat_input("Ex: Quels sont les 10 produits les plus vendus ?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyse en cours..."):
                try:
                    orchestrator = _get_orchestrator()
                    result = orchestrator.handle_request(prompt)
                except Exception as exc:
                    result = {
                        "intent": "error",
                        "answer": f"Erreur : {exc}",
                        "sql": None,
                        "data": [],
                        "analysis": None,
                        "error": str(exc),
                    }

            _render_assistant_message(result)
            st.session_state.messages.append({**result, "role": "assistant"})

    # Reset button
    if st.session_state.messages:
        if st.button("Effacer la conversation", key="clear_chat"):
            st.session_state.messages = []
            st.rerun()


def _render_assistant_message(msg: dict[str, Any]) -> None:
    """Render a structured agent response inside a chat bubble."""
    answer = msg.get("answer", "")
    sql = msg.get("sql")
    data = msg.get("data", [])
    analysis = msg.get("analysis")
    error = msg.get("error")

    if error:
        st.error(f"Erreur : {error}")
        return

    # Main answer
    st.markdown(answer or "_Aucune réponse générée._")

    # SQL expandable
    if sql:
        with st.expander("SQL généré", expanded=False):
            st.code(sql, language="sql")

    # Data table
    if data and isinstance(data, list) and len(data) > 0:
        df = pd.DataFrame(data)
        with st.expander(f"Résultats ({len(df)} lignes)", expanded=True):
            st.dataframe(df, use_container_width=True)

    # Analysis
    if analysis and analysis != answer:
        with st.expander("Analyse détaillée", expanded=False):
            st.markdown(analysis)


# ------------------------------------------------------------------
# Tab 2 — Ingestion
# ------------------------------------------------------------------
def _tab_ingestion() -> None:
    st.header("Ingérer des données dans Snowflake")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Fichier CSV")
        uploaded = st.file_uploader("Glissez un fichier CSV", type=["csv"])
        table_name_csv = st.text_input("Nom de la table cible (RAW schema)", placeholder="EX: MY_TABLE")

        if uploaded:
            # Preview
            try:
                df_preview = pd.read_csv(uploaded)
                uploaded.seek(0)
                st.info(f"{len(df_preview)} lignes × {len(df_preview.columns)} colonnes")
                st.dataframe(df_preview.head(10), use_container_width=True)
            except Exception as exc:
                st.error(f"Erreur de lecture : {exc}")

            if st.button("Ingérer dans Snowflake", key="ingest_csv", type="primary"):
                with st.spinner("Ingestion en cours..."):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                        tmp.write(uploaded.read())
                        tmp_path = tmp.name

                    try:
                        orchestrator = _get_orchestrator()
                        report = orchestrator.ingestion_agent.ingest_csv(
                            file_path=tmp_path,
                            table_name=table_name_csv or Path(uploaded.name).stem.upper(),
                        )
                        Path(tmp_path).unlink(missing_ok=True)
                        _render_ingestion_report(report)
                    except Exception as exc:
                        st.error(f"Erreur : {exc}")

    with col2:
        st.subheader("URL API JSON")
        api_url = st.text_input("URL de l'API", placeholder="https://api.example.com/data")
        table_name_api = st.text_input("Nom de la table cible", placeholder="EX: API_DATA", key="tbl_api")
        json_key = st.text_input("Clé JSON (optionnel)", placeholder="Ex: 'results' ou 'data'")

        if api_url:
            if st.button("Tester l'API", key="test_api"):
                import httpx
                with st.spinner("Appel API..."):
                    try:
                        resp = httpx.get(api_url, timeout=10)
                        resp.raise_for_status()
                        data = resp.json()
                        st.success("API accessible")
                        st.json(data if isinstance(data, dict) else data[:3])
                    except Exception as exc:
                        st.error(f"Erreur : {exc}")

            if st.button("Ingérer depuis l'API", key="ingest_api", type="primary"):
                if not table_name_api:
                    st.warning("Spécifie un nom de table")
                else:
                    with st.spinner("Ingestion en cours..."):
                        try:
                            orchestrator = _get_orchestrator()
                            report = orchestrator.ingestion_agent.ingest_api(
                                url=api_url,
                                table_name=table_name_api,
                                json_key=json_key or None,
                            )
                            _render_ingestion_report(report)
                        except Exception as exc:
                            st.error(f"Erreur : {exc}")


def _render_ingestion_report(report: dict[str, Any]) -> None:
    """Display an ingestion report."""
    if report.get("success"):
        st.success(
            f"✅ {report.get('rows_inserted', 0)} lignes ingérées dans `{report.get('table')}`"
        )
    else:
        st.warning("⚠️ Ingestion partielle ou échouée")

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Lignes insérées", report.get("rows_inserted", 0))
    col_b.metric("Lignes échouées", report.get("rows_failed", 0))
    col_c.metric("Total", report.get("total_rows", 0))

    if report.get("ddl"):
        with st.expander("DDL créé"):
            st.code(report["ddl"], language="sql")

    if report.get("errors"):
        with st.expander("Erreurs"):
            for err in report["errors"]:
                st.error(err)


# ------------------------------------------------------------------
# Tab 3 — Explorer
# ------------------------------------------------------------------
def _tab_explorer(schema: str) -> None:
    st.header("Explorer les données Snowflake")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Tables disponibles")
        try:
            client = _get_client()
            tables = client.list_tables(schema)
            if not tables:
                st.info(f"Aucune table dans le schéma {schema}")
            else:
                selected_table = st.selectbox("Sélectionner une table", tables)
                if selected_table:
                    schema_info = client.get_schema(selected_table, schema=schema)
                    st.subheader(f"Schéma : {schema}.{selected_table}")
                    schema_df = pd.DataFrame(schema_info["columns"])
                    st.dataframe(schema_df, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"Erreur Snowflake : {exc}")

    with col2:
        st.subheader("Requête SQL libre")
        default_sql = f"SELECT * FROM {schema}.{tables[0] if 'tables' in dir() and tables else 'CUSTOMERS'} LIMIT 20"
        sql_query = st.text_area("SQL", value=default_sql, height=150)

        if st.button("Exécuter", key="run_sql", type="primary"):
            with st.spinner("Exécution..."):
                try:
                    client = _get_client()
                    df = client.execute_query(sql_query)
                    st.success(f"{len(df)} lignes retournées")
                    st.dataframe(df, use_container_width=True)

                    # Download button
                    csv = df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "Télécharger CSV",
                        data=csv,
                        file_name="query_results.csv",
                        mime="text/csv",
                    )
                except Exception as exc:
                    st.error(f"Erreur SQL : {exc}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main() -> None:
    schema = _render_sidebar()

    tab1, tab2, tab3 = st.tabs(["💬 Chat Data", "📥 Ingestion", "📊 Explorer"])

    with tab1:
        _tab_chat(schema)

    with tab2:
        _tab_ingestion()

    with tab3:
        _tab_explorer(schema)


if __name__ == "__main__":
    main()

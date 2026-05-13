"""Tests for agents — SQLAgent uses mocked Gemini API and Snowflake client."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ------------------------------------------------------------------
# Helpers to build fake Gemini responses
# ------------------------------------------------------------------

def _make_text_response(text: str):
    """Create a minimal fake Gemini response with a text part (no function calls)."""
    part = MagicMock()
    part.text = text
    part.function_call = None

    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content
    candidate.finish_reason = "STOP"

    response = MagicMock()
    response.candidates = [candidate]
    response.text = text
    return response


def _make_tool_call_response(tool_name: str, tool_args: dict):
    """Create a fake Gemini response that contains a single function_call part."""
    fc = MagicMock()
    fc.name = tool_name
    fc.args = tool_args

    part = MagicMock()
    part.text = None
    part.function_call = fc

    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content
    candidate.finish_reason = "STOP"  # finish_reason is STOP but part has function_call

    response = MagicMock()
    response.candidates = [candidate]
    response.text = None
    return response


# ------------------------------------------------------------------
# SQLAgent tests
# ------------------------------------------------------------------

class TestSQLAgent:
    @patch("src.agents.sql_agent.get_client")
    @patch("src.agents.base_agent.genai.Client")
    def test_simple_question_returns_json(self, mock_client_cls, mock_get_client):
        """SQLAgent.run should return a JSON string with sql + results + explanation."""
        # Mock Snowflake schema fetch
        mock_sf = MagicMock()
        mock_sf.get_all_schemas_info.return_value = "RAW.CUSTOMERS (...)"
        mock_get_client.return_value = mock_sf

        # Mock Gemini client
        mock_genai = MagicMock()
        mock_client_cls.return_value = mock_genai

        expected = {
            "sql": "SELECT COUNT(*) AS NB FROM RAW.CUSTOMERS",
            "results": [{"NB": 30}],
            "explanation": "Il y a 30 clients.",
        }
        mock_genai.models.generate_content.return_value = _make_text_response(
            json.dumps(expected)
        )

        from src.agents.sql_agent import SQLAgent
        agent = SQLAgent()
        result = json.loads(agent.run("Combien de clients avons-nous ?"))

        assert result["sql"] == expected["sql"]
        assert result["results"] == expected["results"]
        assert "clients" in result["explanation"]

    @patch("src.agents.sql_agent.get_client")
    @patch("src.agents.base_agent.genai.Client")
    def test_tool_call_then_text(self, mock_client_cls, mock_get_client):
        """SQLAgent should handle a function_call turn then a text turn."""
        mock_get_client.return_value.get_all_schemas_info.return_value = ""
        mock_genai = MagicMock()
        mock_client_cls.return_value = mock_genai

        final_json = json.dumps({
            "sql": "SELECT 1",
            "results": [{"COL": 1}],
            "explanation": "Résultat de test.",
        })
        # First call returns a function_call; second call returns final text
        mock_genai.models.generate_content.side_effect = [
            _make_tool_call_response("execute_sql", {"query": "SELECT 1"}),
            _make_text_response(final_json),
        ]

        with patch("src.tools.snowflake_tools.get_client") as mock_sf:
            import pandas as pd
            mock_sf.return_value.execute_query.return_value = pd.DataFrame([{"COL": 1}])

            from src.agents.sql_agent import SQLAgent
            agent = SQLAgent()
            result = json.loads(agent.run("Fais un SELECT 1"))

        assert mock_genai.models.generate_content.call_count == 2
        assert result["sql"] == "SELECT 1"

    @patch("src.agents.sql_agent.get_client")
    @patch("src.agents.base_agent.genai.Client")
    def test_agent_reset_clears_history(self, mock_client_cls, mock_get_client):
        """reset() must clear conversation_history."""
        mock_get_client.return_value.get_all_schemas_info.return_value = ""
        mock_client_cls.return_value = MagicMock()

        from src.agents.sql_agent import SQLAgent
        from google.genai import types
        agent = SQLAgent()
        agent.conversation_history = [types.Content(role="user", parts=[])]
        agent.reset()
        assert agent.conversation_history == []


# ------------------------------------------------------------------
# Orchestrator tests
# ------------------------------------------------------------------

class TestOrchestratorIntentClassification:
    @patch("src.agents.orchestrator.genai.Client")
    def test_routes_sql_question(self, mock_client_cls):
        """Orchestrator should detect sql_question intent."""
        mock_genai = MagicMock()
        mock_client_cls.return_value = mock_genai
        mock_genai.models.generate_content.return_value = _make_text_response("sql_question")

        from src.agents.orchestrator import Orchestrator
        orc = Orchestrator()
        assert orc._classify_intent("Combien de ventes ce mois-ci ?") == "sql_question"

    @patch("src.agents.orchestrator.genai.Client")
    def test_routes_ingestion(self, mock_client_cls):
        """Orchestrator should detect ingestion intent."""
        mock_genai = MagicMock()
        mock_client_cls.return_value = mock_genai
        mock_genai.models.generate_content.return_value = _make_text_response("ingestion")

        from src.agents.orchestrator import Orchestrator
        orc = Orchestrator()
        assert orc._classify_intent("Importe le fichier data.csv dans Snowflake") == "ingestion"

    @patch("src.agents.orchestrator.genai.Client")
    def test_falls_back_to_general(self, mock_client_cls):
        """Unknown responses should fall back to general."""
        mock_genai = MagicMock()
        mock_client_cls.return_value = mock_genai
        mock_genai.models.generate_content.return_value = _make_text_response("xyz_unknown")

        from src.agents.orchestrator import Orchestrator
        orc = Orchestrator()
        assert orc._classify_intent("Bonjour !") == "general"

    @patch("src.agents.orchestrator.genai.Client")
    def test_extract_csv_path(self, mock_client_cls):
        """_extract_ingestion_params should detect CSV path and table name."""
        mock_client_cls.return_value = MagicMock()
        from src.agents.orchestrator import Orchestrator
        orc = Orchestrator()
        params = orc._extract_ingestion_params(
            "Charge le fichier /data/sales.csv dans la table SALES_2025"
        )
        assert params["type"] == "csv"
        assert params["path"].endswith("sales.csv")
        assert params.get("table_name") == "SALES_2025"

    @patch("src.agents.orchestrator.genai.Client")
    def test_extract_api_url(self, mock_client_cls):
        """_extract_ingestion_params should detect API URL."""
        mock_client_cls.return_value = MagicMock()
        from src.agents.orchestrator import Orchestrator
        orc = Orchestrator()
        params = orc._extract_ingestion_params(
            "Ingère les données depuis https://api.example.com/products dans la table PRODUCTS_EXT"
        )
        assert params["type"] == "api"
        assert "api.example.com" in params["url"]


# ------------------------------------------------------------------
# Memory tools tests (no external dependencies)
# ------------------------------------------------------------------

class TestMemoryTools:
    def test_save_and_search(self, tmp_path, monkeypatch):
        """save_memory + recall_memory should work end-to-end."""
        monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
        monkeypatch.setenv("AGENT_STATE_DIR", str(tmp_path / "states"))

        import src.tools.memory_tools as mt
        mt._chroma_client = None  # reset singleton

        result = json.loads(mt.save_memory("test_key", "Ceci est un test de mémoire sémantique."))
        assert result["success"] is True

        search_result = json.loads(mt.recall_memory("mémoire sémantique"))
        assert "results" in search_result

    def test_save_agent_state(self, tmp_path, monkeypatch):
        """save_agent_state should create a JSON file and load it back."""
        monkeypatch.setenv("AGENT_STATE_DIR", str(tmp_path / "states"))

        import importlib
        import src.tools.memory_tools as mt
        importlib.reload(mt)

        result = json.loads(mt.save_agent_state("test_agent", {"key": "value", "count": 42}))
        assert result["success"] is True

        state = mt.load_agent_state("test_agent")
        assert state["key"] == "value"
        assert state["count"] == 42

"""Orchestrator — routes user requests to the correct agent(s) and chains responses."""

import json
import logging
from enum import Enum
from typing import Any

from google import genai
from google.genai import types

from src.config import settings
from src.agents.sql_agent import SQLAgent
from src.agents.analyst_agent import AnalystAgent
from src.agents.ingestion_agent import IngestionAgent
from src.tools.memory_tools import save_interaction, save_to_memory

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    SQL_QUESTION = "sql_question"
    ANALYSIS     = "analysis"
    INGESTION    = "ingestion"
    GENERAL      = "general"


_CLASSIFIER_PROMPT = """Classe l'intention de l'utilisateur parmi ces catégories :
- "sql_question" : l'utilisateur pose une question sur des données (ventes, clients, produits, chiffres, stats)
- "analysis" : l'utilisateur demande une analyse, des insights, des tendances, des recommandations
- "ingestion" : l'utilisateur veut importer, charger ou ingérer des données (CSV, fichier, API)
- "general" : toute autre question

Réponds UNIQUEMENT avec le mot-clé de la catégorie, rien d'autre."""


class Orchestrator:
    """Top-level controller that classifies intent and routes to the right agent.

    Agents are lazily instantiated on first use to avoid unnecessary
    Snowflake connections at startup.
    """

    def __init__(self) -> None:
        self._sql_agent: SQLAgent | None = None
        self._analyst_agent: AnalystAgent | None = None
        self._ingestion_agent: IngestionAgent | None = None
        self._genai_client = genai.Client(api_key=settings.google.api_key)

    # ------------------------------------------------------------------
    # Lazy agent accessors
    # ------------------------------------------------------------------

    @property
    def sql_agent(self) -> SQLAgent:
        if self._sql_agent is None:
            self._sql_agent = SQLAgent()
        return self._sql_agent

    @property
    def analyst_agent(self) -> AnalystAgent:
        if self._analyst_agent is None:
            self._analyst_agent = AnalystAgent()
        return self._analyst_agent

    @property
    def ingestion_agent(self) -> IngestionAgent:
        if self._ingestion_agent is None:
            self._ingestion_agent = IngestionAgent()
        return self._ingestion_agent

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def handle_request(self, user_input: str) -> dict[str, Any]:
        """Classify *user_input*, route to agent(s), and return a unified response.

        Args:
            user_input: Raw user message.

        Returns:
            Dict with keys: ``intent``, ``answer``, ``sql``, ``data``,
            ``analysis``, ``error`` (optional).
        """
        logger.info("[Orchestrator] Handling: %.100s", user_input)

        intent = self._classify_intent(user_input)
        logger.info("[Orchestrator] Intent: %s", intent)

        response: dict[str, Any] = {
            "intent": intent,
            "question": user_input,
            "answer": "",
            "sql": None,
            "data": [],
            "analysis": None,
            "error": None,
        }

        try:
            if intent == Intent.INGESTION:
                response = self._handle_ingestion(user_input, response)

            elif intent in (Intent.SQL_QUESTION, Intent.ANALYSIS):
                with_analysis = intent == Intent.ANALYSIS or user_input.startswith("[ANALYSE]")
                clean_input = user_input.removeprefix("[ANALYSE]").strip()
                response = self._handle_data_question(clean_input, response, with_analysis=with_analysis)

            else:
                response["answer"] = self._general_answer(user_input)

            # Persist interaction
            save_interaction(
                question=user_input,
                answer=response.get("answer", ""),
                sql=response.get("sql"),
                agent=intent,
            )
            save_to_memory(
                key=f"q_{abs(hash(user_input))}",
                content=f"Q: {user_input}\nA: {response.get('answer', '')[:500]}",
                metadata={"type": "interaction", "intent": intent},
            )

        except Exception as exc:
            logger.exception("[Orchestrator] Unhandled error")
            response["error"] = str(exc)
            response["answer"] = f"Une erreur inattendue s'est produite : {exc}"

        return response

    # ------------------------------------------------------------------
    # Request handlers
    # ------------------------------------------------------------------

    def _handle_data_question(
        self, user_input: str, response: dict[str, Any], with_analysis: bool
    ) -> dict[str, Any]:
        """Run SQLAgent, then optionally AnalystAgent."""
        sql_raw = self.sql_agent.run(user_input)
        sql_result = _parse_sql_result(sql_raw)
        response["sql"]    = sql_result.get("sql")
        response["data"]   = sql_result.get("results", [])
        response["answer"] = sql_result.get("explanation", sql_raw)

        if with_analysis and response["data"]:
            analysis = self.analyst_agent.analyse(
                data=response["data"],
                question=user_input,
                context=f"SQL: {response['sql']}",
            )
            response["analysis"] = analysis
            response["answer"]   = analysis

        return response

    def _handle_ingestion(self, user_input: str, response: dict[str, Any]) -> dict[str, Any]:
        """Extract ingestion parameters and run IngestionAgent."""
        params = self._extract_ingestion_params(user_input)
        source_type = params.get("type", "unknown")

        if source_type == "csv":
            report = self.ingestion_agent.ingest_csv(
                file_path=params.get("path", ""),
                table_name=params.get("table_name"),
            )
        elif source_type == "api":
            report = self.ingestion_agent.ingest_api(
                url=params.get("url", ""),
                table_name=params.get("table_name", "IMPORTED_DATA"),
                json_key=params.get("json_key"),
            )
        else:
            response["answer"] = (
                "Je n'ai pas pu identifier la source de données. "
                "Précise le chemin d'un fichier CSV ou une URL d'API."
            )
            return response

        inserted = report.get("rows_inserted", 0)
        table = report.get("table", "")
        errors = report.get("errors", [])
        response["answer"] = (
            f"✅ Ingestion terminée : {inserted} lignes chargées dans `{table}`."
            if not errors
            else f"⚠️ Ingestion partielle : {inserted} lignes chargées. Erreurs : {errors}"
        )
        response["data"] = [report]
        return response

    # ------------------------------------------------------------------
    # Intent classification (Gemini)
    # ------------------------------------------------------------------

    def _classify_intent(self, user_input: str) -> str:
        """Use Gemini to classify the user's intent."""
        try:
            resp = self._genai_client.models.generate_content(
                model=settings.google.model,
                contents=user_input,
                config=types.GenerateContentConfig(
                    system_instruction=_CLASSIFIER_PROMPT,
                    temperature=0.0,
                    max_output_tokens=20,
                ),
            )
            raw = resp.text.strip().lower()
            for intent in Intent:
                if intent.value in raw:
                    return intent.value
        except Exception as exc:
            logger.warning("[Orchestrator] Intent classification failed: %s", exc)
        return Intent.GENERAL

    def _extract_ingestion_params(self, user_input: str) -> dict[str, Any]:
        """Extract file path / URL and table name from *user_input*."""
        import re
        params: dict[str, Any] = {}

        csv_match = re.search(r'(["\']?)([^\s"\']+\.csv)\1', user_input, re.IGNORECASE)
        if csv_match:
            params["type"] = "csv"
            params["path"] = csv_match.group(2)

        url_match = re.search(r"https?://[^\s\"']+", user_input, re.IGNORECASE)
        if url_match:
            params["type"] = "api"
            params["url"] = url_match.group(0)

        table_match = re.search(
            r"(?:table|dans|vers|into)\s+([A-Za-z_][A-Za-z0-9_]*)", user_input, re.IGNORECASE
        )
        if table_match:
            params["table_name"] = table_match.group(1).upper()

        return params

    def _general_answer(self, user_input: str) -> str:
        """Answer a general question with Gemini directly."""
        try:
            resp = self._genai_client.models.generate_content(
                model=settings.google.model,
                contents=user_input,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "Tu es un assistant data expert spécialisé dans Snowflake et l'analyse de données. "
                        "Réponds de manière concise et utile en français."
                    ),
                    max_output_tokens=1024,
                ),
            )
            return resp.text.strip()
        except Exception as exc:
            return f"Erreur lors de la génération de réponse : {exc}"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_sql_result(raw: str) -> dict[str, Any]:
    """Try to parse a JSON SQL result; fall back to plain text."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"sql": None, "results": [], "explanation": raw}

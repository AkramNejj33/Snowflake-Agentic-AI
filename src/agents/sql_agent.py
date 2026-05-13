"""SQL Agent — Text-to-SQL with auto-schema enrichment and error self-correction."""

import json
import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.snowflake_client import get_client
from src.tools.snowflake_tools import SNOWFLAKE_TOOL_FUNCTIONS, dispatch_snowflake_tool

logger = logging.getLogger(__name__)

_BASE_SYSTEM = """Tu es un expert SQL Snowflake. Ton rôle est de convertir des questions en langage naturel en requêtes SQL Snowflake valides et optimisées.

RÈGLES IMPÉRATIVES :
1. Utilise TOUJOURS les noms de tables pleinement qualifiés : RAW.SALES, RAW.CUSTOMERS, RAW.PRODUCTS, ANALYTICS.SALES_SUMMARY, ANALYTICS.CUSTOMER_LTV.
2. Avant d'écrire une requête, utilise get_table_schema pour vérifier les colonnes disponibles si tu as un doute.
3. Ajoute LIMIT 100 par défaut sauf si l'utilisateur demande explicitement tous les résultats.
4. Si une requête échoue, analyse l'erreur et corrige le SQL automatiquement (max 3 tentatives).
5. Retourne TOUJOURS ta réponse au format JSON : {"sql": "...", "results": [...], "explanation": "..."}.
6. Écris des requêtes efficaces : utilise les bons types de JOINs, évite les SELECT *.
7. Les dates sont au format DATE (YYYY-MM-DD) dans Snowflake.
8. Pour les agrégations, utilise des alias clairs (AS total_revenue, AS nb_orders, etc.).

SCHÉMA DISPONIBLE :
{schema_context}

Réponds toujours en français dans la partie "explanation"."""

_MAX_SQL_RETRIES = 3


class SQLAgent(BaseAgent):
    """Agent that translates natural language questions into Snowflake SQL.

    Automatically enriches its system prompt with the live table schema at
    construction time, and retries failed SQL queries with error context.
    """

    def __init__(self) -> None:
        schema_context = self._fetch_schema_context()
        system_prompt = _BASE_SYSTEM.format(schema_context=schema_context)
        super().__init__(
            name="SQLAgent",
            system_prompt=system_prompt,
            tools=SNOWFLAKE_TOOL_FUNCTIONS,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, user_message: str) -> str:
        """Convert *user_message* to SQL, execute it, and return structured JSON.

        Overrides BaseAgent.run to add SQL error auto-correction logic.

        Args:
            user_message: Natural-language question about the data.

        Returns:
            JSON string: ``{"sql": "...", "results": [...], "explanation": "..."}``.
        """
        for attempt in range(1, _MAX_SQL_RETRIES + 1):
            result = super().run(user_message)

            parsed = _try_parse_json(result)
            if parsed is None:
                return json.dumps({"sql": None, "results": [], "explanation": result})

            if "error" not in parsed:
                return json.dumps(parsed, default=str)

            if attempt < _MAX_SQL_RETRIES:
                error_msg = parsed.get("error", "unknown error")
                logger.warning(
                    "[SQLAgent] SQL error on attempt %d/%d: %s",
                    attempt, _MAX_SQL_RETRIES, error_msg,
                )
                user_message = (
                    f"La requête a échoué avec l'erreur suivante : {error_msg}\n"
                    f"Corrige le SQL et réessaie."
                )
            else:
                logger.error("[SQLAgent] Failed after %d attempts", _MAX_SQL_RETRIES)
                return json.dumps(parsed, default=str)

        return json.dumps({"sql": None, "results": [], "explanation": "Échec après plusieurs tentatives."})

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        return dispatch_snowflake_tool(tool_name, tool_input)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_schema_context() -> str:
        """Fetch live schema info from Snowflake to inject into the system prompt."""
        try:
            client = get_client()
            return client.get_all_schemas_info(["RAW", "ANALYTICS"])
        except Exception as exc:
            logger.warning("[SQLAgent] Could not fetch schema: %s — using placeholder", exc)
            return (
                "RAW.CUSTOMERS (CUSTOMER_ID, FIRST_NAME, LAST_NAME, EMAIL, SEGMENT, CITY)\n"
                "RAW.PRODUCTS  (PRODUCT_ID, PRODUCT_NAME, CATEGORY, UNIT_PRICE, STOCK_QTY)\n"
                "RAW.SALES     (SALE_ID, CUSTOMER_ID, PRODUCT_ID, QUANTITY, TOTAL_AMOUNT, SALE_DATE, CHANNEL, STATUS)\n"
                "ANALYTICS.SALES_SUMMARY  (SALE_DATE, CATEGORY, NB_TRANSACTIONS, TOTAL_REVENUE)\n"
                "ANALYTICS.CUSTOMER_LTV   (CUSTOMER_ID, FULL_NAME, SEGMENT, LIFETIME_VALUE)\n"
            )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _try_parse_json(text: str) -> dict[str, Any] | None:
    """Try to extract and parse the first JSON object in *text*."""
    text = text.strip()
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    idx = text.find("{")
    if idx != -1:
        try:
            return json.loads(text[idx:])
        except json.JSONDecodeError:
            pass
    return None

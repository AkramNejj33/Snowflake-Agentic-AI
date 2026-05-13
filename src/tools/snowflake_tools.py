"""Snowflake tools — Python functions passed directly to Gemini for tool calling.

Gemini extracts the JSON schema automatically from type hints and docstrings.
The same functions are also called manually via ``dispatch_snowflake_tool``.
"""

import json
import logging
from typing import Any

from src.snowflake_client import get_client

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Tool functions (Gemini reads signatures + docstrings as schema)
# ------------------------------------------------------------------

def execute_sql(query: str) -> str:
    """Execute a SQL query on Snowflake and return results as JSON.

    Always use fully qualified table names (e.g. RAW.SALES, ANALYTICS.SALES_SUMMARY).
    Add LIMIT 100 unless the user explicitly requests all rows.

    Args:
        query: Valid Snowflake SQL statement to execute.

    Returns:
        JSON string with keys: success, rows (list of dicts), row_count.
    """
    client = get_client()
    try:
        df = client.execute_query(query)
        rows = _json_safe(df.to_dict(orient="records"))
        logger.info("execute_sql OK: %d rows | %.200s", len(rows), query)
        return json.dumps({"success": True, "rows": rows, "row_count": len(rows)})
    except Exception as exc:
        logger.error("execute_sql FAILED: %s | %.200s", exc, query)
        return json.dumps({"success": False, "error": str(exc)})


def get_table_schema(table_name: str, schema: str = "RAW") -> str:
    """Return column metadata for a Snowflake table or view.

    Call this before writing a SQL query to verify column names and types.

    Args:
        table_name: Table name, qualified or not (e.g. 'SALES' or 'RAW.SALES').
        schema: Snowflake schema name (e.g. 'RAW', 'ANALYTICS').

    Returns:
        JSON string with keys: table, schema, columns (list of {name, type, nullable}).
    """
    client = get_client()
    try:
        info = client.get_schema(table_name, schema=schema)
        return json.dumps({"success": True, **info})
    except Exception as exc:
        logger.error("get_table_schema FAILED for %s: %s", table_name, exc)
        return json.dumps({"success": False, "error": str(exc)})


def list_tables(schema: str = "RAW") -> str:
    """List all tables and views available in a Snowflake schema.

    Args:
        schema: Snowflake schema to explore (e.g. 'RAW', 'ANALYTICS').

    Returns:
        JSON string with keys: success, schema, tables (list of names).
    """
    client = get_client()
    try:
        tables = client.list_tables(schema)
        return json.dumps({"success": True, "schema": schema.upper(), "tables": tables})
    except Exception as exc:
        logger.error("list_tables FAILED for schema %s: %s", schema, exc)
        return json.dumps({"success": False, "error": str(exc)})


# List of callables passed to Gemini (replaces JSON schema dicts)
SNOWFLAKE_TOOL_FUNCTIONS = [execute_sql, get_table_schema, list_tables]


# ------------------------------------------------------------------
# Dispatcher (used by _execute_tool in agents)
# ------------------------------------------------------------------

def dispatch_snowflake_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Route *tool_name* to the correct Python function.

    Args:
        tool_name: One of ``execute_sql``, ``get_table_schema``, ``list_tables``.
        tool_input: Arguments dict matching the function's signature.

    Returns:
        JSON string result.
    """
    handlers: dict[str, Any] = {
        "execute_sql":      lambda i: execute_sql(i["query"]),
        "get_table_schema": lambda i: get_table_schema(i["table_name"], i.get("schema", "RAW")),
        "list_tables":      lambda i: list_tables(i.get("schema", "RAW")),
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"})
    return handler(tool_input)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _json_safe(obj: Any) -> Any:
    """Recursively convert non-JSON-serialisable types."""
    import decimal
    import datetime

    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return obj

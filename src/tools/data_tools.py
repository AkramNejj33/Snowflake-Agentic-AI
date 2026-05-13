"""Data ingestion tools — CSV file loading and external API fetching.

Functions are passed directly to Gemini; schemas are auto-extracted from
type hints and docstrings.
"""

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Tool functions
# ------------------------------------------------------------------

def fetch_csv(file_path: str, separator: str = ",", encoding: str = "utf-8") -> str:
    """Read a local CSV file and return a preview with column types and statistics.

    Use this tool to inspect a file before ingesting it into Snowflake.

    Args:
        file_path: Absolute or relative path to the CSV file.
        separator: Column delimiter character (default: comma).
        encoding: File encoding (default: utf-8).

    Returns:
        JSON string with keys: columns, dtypes, row_count, preview (first 5 rows), null_counts.
    """
    path = Path(file_path)
    if not path.exists():
        return json.dumps({"success": False, "error": f"File not found: {file_path}"})

    try:
        df = pd.read_csv(path, sep=separator, encoding=encoding)
        summary = {
            "success": True,
            "file_path": str(path.resolve()),
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "preview": df.head(5).to_dict(orient="records"),
            "null_counts": df.isnull().sum().to_dict(),
            "stats": _safe_describe(df),
        }
        return json.dumps(summary, default=str)
    except Exception as exc:
        logger.error("fetch_csv FAILED for %s: %s", file_path, exc)
        return json.dumps({"success": False, "error": str(exc)})


def call_external_api(url: str, method: str = "GET") -> str:
    """Call an external HTTP API and return the JSON response data.

    Args:
        url: Full URL of the API endpoint (https://...).
        method: HTTP method, either 'GET' or 'POST'.

    Returns:
        JSON string with keys: success, status_code, data.
    """
    method = method.upper()
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url) if method == "GET" else client.post(url)
        resp.raise_for_status()
        return json.dumps({"success": True, "status_code": resp.status_code, "data": resp.json()}, default=str)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"success": False, "error": f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"})
    except Exception as exc:
        logger.error("call_external_api FAILED for %s: %s", url, exc)
        return json.dumps({"success": False, "error": str(exc)})


# List of callables passed to Gemini
DATA_TOOL_FUNCTIONS = [fetch_csv, call_external_api]


# ------------------------------------------------------------------
# Dispatcher
# ------------------------------------------------------------------

def dispatch_data_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Route *tool_name* to the correct data tool function."""
    handlers: dict[str, Any] = {
        "fetch_csv": lambda i: fetch_csv(
            i["file_path"], i.get("separator", ","), i.get("encoding", "utf-8")
        ),
        "call_external_api": lambda i: call_external_api(
            i["url"], i.get("method", "GET")
        ),
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return json.dumps({"success": False, "error": f"Unknown data tool: {tool_name}"})
    return handler(tool_input)


# ------------------------------------------------------------------
# Internal helper (used directly by IngestionAgent)
# ------------------------------------------------------------------

def load_csv_as_dataframe(file_path: str, separator: str = ",", encoding: str = "utf-8") -> pd.DataFrame:
    """Load a CSV file and return a pandas DataFrame."""
    return pd.read_csv(file_path, sep=separator, encoding=encoding)


def _safe_describe(df: pd.DataFrame) -> dict[str, Any]:
    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        return {}
    return numeric.describe().round(2).to_dict()

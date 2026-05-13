"""Ingestion Agent — detects schema, creates Snowflake tables, and loads data in batches."""

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.agents.base_agent import BaseAgent
from src.snowflake_client import get_client
from src.tools.data_tools import DATA_TOOL_FUNCTIONS, dispatch_data_tool, load_csv_as_dataframe

logger = logging.getLogger(__name__)

_BATCH_SIZE = 1000

_SYSTEM_PROMPT = """Tu es un expert en ingestion de données Snowflake.

Ton rôle est d'analyser des données (CSV ou API) et de :
1. Détecter le schéma des données (noms de colonnes, types)
2. Générer le DDL Snowflake adapté (CREATE TABLE IF NOT EXISTS)
3. Valider que les données sont propres avant insertion
4. Générer un rapport d'ingestion détaillé

RÈGLES :
- Toujours utiliser RAW.{table_name} comme destination
- Mapper les types Python/pandas vers les types Snowflake corrects :
  * int64 → NUMBER(18,0)
  * float64 → NUMBER(18,4)
  * object/string → VARCHAR(500)
  * datetime → TIMESTAMP_NTZ
  * bool → BOOLEAN
  * date → DATE
- Ajouter une colonne INGESTED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
- Retourner un rapport JSON : {"table_created": bool, "rows_inserted": int, "errors": [...], "ddl": "..."}
"""


class IngestionAgent(BaseAgent):
    """Agent that ingests CSV files or API data into Snowflake.

    Workflow:
    1. Load data via ``fetch_csv`` or ``call_external_api`` tool.
    2. Detect schema and generate Snowflake DDL.
    3. Create the target table if it does not exist.
    4. Insert data in batches of 1 000 rows.
    5. Return a structured ingestion report.
    """

    def __init__(self) -> None:
        super().__init__(
            name="IngestionAgent",
            system_prompt=_SYSTEM_PROMPT,
            tools=DATA_TOOL_FUNCTIONS,
        )

    # ------------------------------------------------------------------
    # Main ingestion entry points
    # ------------------------------------------------------------------

    def ingest_csv(self, file_path: str, table_name: str | None = None) -> dict[str, Any]:
        """Ingest a CSV file into Snowflake.

        Args:
            file_path: Path to the CSV file.
            table_name: Target table name (defaults to the file stem in uppercase).

        Returns:
            Ingestion report dict.
        """
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        target_table = (table_name or path.stem.upper()).upper()

        try:
            df = load_csv_as_dataframe(file_path)
        except Exception as exc:
            return {"success": False, "error": f"CSV read error: {exc}"}

        return self._ingest_dataframe(df, target_table, source=str(path.resolve()))

    def ingest_api(self, url: str, table_name: str, json_key: str | None = None) -> dict[str, Any]:
        """Fetch data from an API and ingest it into Snowflake.

        Args:
            url: API endpoint URL.
            table_name: Target Snowflake table name.
            json_key: Optional key to extract the records list from the JSON response.

        Returns:
            Ingestion report dict.
        """
        import httpx

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            return {"success": False, "error": f"API fetch error: {exc}"}

        records = data.get(json_key, data) if json_key else data
        if not isinstance(records, list):
            records = [records]

        if not records:
            return {"success": False, "error": "API returned empty data"}

        df = pd.DataFrame(records)
        return self._ingest_dataframe(df, table_name.upper(), source=url)

    # ------------------------------------------------------------------
    # Core ingestion logic
    # ------------------------------------------------------------------

    def _ingest_dataframe(
        self, df: pd.DataFrame, table_name: str, source: str = ""
    ) -> dict[str, Any]:
        """Create table if needed and insert *df* into Snowflake.

        Args:
            df: Data to ingest.
            table_name: Unqualified target table name (placed in RAW schema).
            source: Source label for the report.

        Returns:
            Ingestion report dict.
        """
        client = get_client()
        fqn = f"RAW.{table_name}"
        report: dict[str, Any] = {
            "source": source,
            "table": fqn,
            "total_rows": len(df),
            "rows_inserted": 0,
            "rows_failed": 0,
            "errors": [],
            "ddl": "",
            "table_created": False,
        }

        # 1. Clean column names
        df = _sanitise_columns(df)

        # 2. Generate and execute DDL
        ddl = _generate_ddl(df, fqn)
        report["ddl"] = ddl
        try:
            client.execute_query(ddl)
            report["table_created"] = True
            logger.info("[IngestionAgent] Table ready: %s", fqn)
        except Exception as exc:
            report["errors"].append(f"DDL error: {exc}")
            return {**report, "success": False}

        # 3. Insert in batches
        for batch_start in range(0, len(df), _BATCH_SIZE):
            batch = df.iloc[batch_start : batch_start + _BATCH_SIZE]
            try:
                rows_ok = _insert_batch(client, fqn, batch)
                report["rows_inserted"] += rows_ok
            except Exception as exc:
                error_msg = f"Batch {batch_start}–{batch_start + len(batch)}: {exc}"
                logger.error("[IngestionAgent] %s", error_msg)
                report["errors"].append(error_msg)
                report["rows_failed"] += len(batch)

        report["success"] = report["rows_failed"] == 0
        logger.info(
            "[IngestionAgent] Done: %d/%d rows inserted into %s",
            report["rows_inserted"], report["total_rows"], fqn,
        )
        return report

    def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        return dispatch_data_tool(tool_name, tool_input)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _sanitise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise column names to uppercase Snowflake-safe identifiers."""
    import re

    df = df.copy()
    new_cols = []
    for col in df.columns:
        clean = re.sub(r"[^A-Za-z0-9_]", "_", str(col)).upper().strip("_")
        clean = re.sub(r"_+", "_", clean)
        new_cols.append(clean or f"COL_{len(new_cols)}")
    df.columns = new_cols
    return df


def _pandas_dtype_to_snowflake(dtype: str) -> str:
    """Map a pandas dtype string to a Snowflake SQL type."""
    dtype = dtype.lower()
    if "int" in dtype:
        return "NUMBER(18,0)"
    if "float" in dtype:
        return "NUMBER(18,4)"
    if "bool" in dtype:
        return "BOOLEAN"
    if "datetime" in dtype:
        return "TIMESTAMP_NTZ"
    if "date" in dtype:
        return "DATE"
    return "VARCHAR(500)"


def _generate_ddl(df: pd.DataFrame, fqn: str) -> str:
    """Generate a CREATE TABLE IF NOT EXISTS DDL for *df*."""
    col_defs = [
        f"    {col} {_pandas_dtype_to_snowflake(str(dtype))} NULL"
        for col, dtype in df.dtypes.items()
    ]
    col_defs.append("    INGESTED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()")
    cols_sql = ",\n".join(col_defs)
    return f"CREATE TABLE IF NOT EXISTS {fqn} (\n{cols_sql}\n);"


def _insert_batch(client: Any, fqn: str, batch: pd.DataFrame) -> int:
    """Insert one batch of rows using parameterised INSERT statements.

    Returns the number of rows inserted.
    """
    if batch.empty:
        return 0

    cols = ", ".join(batch.columns)
    placeholders = ", ".join(["%s"] * len(batch.columns))
    sql = f"INSERT INTO {fqn} ({cols}) VALUES ({placeholders})"

    client._ensure_connected()
    with client._conn.cursor() as cur:
        data = [tuple(row) for row in batch.itertuples(index=False, name=None)]
        cur.executemany(sql, data)
    return len(batch)

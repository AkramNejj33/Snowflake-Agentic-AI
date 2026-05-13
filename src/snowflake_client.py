"""Snowflake client — singleton with retry, query execution, and schema introspection."""

import logging
import threading
from typing import Any

import pandas as pd
import snowflake.connector
from snowflake.connector import DictCursor, ProgrammingError, OperationalError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from src.config import settings

logger = logging.getLogger(__name__)

_RETRYABLE = (OperationalError,)


class SnowflakeClient:
    """Thread-safe singleton Snowflake client."""

    _instance: "SnowflakeClient | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "SnowflakeClient":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = object.__new__(cls)
                    obj._conn = None
                    cls._instance = obj
        return cls._instance

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Open a new Snowflake connection."""
        sf = settings.snowflake
        self._conn = snowflake.connector.connect(
            account=sf.account,
            user=sf.user,
            password=sf.password,
            database=sf.database,
            schema=sf.schema_,
            warehouse=sf.warehouse,
            role=sf.role,
            session_parameters={"QUERY_TAG": "agentic-ai"},
        )
        logger.info("Snowflake connection established (account=%s)", sf.account)

    def _ensure_connected(self) -> None:
        """Reconnect if the connection is closed or was never opened."""
        if self._conn is None or self._conn.is_closed():
            self._connect()

    def close(self) -> None:
        """Close the underlying connection."""
        if self._conn and not self._conn.is_closed():
            self._conn.close()
            logger.info("Snowflake connection closed")

    def is_healthy(self) -> bool:
        """Return True if the connection is alive."""
        try:
            self._ensure_connected()
            self._conn.cursor().execute("SELECT 1")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def execute_query(self, sql: str, params: tuple[Any, ...] | None = None) -> pd.DataFrame:
        """Execute *sql* and return results as a pandas DataFrame.

        Args:
            sql: SQL statement to run.
            params: Optional positional parameters for parameterized queries.

        Returns:
            DataFrame with query results (empty DataFrame for DDL/DML).

        Raises:
            ProgrammingError: On SQL syntax or permission errors (not retried).
            OperationalError: On transient connection errors (retried up to 3×).
        """
        self._ensure_connected()
        try:
            with self._conn.cursor(DictCursor) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                if rows:
                    return pd.DataFrame(rows)
                # DDL/DML — return empty frame with column descriptions if available
                if cur.description:
                    cols = [d.name for d in cur.description]
                    return pd.DataFrame(columns=cols)
                return pd.DataFrame()
        except ProgrammingError as exc:
            logger.error("SQL error: %s | query: %.500s", exc, sql)
            raise

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    def get_schema(self, table_name: str, schema: str | None = None) -> dict[str, Any]:
        """Return column metadata for *table_name*.

        Args:
            table_name: Table name (unqualified or fully qualified).
            schema: Optional schema override; defaults to the configured schema.

        Returns:
            Dict with keys ``table``, ``schema``, ``columns``.
            Each column entry: ``{name, type, nullable, primary_key}``.
        """
        target_schema = schema or settings.snowflake.schema_
        # Support fully qualified names like SCHEMA.TABLE
        if "." in table_name:
            parts = table_name.split(".")
            target_schema, table_name = parts[-2], parts[-1]

        sql = """
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                IS_NULLABLE,
                COLUMN_DEFAULT,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %(schema)s
              AND TABLE_NAME   = %(table)s
            ORDER BY ORDINAL_POSITION
        """
        df = self.execute_query(
            sql,
            params=None,  # use string interpolation via cursor.execute
        )
        # Re-execute with dict params (Snowflake connector supports %(...) style)
        self._ensure_connected()
        with self._conn.cursor(DictCursor) as cur:
            cur.execute(
                sql,
                {"schema": target_schema.upper(), "table": table_name.upper()},
            )
            rows = cur.fetchall()

        columns = [
            {
                "name": r["COLUMN_NAME"],
                "type": r["DATA_TYPE"],
                "nullable": r["IS_NULLABLE"] == "YES",
                "default": r["COLUMN_DEFAULT"],
            }
            for r in rows
        ]
        return {"table": table_name.upper(), "schema": target_schema.upper(), "columns": columns}

    def list_tables(self, schema: str | None = None) -> list[str]:
        """Return table names in *schema* (default: configured schema).

        Args:
            schema: Target schema name.

        Returns:
            Sorted list of table names (unqualified).
        """
        target_schema = (schema or settings.snowflake.schema_).upper()
        sql = """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %(schema)s
              AND TABLE_TYPE IN ('BASE TABLE', 'VIEW')
            ORDER BY TABLE_NAME
        """
        self._ensure_connected()
        with self._conn.cursor(DictCursor) as cur:
            cur.execute(sql, {"schema": target_schema})
            rows = cur.fetchall()
        return [r["TABLE_NAME"] for r in rows]

    def get_all_schemas_info(self, schemas: list[str] | None = None) -> str:
        """Return a formatted string of all table schemas — used for LLM context.

        Args:
            schemas: List of schema names to introspect. Defaults to RAW + ANALYTICS.

        Returns:
            Multi-line string ready to be injected into a system prompt.
        """
        target_schemas = schemas or ["RAW", "ANALYTICS"]
        lines: list[str] = []

        for schema in target_schemas:
            try:
                tables = self.list_tables(schema)
            except Exception as exc:
                logger.warning("Could not list tables in schema %s: %s", schema, exc)
                continue

            for table in tables:
                try:
                    info = self.get_schema(table, schema=schema)
                except Exception as exc:
                    logger.warning("Could not get schema for %s.%s: %s", schema, table, exc)
                    continue

                fqn = f"{schema}.{table}"
                lines.append(f"Table: {fqn}")
                for col in info["columns"]:
                    nullable = "NULL" if col["nullable"] else "NOT NULL"
                    lines.append(f"  - {col['name']} ({col['type']}, {nullable})")
                lines.append("")

        return "\n".join(lines)


# Module-level singleton accessor
def get_client() -> SnowflakeClient:
    """Return the shared SnowflakeClient instance."""
    return SnowflakeClient()

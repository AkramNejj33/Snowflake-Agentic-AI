"""FastAPI route definitions."""

import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from src.agents.orchestrator import Orchestrator
from src.snowflake_client import get_client
from src.tools.memory_tools import load_history

logger = logging.getLogger(__name__)

router = APIRouter()

# Shared orchestrator instance (lives for the duration of the process)
_orchestrator: Orchestrator | None = None


def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


# ------------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Natural-language question about data")
    with_analysis: bool = Field(False, description="Also run AnalystAgent on the results")


class AskResponse(BaseModel):
    intent: str
    question: str
    answer: str
    sql: str | None
    data: list[dict[str, Any]]
    analysis: str | None
    error: str | None


class IngestURLRequest(BaseModel):
    url: str = Field(..., description="HTTP URL returning JSON data")
    table_name: str = Field(..., description="Target Snowflake table name (RAW schema)")
    json_key: str | None = Field(None, description="JSON key containing the records list")


class HealthResponse(BaseModel):
    status: str
    snowflake_connected: bool
    database: str
    warehouse: str


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health() -> HealthResponse:
    """Check Snowflake connectivity and application status."""
    from src.config import settings
    client = get_client()
    connected = client.is_healthy()
    return HealthResponse(
        status="ok" if connected else "degraded",
        snowflake_connected=connected,
        database=settings.snowflake.database,
        warehouse=settings.snowflake.warehouse,
    )


@router.post("/ask", response_model=AskResponse, tags=["Agents"])
async def ask(request: AskRequest) -> AskResponse:
    """Submit a natural-language question to the Orchestrator.

    The orchestrator classifies the intent, routes to the correct agent(s),
    and returns the answer along with the generated SQL and data.
    """
    orchestrator = _get_orchestrator()

    # Override intent to force analysis if requested
    user_input = request.question
    if request.with_analysis:
        user_input = f"[ANALYSE] {user_input}"

    result = orchestrator.handle_request(user_input)
    return AskResponse(**{k: result.get(k) for k in AskResponse.model_fields})


@router.post("/ingest/csv", tags=["Ingestion"])
async def ingest_csv(
    file: UploadFile = File(..., description="CSV file to ingest"),
    table_name: str | None = None,
) -> dict[str, Any]:
    """Upload a CSV file and ingest it into Snowflake (RAW schema)."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    # Write upload to a temp file
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    orchestrator = _get_orchestrator()
    report = orchestrator.ingestion_agent.ingest_csv(
        file_path=tmp_path,
        table_name=table_name or Path(file.filename).stem.upper(),
    )

    # Cleanup temp file
    Path(tmp_path).unlink(missing_ok=True)
    return report


@router.post("/ingest/url", tags=["Ingestion"])
async def ingest_url(request: IngestURLRequest) -> dict[str, Any]:
    """Fetch data from an external JSON API and ingest it into Snowflake."""
    orchestrator = _get_orchestrator()
    return orchestrator.ingestion_agent.ingest_api(
        url=request.url,
        table_name=request.table_name,
        json_key=request.json_key,
    )


@router.get("/tables", tags=["Data"])
async def list_tables(schema: str = "RAW") -> dict[str, Any]:
    """List all tables and views in the given Snowflake schema."""
    client = get_client()
    try:
        tables = client.list_tables(schema)
        return {"schema": schema.upper(), "tables": tables}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/tables/{schema}/{table}/schema", tags=["Data"])
async def get_table_schema(schema: str, table: str) -> dict[str, Any]:
    """Return column metadata for a specific Snowflake table."""
    client = get_client()
    try:
        return client.get_schema(table, schema=schema)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/history", tags=["Data"])
async def get_history(limit: int = 20) -> list[dict[str, Any]]:
    """Return the most recent user interactions (from local JSON log)."""
    return load_history(limit=min(limit, 100))


@router.post("/sql", tags=["Agents"])
async def run_sql(body: dict[str, str]) -> dict[str, Any]:
    """Execute a raw SQL query on Snowflake (for power users / debugging).

    Body: ``{"query": "SELECT ..."}``
    """
    sql = (body.get("query") or "").strip()
    if not sql:
        raise HTTPException(status_code=400, detail="Field 'query' is required")

    client = get_client()
    try:
        df = client.execute_query(sql)
        return {
            "success": True,
            "row_count": len(df),
            "rows": df.to_dict(orient="records"),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

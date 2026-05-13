"""Memory tools — ChromaDB semantic memory + JSON agent state persistence.

Also exports Anthropic tool definitions (MEMORY_TOOLS_DEFINITIONS) and
a dispatcher (dispatch_memory_tool) for use by agents.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config import settings as app_settings

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# ChromaDB client (lazy singleton)
# ------------------------------------------------------------------

_chroma_client: chromadb.ClientAPI | None = None


def _get_chroma_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        persist_dir = app_settings.app.chroma_persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


def _get_collection(name: str = "agent_memory") -> chromadb.Collection:
    client = _get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


# ------------------------------------------------------------------
# Semantic memory (ChromaDB)
# ------------------------------------------------------------------

def save_to_memory(key: str, content: str, metadata: dict[str, Any] | None = None) -> str:
    """Persist *content* to ChromaDB with *key* as document id.

    Args:
        key: Unique identifier for this memory entry.
        content: Text content to embed and store.
        metadata: Optional dict of extra metadata (tags, agent name, etc.).

    Returns:
        JSON string confirming success or describing the error.
    """
    collection = _get_collection()
    meta = {
        "key": key,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **(metadata or {}),
    }
    try:
        # Upsert so repeated saves with the same key overwrite the old entry
        collection.upsert(
            ids=[key],
            documents=[content],
            metadatas=[meta],
        )
        logger.debug("Memory saved: key=%s", key)
        return json.dumps({"success": True, "key": key})
    except Exception as exc:
        logger.error("save_to_memory FAILED: %s", exc)
        return json.dumps({"success": False, "error": str(exc)})


def search_memory(query: str, n_results: int = 5, collection_name: str = "agent_memory") -> str:
    """Semantic search over stored memories.

    Args:
        query: Natural-language search query.
        n_results: Number of results to return.
        collection_name: ChromaDB collection to search.

    Returns:
        JSON string: ``{"results": [{"content": ..., "key": ..., "distance": ..., "metadata": ...}]}``.
    """
    collection = _get_collection(collection_name)
    try:
        count = collection.count()
        if count == 0:
            return json.dumps({"results": [], "message": "Memory is empty"})

        n = min(n_results, count)
        results = collection.query(
            query_texts=[query],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            hits.append({
                "content": doc,
                "key": meta.get("key", ""),
                "distance": round(dist, 4),
                "metadata": meta,
            })
        return json.dumps({"results": hits})
    except Exception as exc:
        logger.error("search_memory FAILED: %s", exc)
        return json.dumps({"results": [], "error": str(exc)})


def delete_memory(key: str) -> str:
    """Delete a memory entry by key.

    Args:
        key: The id of the entry to delete.

    Returns:
        JSON confirmation string.
    """
    collection = _get_collection()
    try:
        collection.delete(ids=[key])
        return json.dumps({"success": True, "key": key})
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})


# ------------------------------------------------------------------
# Agent state (JSON files)
# ------------------------------------------------------------------

def save_agent_state(agent_name: str, state_dict: dict[str, Any]) -> str:
    """Persist *state_dict* for *agent_name* as a JSON file.

    Args:
        agent_name: Identifier for the agent (used as filename).
        state_dict: Arbitrary serialisable state to persist.

    Returns:
        JSON confirmation string with the file path.
    """
    state_dir = Path(app_settings.app.agent_state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"{agent_name}.json"

    payload = {
        "agent_name": agent_name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "state": state_dict,
    }
    try:
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        logger.debug("Agent state saved: %s -> %s", agent_name, path)
        return json.dumps({"success": True, "path": str(path)})
    except Exception as exc:
        logger.error("save_agent_state FAILED for %s: %s", agent_name, exc)
        return json.dumps({"success": False, "error": str(exc)})


def load_agent_state(agent_name: str) -> dict[str, Any]:
    """Load persisted state for *agent_name*.

    Args:
        agent_name: Agent identifier.

    Returns:
        State dict, or empty dict if no state was previously saved.
    """
    path = Path(app_settings.app.agent_state_dir) / f"{agent_name}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("state", {})
    except Exception as exc:
        logger.error("load_agent_state FAILED for %s: %s", agent_name, exc)
        return {}


# ------------------------------------------------------------------
# Interaction history (JSON append log)
# ------------------------------------------------------------------

def save_interaction(
    question: str,
    answer: str,
    sql: str | None = None,
    agent: str = "unknown",
) -> str:
    """Append one Q&A interaction to the global history log.

    Args:
        question: User question.
        answer: Agent response.
        sql: Optional SQL that was generated.
        agent: Name of the agent that handled the request.

    Returns:
        JSON confirmation string.
    """
    history_path = Path(app_settings.app.agent_state_dir) / "interaction_history.json"

    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "question": question,
        "sql": sql,
        "answer": answer,
    }

    history: list[dict[str, Any]] = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except Exception:
            history = []

    history.append(entry)
    # Keep last 200 entries
    history = history[-200:]

    try:
        history_path.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")
        return json.dumps({"success": True, "id": entry["id"]})
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})


def load_history(limit: int = 20) -> list[dict[str, Any]]:
    """Load the most recent interaction history entries.

    Args:
        limit: Maximum number of entries to return.

    Returns:
        List of interaction dicts, most recent first.
    """
    history_path = Path(app_settings.app.agent_state_dir) / "interaction_history.json"
    if not history_path.exists():
        return []
    try:
        history = json.loads(history_path.read_text(encoding="utf-8"))
        return list(reversed(history[-limit:]))
    except Exception:
        return []


# ------------------------------------------------------------------
# Gemini tool functions — clean signatures for auto schema extraction
# ------------------------------------------------------------------

def save_memory(key: str, content: str) -> str:
    """Save text content to semantic memory (ChromaDB) for future retrieval.

    Args:
        key: Unique identifier for this memory entry.
        content: Text content to store and embed.

    Returns:
        JSON string confirming success or describing the error.
    """
    return save_to_memory(key, content)


def recall_memory(query: str, n_results: int = 5) -> str:
    """Search semantic memory for information relevant to the query.

    Args:
        query: Natural-language search query.
        n_results: Number of results to return (default: 5).

    Returns:
        JSON string with a list of matching memory entries.
    """
    return search_memory(query, n_results)


# List of callables passed to Gemini (replaces JSON schema dicts)
MEMORY_TOOL_FUNCTIONS = [save_memory, recall_memory]


def dispatch_memory_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Route memory tool calls to the correct function.

    Args:
        tool_name: ``save_memory`` or ``recall_memory``.
        tool_input: Arguments matching the function's signature.

    Returns:
        JSON string result.
    """
    handlers: dict[str, Any] = {
        "save_memory":   lambda i: save_memory(i["key"], i["content"]),
        "recall_memory": lambda i: recall_memory(i["query"], i.get("n_results", 5)),
        # backward-compat alias
        "search_memory": lambda i: recall_memory(i["query"], i.get("n_results", 5)),
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return json.dumps({"success": False, "error": f"Unknown memory tool: {tool_name}"})
    return handler(tool_input)

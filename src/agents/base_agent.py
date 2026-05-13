"""Abstract base agent — wraps the Google Gemini agentic loop with tool calling."""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable

from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 15


class BaseAgent(ABC):
    """Abstract agent that drives the Gemini agentic loop.

    Subclasses must implement ``_execute_tool`` and pass a list of
    Python callable functions as ``tools``.  Gemini extracts the JSON
    schema automatically from the function signatures and docstrings.
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        tools: list[Callable],
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools  # Python callables — Gemini reads their signatures
        self.client = genai.Client(api_key=settings.google.api_key)
        self.model = settings.google.model
        self.conversation_history: list[types.Content] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, user_message: str) -> str:
        """Process *user_message* through the full Gemini agentic loop.

        Loop:
        1. Append user message to conversation history.
        2. Call Gemini with the current history, system prompt, and tools.
        3. If the response contains function_call parts → execute each tool,
           append a function_response turn, and loop.
        4. Return the final text when Gemini stops calling tools.

        Args:
            user_message: Input from the user or a calling agent.

        Returns:
            Final text response from Gemini.
        """
        self.conversation_history.append(
            types.Content(role="user", parts=[types.Part(text=user_message)])
        )
        logger.info("[%s] Starting run | message: %.100s", self.name, user_message)

        for iteration in range(_MAX_ITERATIONS):
            config = types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                temperature=0.1,
                max_output_tokens=4096,
                tools=self.tools if self.tools else None,
            )

            response = self.client.models.generate_content(
                model=self.model,
                contents=self.conversation_history,
                config=config,
            )

            candidate = response.candidates[0]
            logger.debug(
                "[%s] Iteration %d | finish_reason=%s",
                self.name, iteration, candidate.finish_reason,
            )

            # Append model turn to history
            self.conversation_history.append(candidate.content)

            # Collect function call parts
            fc_parts = [
                p for p in candidate.content.parts
                if hasattr(p, "function_call") and p.function_call is not None
            ]

            if not fc_parts:
                # No tool calls — we're done
                final_text = _extract_text(candidate.content)
                logger.info("[%s] Run complete | response: %.150s", self.name, final_text)
                return final_text

            # Execute all requested tools and collect responses
            fr_parts: list[types.Part] = []
            for part in fc_parts:
                fc = part.function_call
                logger.info("[%s] Calling tool: %s | args: %s", self.name, fc.name, dict(fc.args))
                try:
                    result = self._execute_tool(fc.name, dict(fc.args))
                except Exception as exc:
                    result = json.dumps({"success": False, "error": str(exc)})
                    logger.error("[%s] Tool %s raised: %s", self.name, fc.name, exc)

                fr_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"result": result},
                        )
                    )
                )

            self.conversation_history.append(
                types.Content(role="user", parts=fr_parts)
            )

        logger.warning("[%s] Reached max iterations (%d)", self.name, _MAX_ITERATIONS)
        return f"[{self.name}] Nombre maximum d'itérations atteint sans réponse finale."

    def reset(self) -> None:
        """Clear the conversation history."""
        self.conversation_history = []
        logger.debug("[%s] History reset", self.name)

    # ------------------------------------------------------------------
    # Tool execution (implemented by subclasses)
    # ------------------------------------------------------------------

    @abstractmethod
    def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Dispatch *tool_name* to the appropriate Python function.

        Args:
            tool_name: Name of the function Gemini wants to call.
            tool_input: Arguments dict matching the function's signature.

        Returns:
            JSON string result sent back to Gemini as a function_response.
        """


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_text(content: types.Content) -> str:
    """Extract and concatenate all text parts from a Content object."""
    parts = []
    for part in content.parts:
        if hasattr(part, "text") and part.text:
            parts.append(part.text)
    return "\n".join(parts).strip()

"""Analyst Agent — generates insights, trends, and visualisation code from query results."""

import json
import logging
from typing import Any

import pandas as pd

from src.agents.base_agent import BaseAgent
from src.tools.memory_tools import MEMORY_TOOL_FUNCTIONS, dispatch_memory_tool

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Tu es un analyste de données expert, spécialisé dans l'analyse de données commerciales (ventes, clients, produits).

Tu reçois des données sous forme de JSON (résultats d'une requête SQL) et tu dois produire une analyse approfondie en français.

STRUCTURE DE TA RÉPONSE (toujours en Markdown) :

## 📊 Résumé exécutif
[2-3 phrases résumant l'essentiel]

## 🔍 Insights clés
[3-5 points d'analyse avec des chiffres précis]

## 📈 Tendances et anomalies
[Tendances observées, valeurs aberrantes, patterns]

## 💡 Recommandations
[2-3 actions concrètes basées sur les données]

## 📉 Code de visualisation
```python
# Code Python avec plotly pour visualiser les données
import plotly.express as px
import pandas as pd
# [code complet et fonctionnel]
```

RÈGLES :
- Cite toujours des chiffres précis tirés des données
- Compare avec des benchmarks (moyenne, médiane) quand c'est pertinent
- Mets en évidence les 20% qui génèrent 80% des résultats (loi de Pareto)
- Sois concis mais précis — pas de blabla inutile
- Le code plotly doit être fonctionnel et prêt à exécuter"""


class AnalystAgent(BaseAgent):
    """Agent that produces analytical reports and visualisation code from data.

    Accepts either a pandas DataFrame or a JSON/list of records, then drives
    Claude to generate structured Markdown insights with Plotly code snippets.
    """

    def __init__(self) -> None:
        super().__init__(
            name="AnalystAgent",
            system_prompt=_SYSTEM_PROMPT,
            tools=MEMORY_TOOL_FUNCTIONS,
        )

    def analyse(
        self,
        data: pd.DataFrame | list[dict[str, Any]] | dict[str, Any],
        question: str = "",
        context: str = "",
    ) -> str:
        """Analyse *data* and return a structured Markdown report.

        Args:
            data: Query results as a DataFrame, list of records, or single dict.
            question: Original user question for context.
            context: Additional context (e.g., SQL query used).

        Returns:
            Structured Markdown report with insights and Plotly code.
        """
        # Normalise input to a list of records
        if isinstance(data, pd.DataFrame):
            records = data.to_dict(orient="records")
            shape_info = f"DataFrame: {len(data)} lignes × {len(data.columns)} colonnes"
        elif isinstance(data, dict):
            records = [data]
            shape_info = "1 enregistrement"
        else:
            records = list(data)
            shape_info = f"{len(records)} enregistrements"

        if not records:
            return "## ⚠️ Aucune donnée\n\nLa requête n'a retourné aucun résultat à analyser."

        # Build prompt
        json_data = json.dumps(records[:500], default=str, ensure_ascii=False, indent=2)
        prompt_parts = [
            f"**Question utilisateur :** {question}" if question else "",
            f"**Contexte :** {context}" if context else "",
            f"**Volume :** {shape_info}",
            "",
            "**Données à analyser :**",
            f"```json\n{json_data}\n```",
        ]
        prompt = "\n".join(p for p in prompt_parts if p is not None)

        self.reset()
        return self.run(prompt)

    def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        return dispatch_memory_tool(tool_name, tool_input)

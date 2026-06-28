from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .models import Article

VOCABULARY_PROMPT = """You are an expert in Chinese postgraduate entrance examination English.

Analyze the following article. For difficult vocabulary items, classify them into:
1. domain terminology
2. academic vocabulary
3. polysemy (common word with uncommon meaning)
4. idiomatic expression
5. institutional vocabulary
6. legal or political vocabulary

For each item provide:
lemma, meaning_in_context, common_meaning,
why_chinese_students_misunderstand_it, estimated_level, exam_importance.
Return compact JSON only.
"""

RHETORIC_PROMPT = """Analyze the rhetorical structure of this article.

Identify concession structures, contrast structures, causality structures,
author attitude expressions, argument development patterns, hedging expressions,
and stance markers.
For each item provide:
original_sentence, type, explanation, importance_for_chinese_postgraduate_reading.
Return compact JSON only.
"""

ARTICLE_VALUE_PROMPT = """Evaluate the usefulness of this article for
Chinese postgraduate entrance examination preparation.

Provide scores from 1 to 10 for vocabulary_difficulty, sentence_complexity,
logical_structure, domain_knowledge_density, similarity_to_previous_exam_passages.
Also provide primary_domain and a probability distribution over:
politics, law, economics, science, environment, sociology, psychology, education.
Return compact JSON only.
"""


@dataclass(slots=True)
class LLMAnalyzer:
    model: str = "gpt-4.1-mini"
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> LLMAnalyzer:
        return cls(
            model=os.getenv("GRECIS_LLM_MODEL", "gpt-4.1-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )

    def enabled(self) -> bool:
        return bool(self.api_key)

    def analyze(self, article: Article) -> dict[str, Any]:
        if not self.enabled():
            return {}

        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        article_text = article.text[:12000]
        payload = {
            "title": article.title,
            "source": article.source,
            "text": article_text,
        }
        tasks = {
            "vocabulary": VOCABULARY_PROMPT,
            "rhetoric": RHETORIC_PROMPT,
            "exam_value": ARTICLE_VALUE_PROMPT,
        }
        results: dict[str, Any] = {}
        for name, prompt in tasks.items():
            response = client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            )
            results[name] = parse_jsonish(response.output_text)
        return results


def parse_jsonish(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw": text}

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from functools import cached_property
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
Return compact JSON only. Do NOT output any <think> tags or thinking process.
Output raw JSON directly.
"""

COMBINED_ANALYSIS_PROMPT = """Analyze this article for Chinese postgraduate English reading.
Return compact JSON with exactly:
{
"vocabulary":[{"lemma":"","meaning_in_context":"","common_meaning":"",
"why_chinese_students_misunderstand_it":"","estimated_level":"",
"exam_importance":"","domain":""}],
"rhetoric":[{"original_sentence":"","type":"","explanation":"",
"importance_for_chinese_postgraduate_reading":""}],
"exam_value":{"vocabulary_difficulty":1,"sentence_complexity":1,
"logical_structure":1,"domain_knowledge_density":1,
"similarity_to_previous_exam_passages":1,"primary_domain":"",
"domain_probabilities":{}}
}
Limits: vocabulary <= 12 high-value items, rhetoric <= 6 items.
Prefer polysemy, exam phrases, domain terms. Raw JSON only.
"""

RHETORIC_PROMPT = """Analyze the rhetorical structure of this article.

Identify concession structures, contrast structures, causality structures,
author attitude expressions, argument development patterns, hedging expressions,
and stance markers.
For each item provide:
original_sentence, type, explanation, importance_for_chinese_postgraduate_reading.
Return compact JSON only. Do NOT output any <think> tags or thinking process.
Output raw JSON directly.
"""

ARTICLE_VALUE_PROMPT = """Evaluate the usefulness of this article for
Chinese postgraduate entrance examination preparation.

Provide scores from 1 to 10 for vocabulary_difficulty, sentence_complexity,
logical_structure, domain_knowledge_density, similarity_to_previous_exam_passages.
Also provide primary_domain and a probability distribution over:
politics, law, economics, science, environment, sociology, psychology, education.
Return compact JSON only. Do NOT output any <think> tags or thinking process.
Output raw JSON directly.
"""


@dataclass(slots=True)
class LLMAnalyzer:
    model: str = "gpt-4.1-mini"
    api_key: str | None = None
    base_url: str | None = None

    @classmethod
    def from_env(cls) -> LLMAnalyzer:
        return cls(
            model=os.getenv("GRECIS_LLM_MODEL", "gpt-4.1-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("GRECIS_LLM_BASE_URL") or None,
        )

    @classmethod
    def from_config(cls, model: str, api_key: str, base_url: str = "") -> LLMAnalyzer:
        return cls(model=model, api_key=api_key or None, base_url=base_url or None)

    def enabled(self) -> bool:
        return bool(self.api_key) or bool(self.base_url)

    @cached_property
    def client(self):
        from openai import OpenAI

        base_url = normalize_openai_base_url(self.base_url or "")
        api_key = self.api_key or "ollama"
        return OpenAI(api_key=api_key, base_url=base_url or None, max_retries=0, timeout=45.0)

    def analyze(self, article: Article) -> dict[str, Any]:
        if not self.enabled():
            return {}

        article_text = compact_article_text(article.text)
        article_payload = {
            "title": article.title,
            "source": article.source,
            "text": article_text,
        }
        if os.getenv("GRECIS_LLM_LEGACY_THREE_CALLS", "").lower() in {"1", "true", "yes"}:
            return self._analyze_legacy(article_payload)

        request_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": COMBINED_ANALYSIS_PROMPT},
                {"role": "user", "content": json.dumps(article_payload, ensure_ascii=False)},
            ],
            "temperature": 0.1,
            "max_tokens": 1800,
        }
        content = self._chat_completion_content(request_payload)
        parsed = parse_jsonish(content)
        return parsed if isinstance(parsed, dict) else {"raw": content}

    def _analyze_legacy(self, payload: dict[str, Any]) -> dict[str, Any]:
        tasks = {
            "vocabulary": VOCABULARY_PROMPT,
            "rhetoric": RHETORIC_PROMPT,
            "exam_value": ARTICLE_VALUE_PROMPT,
        }
        results: dict[str, Any] = {}
        for name, prompt in tasks.items():
            request_payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                "temperature": 0.1,
                "max_tokens": 1000,
            }
            content = self._chat_completion_content(request_payload)
            results[name] = parse_jsonish(content)
        return results

    def _chat_completion_content(self, payload: dict[str, Any]) -> str:
        if (self.base_url or "").strip().endswith("/chat/completions"):
            return post_chat_completion_raw(self.base_url or "", self.api_key or "", payload)
        response = self.client.chat.completions.create(**payload)
        return response.choices[0].message.content or ""


def normalize_openai_base_url(base_url: str) -> str:
    value = (base_url or "").strip()
    for suffix in ("/chat/completions", "/completions"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    if "11434" in value and not value.endswith("/v1") and not value.endswith("/v1/"):
        value = value.rstrip("/") + "/v1"
    return value.rstrip("/")


def post_chat_completion_raw(
    url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout: float = 60.0,
) -> str:
    req = urllib.request.Request(
        url.strip(),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def compact_article_text(text: str, limit: int = 6500) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    head = cleaned[: int(limit * 0.55)]
    tail = cleaned[-int(limit * 0.25) :]
    middle_start = max((len(cleaned) - int(limit * 0.2)) // 2, 0)
    middle = cleaned[middle_start : middle_start + int(limit * 0.2)]
    return f"{head}\n...\n{middle}\n...\n{tail}"


def parse_jsonish(text: str) -> Any:
    cleaned = text.strip()
    import re

    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw": text}

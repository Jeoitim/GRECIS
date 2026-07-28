import pytest

from grecis.llm import (
    LLMAnalyzer,
    compact_article_text,
    message_text,
    normalize_openai_base_url,
    parse_jsonish,
    post_chat_completion_raw,
)
from grecis.models import Article


def test_llm_base_url_normalization() -> None:
    assert (
        normalize_openai_base_url("https://api.example.com/v1/chat/completions")
        == "https://api.example.com/v1"
    )


def test_llm_client_is_cached_with_slots() -> None:
    analyzer = LLMAnalyzer(
        model="m",
        api_key="k",
        base_url="https://api.example.com/v1",
    )

    assert analyzer.client is analyzer.client


def test_compact_article_text_keeps_text_short() -> None:
    text = " ".join(f"sentence{i}" for i in range(2000))
    compacted = compact_article_text(text, limit=1000)
    assert len(compacted) <= 1010
    assert "sentence0" in compacted
    assert "sentence1999" in compacted


def test_llm_analyzer_uses_single_combined_call(monkeypatch) -> None:
    calls = []

    class FakeMessage:
        content = (
            '{"vocabulary":[],"rhetoric":[],"exam_value":'
            '{"primary_domain":"science","domain_probabilities":{}}}'
        )

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return type("Response", (), {"choices": [FakeChoice()]})()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    analyzer = LLMAnalyzer(model="m", api_key="k", base_url="https://api.example.com/v1")
    monkeypatch.setattr(LLMAnalyzer, "client", FakeClient())

    result = analyzer.analyze(
        Article(title="T", source="S", text="Research evidence suggests change.")
    )

    assert result["vocabulary"] == []
    assert result["_meta"]["prompt_version"] == "combined_rhetoric_v3"
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 8192
    assert calls[0]["timeout"] == 180.0


def test_llm_analyzer_uses_raw_post_for_full_chat_completions_endpoint(monkeypatch) -> None:
    calls = []

    def fake_raw(url, api_key, payload, timeout):
        calls.append((url, api_key, payload, timeout))
        return '{"vocabulary":[],"rhetoric":[],"exam_value":{"primary_domain":"science"}}'

    analyzer = LLMAnalyzer(
        model="m",
        api_key="k",
        base_url="https://api.example.com/v1/chat/completions",
    )
    monkeypatch.setattr("grecis.llm.post_chat_completion_raw", fake_raw)

    result = analyzer.analyze(
        Article(title="T", source="S", text="Research evidence suggests change.")
    )

    assert result["exam_value"]["primary_domain"] == "science"
    assert calls[0][0] == "https://api.example.com/v1/chat/completions"
    assert calls[0][3] == 180.0


def test_reasoning_content_is_used_when_content_is_empty() -> None:
    message = {"content": "", "reasoning_content": '{"ok":true}'}

    assert message_text(message) == '{"ok":true}'


def test_raw_chat_completion_supports_reasoning_content(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return (
                b'{"choices":[{"message":{"content":null,'
                b'"reasoning_content":"{\\"ok\\":true}"}}]}'
            )

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert post_chat_completion_raw("https://example.com", "key", {}) == '{"ok":true}'


def test_parse_jsonish_extracts_json_from_fence_or_reasoning_text() -> None:
    assert parse_jsonish('result follows\n```json\n{"ok": true}\n```') == {"ok": True}
    assert parse_jsonish('analysis first\n{"ok": true}\nfinished') == {"ok": True}
    full = '{"vocabulary":[],"rhetoric":[],"exam_value":{}}'
    assert parse_jsonish(f'consider {{"draft":true}} then answer {full}') == {
        "vocabulary": [],
        "rhetoric": [],
        "exam_value": {},
    }


def test_llm_analyzer_rejects_truncated_json(monkeypatch) -> None:
    analyzer = LLMAnalyzer(model="m", api_key="k")
    monkeypatch.setattr(
        LLMAnalyzer,
        "_chat_completion_content",
        lambda _self, _payload: '{"vocabulary": [',
    )

    with pytest.raises(ValueError, match="完整"):
        analyzer.analyze(Article(title="T", source="S", text="Evidence matters."))

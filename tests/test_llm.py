from grecis.llm import LLMAnalyzer, compact_article_text, normalize_openai_base_url
from grecis.models import Article


def test_llm_base_url_normalization() -> None:
    assert (
        normalize_openai_base_url("https://api.example.com/v1/chat/completions")
        == "https://api.example.com/v1"
    )


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
    assert result["_meta"]["prompt_version"] == "combined_rhetoric_v2"
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 2600


def test_llm_analyzer_uses_raw_post_for_full_chat_completions_endpoint(monkeypatch) -> None:
    calls = []

    def fake_raw(url, api_key, payload):
        calls.append((url, api_key, payload))
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

from grecis.dictionary import (
    extract_dictionary_fields,
    is_negative_cache_entry,
    normalize_openai_base_url,
    query_word,
    should_query_remote_dictionary,
    should_use_llm_fallback,
)


def test_normalize_openai_base_url_accepts_chat_completions_endpoint() -> None:
    assert (
        normalize_openai_base_url("https://api.example.com/v1/chat/completions")
        == "https://api.example.com/v1"
    )


def test_dictionary_sends_phrases_to_llm_without_dictionary_api(monkeypatch, tmp_path) -> None:
    import grecis.dictionary as dictionary

    calls = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dictionary, "_CACHE_IN_MEMORY", {})
    monkeypatch.setattr(dictionary, "query_word_local", lambda word: None)
    monkeypatch.setattr(
        dictionary, "fetch_from_youdao", lambda word: (_ for _ in ()).throw(AssertionError)
    )
    monkeypatch.setattr(
        dictionary, "fetch_from_dictionary_api", lambda word: (_ for _ in ()).throw(AssertionError)
    )

    def fake_llm(word):
        calls.append(word)
        return {"phonetic": "", "zh": "联邦管辖权", "en": "federal legal authority", "pos": ""}

    monkeypatch.setattr(dictionary, "fetch_from_llm", fake_llm)

    assert query_word("federal jurisdiction")["zh"] == "联邦管辖权"
    assert calls == ["federal jurisdiction"]


def test_dictionary_negative_caches_phrase_llm_failures(monkeypatch, tmp_path) -> None:
    import grecis.dictionary as dictionary

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dictionary, "_CACHE_IN_MEMORY", {})
    monkeypatch.setattr(dictionary, "query_word_local", lambda word: None)
    monkeypatch.setattr(
        dictionary, "fetch_from_llm", lambda word: {"phonetic": "", "zh": "", "en": "", "pos": ""}
    )

    assert query_word("federal jurisdiction") == {"phonetic": "", "zh": "", "en": "", "pos": ""}
    cache = dictionary.load_cache()
    assert cache["federal jurisdiction"]["_not_found"] is True
    assert cache["federal jurisdiction"]["_not_found_policy"] == "phrase_llm_v1"


def test_dictionary_llm_fallback_is_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("GRECIS_DICT_LLM_FALLBACK", raising=False)
    assert should_use_llm_fallback("jurisdiction") is False
    assert should_use_llm_fallback("federal jurisdiction") is True
    monkeypatch.setenv("GRECIS_DICT_LLM_FALLBACK", "1")
    assert should_use_llm_fallback("jurisdiction") is True
    assert should_use_llm_fallback("federal jurisdiction") is True


def test_remote_dictionary_only_for_simple_words() -> None:
    assert should_query_remote_dictionary("jurisdiction") is True
    assert should_query_remote_dictionary("federal jurisdiction") is False
    assert should_query_remote_dictionary("anti-regulatory") is False


def test_old_phrase_negative_cache_is_retried() -> None:
    assert is_negative_cache_entry({"_not_found": True}, "jurisdiction") is True
    assert is_negative_cache_entry({"_not_found": True}, "federal jurisdiction") is False
    assert (
        is_negative_cache_entry(
            {"_not_found": True, "_not_found_policy": "phrase_llm_v1"},
            "federal jurisdiction",
        )
        is True
    )


def test_old_phrase_negative_cache_does_not_block_llm(monkeypatch, tmp_path) -> None:
    import grecis.dictionary as dictionary

    calls = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        dictionary,
        "_CACHE_IN_MEMORY",
        {"occupied the field": {"phonetic": "", "zh": "", "en": "", "pos": "", "_not_found": True}},
    )
    monkeypatch.setattr(dictionary, "query_word_local", lambda word: None)

    def fake_llm(word):
        calls.append(word)
        return {"phonetic": "", "zh": "排除其他管辖", "en": "to preempt an area of law", "pos": ""}

    monkeypatch.setattr(dictionary, "fetch_from_llm", fake_llm)

    assert query_word("occupied the field")["zh"] == "排除其他管辖"
    assert calls == ["occupied the field"]


def test_llm_plain_text_short_response_is_used(monkeypatch) -> None:
    import grecis.dictionary as dictionary

    class FakeMessage:
        content = "排除其他管辖"

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletions:
        def create(self, **kwargs):
            return type("Response", (), {"choices": [FakeChoice()]})()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(dictionary, "get_llm_client", lambda: FakeClient())
    monkeypatch.setattr(
        "grecis.config.load_config",
        lambda: type(
            "Config",
            (),
            {"llm": type("LLM", (), {"model": "m", "base_url": "", "api_key": "k"})()},
        )(),
    )

    result = dictionary.fetch_from_llm("occupied the field")

    assert result["zh"] == "排除其他管辖"
    assert result["pos"] == "phrase"


def test_dictionary_uses_raw_post_for_full_chat_endpoint(monkeypatch) -> None:
    import grecis.dictionary as dictionary

    calls = []

    def fake_raw(url, api_key, payload):
        calls.append((url, api_key, payload))
        return '{"phonetic":"","zh":"联邦管辖权","en":"federal jurisdiction","pos":"phrase"}'

    config = type(
        "Config",
        (),
        {
            "llm": type(
                "LLM",
                (),
                {
                    "model": "m",
                    "api_key": "k",
                    "base_url": "https://api.example.com/v1/chat/completions",
                },
            )()
        },
    )()

    monkeypatch.setattr(dictionary, "get_llm_client", lambda: object())
    monkeypatch.setattr("grecis.config.load_config", lambda: config)
    monkeypatch.setattr(dictionary, "post_chat_completion_raw", fake_raw)

    result = dictionary.fetch_from_llm("federal jurisdiction")

    assert result["zh"] == "联邦管辖权"
    assert calls[0][0] == "https://api.example.com/v1/chat/completions"


def test_extract_dictionary_fields_from_partial_json() -> None:
    content = '```json\n{"phonetic":"/x/","zh":"支出条款法规","en":"spending clause statutes"'
    result = extract_dictionary_fields(content, "spending-clause statutes")
    assert result["phonetic"] == "/x/"
    assert result["zh"] == "支出条款法规"
    assert result["en"] == "spending clause statutes"
    assert result["pos"] == "phrase"

from grecis.models import Article
from grecis.nlp import analyze_article, content_tokens, extract_collocations, extract_polysemy


def test_content_tokens_normalize_common_suffixes() -> None:
    assert "study" in content_tokens("Studies suggested stronger findings.")
    assert "suggest" in content_tokens("Studies suggested stronger findings.")


def test_extract_polysemy_finds_exam_risk_word() -> None:
    rows = extract_polysemy("The court held that the case was at issue.")
    words = {row["word"] for row in rows}
    assert {"hold", "case", "issue"} <= words


def test_analyze_article_returns_core_sections() -> None:
    article = Article(
        id="x",
        title="Market case",
        source="test",
        text=(
            "Although the regulator challenged the acquisition, the firm argued that the "
            "market would remain competitive. The court held that the case was at issue."
        ),
    )
    result = analyze_article(article)
    assert result.article_id == "x"
    assert result.field in {"economics", "law", "unknown"}
    assert result.word_frequencies
    assert result.polysemy
    assert result.sentence_patterns


def test_extract_collocations_prioritizes_exam_phrases() -> None:
    text = "What is at issue is whether the policy will lead to higher costs."
    tokens = content_tokens(text)
    rows = extract_collocations(text, tokens)
    by_expression = {row["expression"]: row for row in rows}
    assert by_expression["at issue"]["meaning"] == "争议焦点在于"
    assert by_expression["lead to"]["meaning"] == "导致；通向"


def test_analyze_article_filters_common_high_school_words_from_vocab() -> None:
    article = Article(
        id="y",
        title="Simple",
        source="test",
        text=" ".join(
            [
                "The issue is important because people can understand the policy and the result.",
            ]
            * 30
        ),
    )
    result = analyze_article(article)
    words = {item["word"] for item in result.word_frequencies}
    assert "issue" in words
    assert "people" not in words
    assert "can" not in words

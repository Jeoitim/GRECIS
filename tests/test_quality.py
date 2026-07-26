from grecis.config import SourceConfig
from grecis.models import Article
from grecis.quality import score_article_quality


def test_quality_rejects_excluded_sports_topic() -> None:
    source = SourceConfig(
        name="Example",
        reliability=0.9,
        exclude_keywords=["football"],
        prefer_keywords=["policy"],
    )
    article = Article(
        title="Football live updates",
        text=" ".join(["football policy sentence."] * 300),
        source="Example",
    )
    result = score_article_quality(article, source)
    assert result["quality_keep"] is False
    assert result["quality_score"] < 6.0


def test_quality_keeps_kaoyan_exam_corpus() -> None:
    article = Article(
        title="Exam",
        text="Short passage.",
        source="kaoyan_exam",
        metadata={"corpus_type": "kaoyan_exam"},
    )
    result = score_article_quality(article)
    assert result["quality_keep"] is True
    assert result["quality_score"] == 10.0


def test_quality_prioritizes_guardian_over_other_non_exam_sources() -> None:
    text = " ".join(
        [
            "This policy analysis examines education, society, regulation, and culture because "
            "research suggests that public institutions shape inequality."
        ]
        * 120
    )
    guardian = SourceConfig(name="The Guardian", reliability=0.9, quality_weight=0.5)
    other = SourceConfig(name="Nature", reliability=0.99, quality_weight=1.5)
    guardian_score = score_article_quality(Article(title="Policy analysis", text=text), guardian)
    other_score = score_article_quality(Article(title="Policy analysis", text=text), other)
    assert guardian_score["quality_score"] > other_score["quality_score"]


def test_quality_reports_rhetorical_diversity_and_boilerplate() -> None:
    text = " ".join(
        [
            "Although the evidence may be limited, researchers argue that the policy "
            "could work because it changes incentives."
        ]
        * 80
    )
    text += " Subscribe to our newsletter. Sign in to continue."
    result = score_article_quality(Article(title="Policy analysis", text=text))
    assert result["pattern_diversity"] >= 4
    assert set(result["boilerplate_hits"]) == {"subscription", "account_prompt"}

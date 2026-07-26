from __future__ import annotations

import json

from grecis.db import ensure_db
from grecis.models import Article
from grecis.nlp import analyze_article, extract_sentence_patterns
from grecis.patterns import normalize_sentence_pattern_type
from grecis.redbook import select_sentence_patterns


def test_pattern_type_normalization_collapses_llm_aliases() -> None:
    assert normalize_sentence_pattern_type("Stance Marker") == "stance"
    assert normalize_sentence_pattern_type("author_attitude_expression") == "stance"
    assert normalize_sentence_pattern_type("Contrast structure") == "contrast"
    assert normalize_sentence_pattern_type("argument-development pattern") == (
        "argument_development"
    )


def test_local_pattern_extraction_is_multi_label() -> None:
    sentence = (
        "Although the evidence may appear limited, critics disagree, but they argue "
        "that the policy could "
        "still lead to higher costs."
    )
    rows = extract_sentence_patterns(sentence)
    types = {row["type"] for row in rows}
    assert {"concession", "contrast", "causality", "stance", "hedging"} <= types
    assert all(row["pattern"] for row in rows)


def test_structural_patterns_avoid_common_false_positives() -> None:
    rows = extract_sentence_patterns(
        "It is clear that the model is outdated. It is unarguable that energy matters. "
        "Notably, tipping benefits waiters but not cooks. "
        "What health functions should remain at the centre? "
        "Whether it is a tracker or an app, the technology collects data."
    )
    types = {row["type"] for row in rows}
    assert "cleft" not in types
    assert "participial_clause" not in types
    assert "nominal_clause" not in types


def test_sentence_pattern_selection_preserves_category_diversity() -> None:
    rows = [
        {
            "type": pattern_type,
            "function": pattern_type,
            "pattern": template,
            "frequency": 10,
            "article_count": 5,
            "importance": 4,
            "example_sentence": sentence,
        }
        for pattern_type, template, sentence in [
            ("concession", "although / though ...", "Although it is costly, it may work."),
            ("contrast", "however ...", "The plan is costly; however, it may work."),
            ("causality", "because ...", "The plan failed because funding disappeared."),
            ("condition", "unless ...", "The plan will fail unless funding continues."),
            ("stance", "researchers argue that ...", "Researchers argue that the plan works."),
            ("hedging", "may / might ...", "The plan may work in larger cities."),
            ("inversion", "rarely + auxiliary ...", "Rarely do such reforms work quickly."),
        ]
    ]
    selected = select_sentence_patterns(rows, per_type=2, limit=20)
    assert {item["type"] for item in selected} == {
        "concession",
        "contrast",
        "causality",
        "condition",
        "stance",
        "hedging",
        "inversion",
    }


def test_reanalysis_without_llm_preserves_existing_payload(tmp_path) -> None:
    db = ensure_db(tmp_path / "corpus.sqlite")
    article = Article(
        id="article-1",
        title="Policy evidence",
        source="pastpapers.cn",
        text=(
            "Although the evidence is limited, researchers argue that the policy may "
            "reduce costs because it changes incentives."
        ),
    )
    db.upsert_article(article)
    llm_payload = {
        "vocabulary": [],
        "rhetoric": [
            {
                "original_sentence": article.text,
                "type": "Stance Marker",
                "explanation": "The reporting verb attributes the claim to researchers.",
            }
        ],
        "exam_value": {},
    }
    db.save_analysis(analyze_article(article, llm_payload=llm_payload))
    db.save_analysis(analyze_article(article))

    with db.connect() as conn:
        stored = conn.execute(
            "SELECT llm_json FROM analyses WHERE article_id = ?",
            ("article-1",),
        ).fetchone()
    assert stored is not None
    assert json.loads(stored["llm_json"]) == llm_payload

    patterns = db.aggregate_sentence_patterns()
    assert any(item["type"] == "stance" for item in patterns)
    assert all("pattern" in item and "article_count" in item for item in patterns)

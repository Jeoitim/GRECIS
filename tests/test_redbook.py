from grecis.redbook import render_redbook


def test_render_redbook_contains_review_sections() -> None:
    seed = {
        "metadata": {"title": "T", "subtitle": "S"},
        "domains": {
            "law": {
                "title": "政治法律",
                "overview": "O",
                "entries": [
                    {
                        "headword": "issue",
                        "kind": "polysemy",
                        "pos": "noun",
                        "importance": 5,
                        "chinese": "争议焦点",
                        "english": "a point in dispute",
                        "common": "问题",
                        "exam": "法律语境",
                        "risk": "不要只译成问题",
                        "collocations": ["at issue"],
                        "examples": [
                            {"sentence": "What is at issue is power.", "zh": "争议焦点是权力。"}
                        ],
                    }
                ],
            }
        },
        "sentence_patterns": [],
    }
    corpus = {
        "vocabulary": [],
        "collocations": [],
        "polysemy": [],
        "sentence_patterns": [],
        "by_word": {},
        "by_expression": {},
    }
    text = render_redbook(seed, corpus)
    assert "## 快速背诵清单" in text
    assert "### issue" in text
    assert "## 7 天复习安排" in text

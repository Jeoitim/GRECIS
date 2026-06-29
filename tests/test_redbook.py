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


def test_render_corpus_appendix_prefers_high_value_entries() -> None:
    from grecis.redbook import render_corpus_appendix

    corpus = {
        "vocabulary": [
            {
                "word": "issue",
                "field": "law",
                "category": "polysemy",
                "frequency": 12,
                "article_count": 4,
                "example_sentence": "x",
                "importance": 5,
            },
            {
                "word": "people",
                "field": "sociology",
                "category": "academic/general",
                "frequency": 30,
                "article_count": 10,
                "example_sentence": "y",
                "importance": 1,
            },
        ],
        "collocations": [
            {
                "expression": "at issue",
                "type": "legal/political expression",
                "meaning": "争议焦点在于",
                "frequency": 8,
                "example_sentence": "z",
            },
            {
                "expression": "you can",
                "type": "2-gram",
                "meaning": "",
                "frequency": 40,
                "example_sentence": "s",
            },
        ],
        "polysemy": [],
        "sentence_patterns": [],
        "by_word": {},
        "by_expression": {},
    }

    text = render_corpus_appendix(corpus)
    joined = "\n".join(text)
    assert "issue" in joined
    assert "people" not in joined
    assert "at issue" in joined
    assert "you can" not in joined


def test_is_exportable_vocabulary_filters() -> None:
    from grecis.export import is_exportable_vocabulary
    
    # 1. Polysemy (always keep)
    assert is_exportable_vocabulary({"word": "issue", "category": "polysemy", "importance": 5}) is True
    assert is_exportable_vocabulary({"word": "address", "category": "熟词生义", "importance": 5}) is True
    
    # 2. Gaokao 3500 words (filter out unless polysemy)
    # 'abandon' is in gaokao_3500
    assert is_exportable_vocabulary({"word": "abandon", "category": "academic/general", "importance": 5, "article_count": 2}) is False
    
    # 3. Proper Nouns / Names (filter out)
    assert is_exportable_vocabulary({"word": "biden", "category": "academic/general", "importance": 5, "example_sentence": "President Biden announced..."}) is False
    assert is_exportable_vocabulary({"word": "trump", "category": "academic/general", "importance": 5, "example_sentence": "Trump spoke at..."}) is False
    
    # 4. Uncommon Abbreviations (filter out)
    assert is_exportable_vocabulary({"word": "fda", "category": "academic/general", "importance": 5, "example_sentence": "The FDA approved it."}) is False
    # Common whitelisted abbreviation should keep
    assert is_exportable_vocabulary({"word": "gdp", "category": "academic/general", "importance": 5, "example_sentence": "The GDP grew by 2%."}) is True
    
    # 5. Uncommon Professional Term (Zipf < 2.5) (filter out)
    # 'pterosaur' zipf freq is very low (~1.3)
    assert is_exportable_vocabulary({"word": "pterosaur", "category": "academic/general", "importance": 5, "article_count": 2}) is False
    
    # 6. Important academic word (keep)
    # 'mitigate' has zipf frequency ~3.0 > 2.5
    assert is_exportable_vocabulary({"word": "mitigate", "category": "academic/general", "importance": 5, "article_count": 2}) is True

from grecis.models import Article
from grecis.topics import exam_topic_queries


def test_exam_topic_queries_extracts_repeated_exam_phrases() -> None:
    text = " ".join(
        [
            "Public policy shapes climate change and public education research.",
            "Climate change policy affects public education and social technology.",
        ]
        * 4
    )
    article = Article(
        title="Exam",
        source="pastpapers.cn",
        text=text,
        metadata={"corpus_type": "kaoyan_exam"},
    )

    queries = exam_topic_queries([article], limit=5)

    assert "public policy" in queries
    assert "climate change" in queries

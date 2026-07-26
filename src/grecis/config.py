from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATHS = [
    Path("config/sources.yaml"),
    Path("config/local.yaml"),
    Path("config/local.yml"),
    Path("config/local.json"),
]


@dataclass(slots=True)
class CrawlerConfig:
    user_agent: str = "GRECIS/0.1 (+local research corpus)"
    request_timeout_seconds: int = 20
    delay_seconds: float = 1.0
    max_articles_per_source: int = 5
    min_text_chars: int = 800
    target_article_count: int = 1000
    min_exam_value: float = 4.5
    min_difficulty: float = 3.5
    min_quality_score: float = 6.0
    candidate_multiplier: int = 8
    max_discovery_pages_per_source: int = 20
    max_search_pages_per_query: int = 2


@dataclass(slots=True)
class LLMConfig:
    model: str = "gpt-4.1-mini"
    api_key: str = ""
    base_url: str = ""


@dataclass(slots=True)
class OutputConfig:
    markdown_dir: str = "output/markdown"
    redbook_dir: str = "output/redbook"


@dataclass(slots=True)
class DatabaseConfig:
    path: str = "data/grecis.sqlite"


@dataclass(slots=True)
class SourceConfig:
    name: str
    enabled: bool = True
    field_hint: str = "unknown"
    category: str = "general"
    reliability: float = 0.8
    quality_weight: float = 1.0
    min_quality_score: float | None = None
    prefer_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    feed_urls: list[str] = field(default_factory=list)
    article_urls: list[str] = field(default_factory=list)
    archive_urls: list[str] = field(default_factory=list)
    archive_url_templates: list[str] = field(default_factory=list)
    search_url_templates: list[str] = field(default_factory=list)
    topic_queries: list[str] = field(default_factory=list)
    article_url_patterns: list[str] = field(default_factory=list)
    article_url_exclude_patterns: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MDictConfig:
    oxford_path: str = (
        r"C:\baidunetdiskdownload\mdict"
        r"\牛津高阶（第10版 英汉双解）V5.0（含机翻）"
        r"\牛津高阶（第10版 英汉双解） V5_0.mdx"
    )
    collins_path: str = r"C:\baidunetdiskdownload\mdict\柯林斯\Collins COBUILD (CN - HD).mdx"


@dataclass(slots=True)
class AppConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    crawler: CrawlerConfig = field(default_factory=CrawlerConfig)
    mdict: MDictConfig = field(default_factory=MDictConfig)
    sources: list[SourceConfig] = field(default_factory=list)


def load_config(path: str | Path | None = None) -> AppConfig:
    payload: dict[str, Any] = {}
    base_path = Path("config/sources.yaml")
    if base_path.exists():
        payload = _read_config(base_path)

    if path:
        config_path = Path(path)
        if config_path.exists():
            payload = _merge_config(payload, _read_config(config_path))
    else:
        for candidate in DEFAULT_CONFIG_PATHS[1:]:
            if candidate.exists():
                payload = _merge_config(payload, _read_config(candidate))
                break

    config = app_config_from_mapping(payload)
    apply_env_overrides(config)
    return config


def app_config_from_mapping(payload: dict[str, Any]) -> AppConfig:
    database = DatabaseConfig(**payload.get("database", {}))
    output = OutputConfig(**payload.get("output", {}))
    llm = LLMConfig(**payload.get("llm", {}))
    crawler = CrawlerConfig(**payload.get("crawler", {}))
    mdict = MDictConfig(**payload.get("mdict", {}))
    sources = [SourceConfig(**source) for source in payload.get("sources", [])]
    return AppConfig(
        database=database, output=output, llm=llm, crawler=crawler, sources=sources, mdict=mdict
    )


def apply_env_overrides(config: AppConfig) -> None:
    if os.getenv("GRECIS_DB_PATH"):
        config.database.path = os.environ["GRECIS_DB_PATH"]
    if os.getenv("GRECIS_OUTPUT_DIR"):
        config.output.markdown_dir = os.environ["GRECIS_OUTPUT_DIR"]
    if os.getenv("GRECIS_LLM_MODEL"):
        config.llm.model = os.environ["GRECIS_LLM_MODEL"]
    if os.getenv("GRECIS_LLM_BASE_URL"):
        config.llm.base_url = os.environ["GRECIS_LLM_BASE_URL"]
    if os.getenv("OPENAI_API_KEY"):
        config.llm.api_key = os.environ["OPENAI_API_KEY"]


def _read_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)

    import yaml

    data = yaml.safe_load(text)
    return data or {}


def _merge_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if key == "sources" and value == []:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged

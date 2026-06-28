# GRECIS

GRECIS = Graduate Reading Corpus Intelligence System.

这是一个面向考研英语阅读的领域语料库分析项目。它把新闻、评论、学术短文和真题语料导入本地 SQLite，进行词频、搭配、熟词生义、领域术语和句式结构分析，并导出结构化 Markdown 与 Anki TSV。

## 功能

- 导入 JSONL 文章语料
- 从 URL 抓取正文并清洗文本
- 按领域识别文章：政治、法律、经济、科技、环境、教育、心理、社会文化
- 统计词频、固定搭配、熟词生义风险词
- 抽取让步、转折、因果、态度和强调句式
- 可选调用 LLM 做更细的词汇分类和文章价值评估
- 导出文章报告、领域词汇库、表达库和 Anki 卡片

## 快速开始

使用 uv：

```powershell
uv sync --extra dev
uv run grecis run-demo
```

使用 pixi：

```powershell
pixi run demo
```

运行后会生成：

```text
data/grecis.sqlite
output/markdown/
output/anki/grecis_cards.tsv
```

## 常用命令

```powershell
grecis init
grecis ingest-jsonl data/sample_articles.jsonl
grecis analyze
grecis export
```

导入单个网页：

```powershell
grecis ingest-url "https://example.com/article" --source "Example"
grecis analyze --use-llm
grecis export
```

LLM 分析需要设置 `.env` 或环境变量：

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:GRECIS_LLM_MODEL="gpt-4.1-mini"
```

## JSONL 语料格式

每行一篇文章：

```json
{"id":"article-001","title":"Antitrust and Market Power","source":"Sample","url":"","published_at":"2026-01-01","text":"The regulator challenged the acquisition..."}
```

`id` 可省略，系统会根据标题、来源和正文生成稳定 ID。

## 输出结构

```text
output/markdown/
├── articles/
│   └── article-001.md
├── fields/
│   └── economics.md
├── expressions.md
└── index.md
```

每篇文章报告包含：

- 领域、难度、考研价值分
- 高频词与领域术语
- 熟词生义
- 固定搭配
- 长难句/逻辑句式
- 原文例句

## 项目结构

```text
src/grecis/
├── cli.py       # 命令行入口
├── db.py        # SQLite 存储
├── export.py    # Markdown 和 Anki 导出
├── ingest.py    # JSONL/URL 导入
├── llm.py       # 可选 LLM 分析
├── models.py    # 数据结构
└── nlp.py       # 统计分析
```

## 说明

词典释义目前预留为结构化字段。出于版权和服务条款考虑，项目不会内置柯林斯或牛津全文释义；后续可以接入你有权限使用的词典 API，并只保存允许缓存的短释义或引用信息。

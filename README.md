# GRECIS

GRECIS = Graduate Reading Corpus Intelligence System.

GRECIS 是一个面向考研英语阅读的语料库分析与复习资料生成项目。它把考研真题、外刊文章和本地授权语料统一入库到 SQLite，再做文章质量筛选、领域识别、词频统计、熟词生义识别、固定表达抽取和句式分析，最后生成 Markdown 知识库、Anki 卡片和红宝书式复习资料。

## 项目介绍

这个项目的目标很明确：把“能读”的文章，变成“能背、能复习、能继续扩展”的语料系统。

它不追求把所有词都塞进词表，而是优先保留高频表达、真题常见搭配、熟词生义和能迁移到考研阅读中的核心内容，同时剔除生僻词、专名、噪音词和低价值文本。

当前版本已经把核心成品纳入仓库，便于共享和迭代：

- `data/grecis.sqlite`
- `output/redbook/*.md`

## 项目灵感来源

项目主要来自两个现实需求：

1. 考研英语阅读需要的是稳定、可复习的高质量输入，不是泛泛的词频表。
2. 很多外刊语料虽然多，但分类粗糙、噪音大、学术科技类堆积严重，直接拿来背诵效率不高。

所以 GRECIS 采用“真题优先 + 外刊补充 + 自动筛选 + 结构化导出”的方式，尽量把语料变成适合复习的内容。

## 目前语料库规模

当前 SQLite 语料库规模如下：

- 388 篇文章
- 388 份分析结果
- 13,875 个词汇项
- 12,731 个搭配
- 1,491 个熟词生义
- 7,945 个句式模式
- 13 份红宝书 Markdown 成品

主要存储位于 `data/grecis.sqlite`，文章导出位于 `output/markdown/articles/`，红宝书位于 `output/redbook/`。

## 语料的获取与使用方式

语料获取顺序是：

```text
真题 PDF / 本地语料
↓
外刊源抓取
↓
正文清洗
↓
质量评分
↓
SQLite 入库
↓
本地 NLP / 可选 LLM 分析
↓
红宝书 / Markdown / Anki 导出
```

常用命令：

```powershell
uv run grecis ingest-pastpapers
uv run grecis ingest-exam data/my_kaoyan_passages.jsonl
uv run grecis build-corpus --second-tier-limit 100 --third-tier-limit 20
uv run grecis analyze
uv run grecis export-redbook
```

如果你只想更新某个来源：

```powershell
uv run grecis fetch-sources --source "The Guardian" --limit 100
uv run grecis update-corpus --source "The Atlantic" --limit 100 --use-llm
```

如果你要做复习使用：

```powershell
uv run grecis curate-corpus
uv run grecis export
```

## 技术实现方式

### 总体流程

```text
配置文件 / 环境变量
↓
真题 PDF / 本地语料 / 外刊 URL / RSS / archive / search
↓
正文提取与清洗
↓
文章质量评分与过滤
↓
SQLite 去重入库
↓
本地 NLP 分析
↓
可选 LLM 深度分析
↓
Markdown 知识库 / Anki TSV / 红宝书
```

### 核心模块

```text
src/grecis/
├── cli.py          # 命令行入口
├── config.py       # YAML/JSON/环境变量配置
├── db.py           # SQLite 存储、聚合查询、LLM 结果入库
├── dictionary.py   # 词典、缓存、短语 LLM fallback
├── export.py       # Markdown 和 Anki 导出
├── ingest.py       # JSONL/URL/archive/search/RSS 导入
├── llm.py          # Chat Completions 分析
├── models.py       # Article / AnalysisResult 数据结构
├── nlp.py          # 本地词频、领域、熟词生义、句式识别
├── pastpapers.py   # pastpapers.cn PDF 真题导入
├── quality.py      # 文章质量评分
├── topics.py       # 从真题反向抽取外刊搜索主题
└── redbook.py      # 高质量红宝书生成
```

### 数据库

SQLite 默认路径是：

```text
data/grecis.sqlite
```

主要表包括：

- `articles`
- `analyses`
- `vocabulary`
- `collocations`
- `polysemy`
- `sentence_patterns`

文章元数据放在 `metadata_json`，包括来源、citation、PDF URL、质量分和质量原因等。

### 红宝书生成

红宝书导出由 `src/grecis/redbook.py` 负责，当前策略是：

- 种子词条优先保留
- 高频短语、熟词生义和考研核心术语优先保留
- 生僻专业词、噪音词、专名和异常缩写剔除
- 未知领域不再默认归入“学术科技”，而是进入泛学术核心词或待复核附录
- 每个章节有容量上限，避免单章膨胀

### 词典与缓存

词典入口在 `src/grecis/dictionary.py`。

查询顺序是：

```text
data/dict_cache.json
↓
本地 MDX 词典
↓
Youdao Suggest API + DictionaryAPI.dev
↓
短语 LLM fallback
↓
负缓存
```

短语通常是词典查不到的主力，所以默认允许 LLM fallback；普通单词则默认不走 LLM fallback。

## 如何自己丰富语料库或开发这个项目

### 自己加语料

1. 在 `config/sources.yaml` 里增加外刊来源。
2. 用 `uv run grecis ingest-exam ...` 导入本地授权语料。
3. 用 `uv run grecis fetch-sources` 或 `uv run grecis build-corpus` 扩充文章池。
4. 用 `uv run grecis analyze` 和 `uv run grecis export-redbook` 生成新的结果。

### 自己改规则

- 想改分类，动 `src/grecis/redbook.py` 和 `src/grecis/db.py`
- 想改词典和缓存，动 `src/grecis/dictionary.py`
- 想改 LLM 分析，动 `src/grecis/llm.py`
- 想改本地 NLP，动 `src/grecis/nlp.py`

### 自己开发

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check .
```

如果你要继续扩展成完整项目，推荐沿着“导入 -> 分析 -> 过滤 -> 导出”的链路逐步改，不要先堆 UI。

## 版权与本地使用说明

项目用于本地学习和研究。外刊和真题材料可能受版权保护：

- 不建议公开分发全文语料库
- 红宝书中尽量保存短摘录、URL 和 citation
- 付费墙内容只保存你有权访问和保存的材料

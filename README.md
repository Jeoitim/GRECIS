# GRECIS

GRECIS = Graduate Reading Corpus Intelligence System.

这是一个面向考研英语阅读的领域语料库分析项目。它把新闻、评论、学术短文和真题语料导入本地 SQLite，进行词频、搭配、熟词生义、领域术语和句式结构分析，并导出结构化 Markdown 与 Anki TSV。

## 功能

- 导入 JSONL 文章语料
- 从 URL 抓取正文并清洗文本
- 从 YAML/JSON 配置读取本地明文设置、RSS 源和抓取参数
- 批量抓取 The Guardian、Nature、Science、The Atlantic、Foreign Affairs、NYT Opinion 等公开 RSS 入口
- 按领域识别文章：政治、法律、经济、科技、环境、教育、心理、社会文化
- 统计词频、固定搭配、熟词生义风险词
- 抽取让步、转折、因果、态度和强调句式
- 可选调用 LLM 做更细的词汇分类和文章价值评估
- 导出文章报告、领域词汇库、表达库、熟词生义总表、句式总表和 Anki 卡片

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

从配置的外刊 RSS 源抓取、分析并导出：

```powershell
uv run grecis update-corpus --limit 3
```

只抓取某个来源：

```powershell
uv run grecis fetch-sources --source "The Guardian" --limit 5
uv run grecis analyze
uv run grecis export
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

也可以明文写入本地配置文件。复制：

```powershell
Copy-Item config/local.example.yaml config/local.yaml
```

然后编辑 `config/local.yaml`：

```yaml
llm:
  model: gpt-4.1-mini
  api_key: "sk-..."
database:
  path: data/grecis.sqlite
output:
  markdown_dir: output/markdown
crawler:
  max_articles_per_source: 5
  delay_seconds: 1.0
```

`config/local.yaml`、`config/local.json` 已被 Git 忽略，适合保存本机明文密钥和偏好配置。环境变量优先级更高。

## 外刊来源配置

默认来源在 `config/sources.yaml`。每个来源支持 RSS 和手工 URL：

```yaml
sources:
  - name: The Guardian
    enabled: true
    field_hint: politics
    feed_urls:
      - https://www.theguardian.com/world/rss
    article_urls: []
```

抓取器会：

- 读取 RSS 条目或手工 URL
- 用 `trafilatura` 提取正文，失败时回退到 BeautifulSoup
- 按 URL 去重
- 跳过过短正文
- 按配置限速

请只抓取你有权访问和保存的内容；付费墙、版权受限内容建议只保存链接、摘要和自己生成的学习笔记。

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
├── polysemy.md
├── sentence-patterns.md
└── index.md
```

每篇文章报告包含：

- 领域、难度、考研价值分
- 高频词与领域术语
- 熟词生义
- 固定搭配
- 长难句/逻辑句式
- 原文例句

## 完整工作流

```text
config/sources.yaml 或 config/local.yaml
↓
RSS/URL 抓取
↓
正文提取与清洗
↓
SQLite 去重入库
↓
领域识别、词频、固定表达、熟词生义、句式分析
↓
可选 LLM 语义分类
↓
Markdown 知识库 + Anki TSV
```

## 项目结构

```text
src/grecis/
├── cli.py       # 命令行入口
├── config.py    # YAML/JSON/环境变量配置
├── db.py        # SQLite 存储
├── export.py    # Markdown 和 Anki 导出
├── ingest.py    # JSONL/URL 导入
├── llm.py       # 可选 LLM 分析
├── models.py    # 数据结构
└── nlp.py       # 统计分析
```

## 说明

词典释义目前预留为结构化字段。出于版权和服务条款考虑，项目不会内置柯林斯或牛津全文释义；后续可以接入你有权限使用的词典 API，并只保存允许缓存的短释义或引用信息。

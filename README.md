# GRECIS

GRECIS = Graduate Reading Corpus Intelligence System.

GRECIS 是一个面向考研英语阅读的语料库分析与复习资料生成项目。它把考研真题阅读、外刊文章和本地授权语料导入 SQLite，完成文章质量筛选、领域识别、词频统计、熟词生义识别、固定表达抽取、句式分析，并导出 Markdown 知识库、Anki 卡片和一份按考研阅读主题组织的高质量外刊词汇红宝书。

项目强调三件事：

- 真题优先：以考研阅读真题作为主题锚点和例句优先来源。
- 高质量语料：外刊抓取后先做质量评分，过滤短快讯、体育娱乐、填字游戏和低价值文本。
- 可复习成品：红宝书不是词频全集，而是经过去重、分类、限额和生僻词过滤后的复习资料。

## 功能概览

- 导入 `pastpapers.cn` 考研真题阅读 PDF，提取英语一/英语二 Reading Text 1-4。
- 导入本地 JSONL/CSV/TXT 授权语料。
- 从配置源抓取外刊文章，支持显式 URL、栏目页、archive、站内搜索和 RSS。
- 用本地 NLP 完成领域识别、难度估计、词汇提取、熟词生义和句式识别。
- 可选使用 OpenAI-compatible Chat Completions 模型做深度分析。
- 生成结构化 Markdown 知识库、Anki TSV 和红宝书式 Markdown 复习书。
- 词典释义支持本地缓存、Youdao Suggest、DictionaryAPI.dev、本地 MDX 预留和短语 LLM fallback。

默认输出：

```text
data/grecis.sqlite
output/markdown/
output/redbook/GRECIS-考研外刊词汇红宝书.md
output/anki/grecis_cards.tsv
```

## 快速开始

安装依赖：

```powershell
uv sync --extra dev
```

或使用 Pixi：

```powershell
pixi install
```

验证环境：

```powershell
uv run grecis --help
uv run pytest
```

最短流程：

```powershell
uv run grecis ingest-pastpapers
uv run grecis analyze
uv run grecis export-redbook
```

一键构建真题 + 外刊语料：

```powershell
uv run grecis build-corpus --second-tier-limit 100 --third-tier-limit 20
```

启用 LLM 深度分析：

```powershell
uv run grecis build-corpus --second-tier-limit 100 --third-tier-limit 20 --use-llm
```

## 配置

复制本地配置：

```powershell
Copy-Item config/local.example.yaml config/local.yaml
```

示例：

```yaml
database:
  path: data/grecis.sqlite

output:
  markdown_dir: output/markdown
  redbook_dir: output/redbook

llm:
  model: "provider-model-name"
  base_url: "https://your-provider.example/v1"
  api_key: "your-key"
```

也可以使用环境变量：

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:GRECIS_LLM_MODEL="provider-model-name"
$env:GRECIS_LLM_BASE_URL="https://your-provider.example/v1"
```

`config/local.yaml`、`config/local.json`、`.env` 等本地密钥文件已被 Git 忽略。

LLM 接口要求兼容 Chat Completions。项目支持两类配置：

- SDK 根路径：`https://provider.example/v1`
- 完整端点：`https://provider.example/v1/chat/completions`

完整端点会走项目内置 raw HTTP 兼容路径，避免 SDK 自动拼接路径造成供应商兼容问题。

## 使用指南

### 导入考研真题

```powershell
uv run grecis ingest-pastpapers
```

当前实现会尝试导入：

```text
https://pastpapers.cn/paper/{year}-1
https://pastpapers.cn/paper/{year}-2
```

本地授权真题也可以使用 JSONL：

```powershell
uv run grecis ingest-exam data/my_kaoyan_passages.jsonl
```

JSONL 示例：

```json
{"id":"kaoyan-2024-text1","year":"2024","section":"reading-text-1","title":"...","field":"science","original_source":"...","citation":"2024 English I Text 1","text":"..."}
```

### 构建外刊语料

默认来源在 `config/sources.yaml`。候选文章发现顺序：

```text
显式文章 URL
↓
archive / section / topic 栏目页
↓
由考研真题抽出的主题词站内搜索
↓
RSS 兜底
```

推荐：

```powershell
uv run grecis build-corpus --second-tier-limit 100 --third-tier-limit 20
```

单独抓取某个来源：

```powershell
uv run grecis fetch-sources --source "The Guardian" --limit 100
uv run grecis update-corpus --source "The Atlantic" --limit 100 --use-llm
```

### 分析语料

本地分析：

```powershell
uv run grecis analyze
```

LLM 增强分析：

```powershell
uv run grecis analyze --use-llm
```

只补充还没有 LLM 结果的文章：

```powershell
uv run grecis analyze --use-llm --only-missing-llm
```

当前 LLM 分析默认把词汇、修辞和文章价值三项合并为一次模型调用，并把正文压缩为头/中/尾结构，减少请求次数和 token 使用。需要回到旧的三次调用模式时：

```powershell
$env:GRECIS_LLM_LEGACY_THREE_CALLS="1"
```

### 清洗低质量文章

预览：

```powershell
uv run grecis curate-corpus --dry-run
```

执行：

```powershell
uv run grecis curate-corpus
```

筛选依据包括 `quality_score`、`exam_value`、`difficulty`、文章长度、句长、考研主题密度、熟词生义密度、句式密度和低价值题材关键词。

### 导出资料

红宝书：

```powershell
uv run grecis export-redbook
```

完整 Markdown 知识库和 Anki：

```powershell
uv run grecis export
```

输出结构：

```text
output/markdown/
├── articles/
├── fields/
├── expressions.md
├── polysemy.md
├── sentence-patterns.md
└── index.md

output/redbook/
├── GRECIS-考研外刊词汇红宝书.md
├── GRECIS-考研外刊词汇红宝书-政治法律.md
├── GRECIS-考研外刊词汇红宝书-经贸金融.md
├── GRECIS-考研外刊词汇红宝书-研究方法与学术论证.md
├── GRECIS-考研外刊词汇红宝书-科技互联网与AI.md
├── GRECIS-考研外刊词汇红宝书-医学健康与生命科学.md
├── GRECIS-考研外刊词汇红宝书-环境气候.md
├── GRECIS-考研外刊词汇红宝书-教育社会心理.md
├── GRECIS-考研外刊词汇红宝书-媒体文化与数字版权.md
├── GRECIS-考研外刊词汇红宝书-泛学术核心词.md
├── GRECIS-考研外刊词汇红宝书-未归类附录.md
├── GRECIS-考研外刊词汇红宝书-常见句型与表达.md
└── GRECIS-考研外刊词汇红宝书-7天复习计划.md
```

## 红宝书生成策略

红宝书导出由 `src/grecis/redbook.py` 负责。当前策略：

- 种子词条优先保留。
- 熟词生义、高频短语、考研核心术语优先保留。
- 生僻专业词、噪音词、专名、异常缩写和低价值低频词剔除。
- 未知领域不再默认归入“学术科技”，而是进入泛学术核心词或待复核附录。
- 每个章节有容量上限，避免单章膨胀。
- 分类使用领域词表、上下文、类别、来源字段和词条本身多证据打分。
- 词典释义优先缓存命中，避免重复网络和 LLM 调用。

当前红宝书主题结构：

- 政治法律
- 经贸金融
- 环境气候
- 教育社会心理
- 研究方法与学术论证
- 科技互联网与 AI
- 医学健康与生命科学
- 媒体文化与数字版权
- 泛学术核心词
- 未归类附录

## 词典与缓存

词典入口在 `src/grecis/dictionary.py`。

查询顺序：

```text
data/dict_cache.json
↓
本地 MDX 词典（如已配置）
↓
Youdao Suggest API + DictionaryAPI.dev
↓
短语 LLM fallback
↓
负缓存
```

缓存策略：

- 所有成功查询写入 `data/dict_cache.json`。
- 短语默认允许 LLM fallback，因为普通在线词典通常查不到短语。
- 普通单词默认不走 LLM fallback；如需开启：

```powershell
$env:GRECIS_DICT_LLM_FALLBACK="1"
```

- 查询失败会写入带策略版本的负缓存，避免每次导出重复消耗 token。
- 网络词典连续失败会触发 circuit breaker，自动转为离线/缓存优先模式。

## 技术与架构

### 总体流程

```text
config/local.yaml 或 config/sources.yaml
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

SQLite 默认路径：

```text
data/grecis.sqlite
```

主要表：

- `articles`
- `analyses`
- `vocabulary`
- `collocations`
- `polysemy`
- `sentence_patterns`

文章元数据保存在 `metadata_json`，包括来源、citation、PDF URL、质量分、质量原因等。

### 来源优先级

第一层：考研真题语料

- `pastpapers.cn` PDF 解析导入
- 用户本地授权真题 JSONL/CSV/TXT
- 质量分固定为最高优先级
- 红宝书例句优先使用 citation

第二层：高相似外刊来源

- The Christian Science Monitor
- The Guardian
- The Atlantic

第三层：扩展外刊和报刊

- The Economist
- Financial Times
- Wall Street Journal
- Bloomberg Businessweek
- Nature
- Science
- Scientific American
- New Scientist
- National Geographic
- Time
- Newsweek
- The Washington Post
- USA Today
- Foreign Affairs
- U.S. News & World Report
- The Times
- New York Times Opinion / Science / Business / Climate

## 命令速查

```powershell
uv run grecis run-demo
uv run grecis ingest-pastpapers
uv run grecis ingest-exam data/my_kaoyan_passages.jsonl
uv run grecis fetch-sources --source "The Guardian" --limit 10
uv run grecis update-corpus --source "The Atlantic" --limit 50 --use-llm
uv run grecis analyze
uv run grecis analyze --use-llm --only-missing-llm
uv run grecis curate-corpus --dry-run
uv run grecis export
uv run grecis export-redbook
uv run grecis build-corpus --second-tier-limit 100 --third-tier-limit 20
```

## 开发与质量检查

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

当前测试覆盖配置加载、导入、NLP、质量评分、真题抓取、红宝书筛选、词典 fallback 和 LLM 调用兼容逻辑。

## 版权与本地使用说明

项目用于本地学习和研究。外刊和真题材料可能受版权保护：

- 不建议把抓取到的全文提交到 Git。
- 不建议公开分发生成的全文语料数据库。
- 红宝书中应尽量保存短摘录、URL 和 citation。
- 付费墙内容应只保存你有权访问和保存的材料。

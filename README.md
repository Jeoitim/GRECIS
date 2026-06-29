# GRECIS

GRECIS = Graduate Reading Corpus Intelligence System.

GRECIS 是一个面向考研英语阅读的语料库分析与复习资料生成项目。它把考研真题阅读、外刊文章和你自己的本地语料导入 SQLite，做领域识别、词频统计、熟词生义识别、固定表达抽取和句式分析，最后生成结构化 Markdown、Anki TSV，以及一份离线生成、去重后的考研英语外刊词汇红宝书。

当前项目优先级是：

1. 考研真题阅读语料
2. The Christian Science Monitor、The Guardian、The Atlantic
3. 其他外刊来源

生成结果默认保存在：

```text
data/grecis.sqlite
output/markdown/
output/redbook/GRECIS-考研外刊词汇红宝书.md
output/anki/grecis_cards.tsv
```

## 用户指引

### 1. 安装环境

使用 `uv`：

```powershell
uv sync --extra dev
```

或使用 `pixi`：

```powershell
pixi install
```

验证项目可运行：

```powershell
uv run grecis --help
uv run pytest
```

### 2. 配置模型 API

项目的基础抓取、词频、熟词生义和红宝书生成不强制需要 LLM。只有运行 `--use-llm` 时才会调用模型，且当前红宝书仍可完全离线生成。

复制本地配置文件：

```powershell
Copy-Item config/local.example.yaml config/local.yaml
```

编辑 `config/local.yaml`：

```yaml
llm:
  model: "provider-model-name"
  base_url: "https://your-provider.example/v1"
  api_key: "your-key"

database:
  path: data/grecis.sqlite

output:
  markdown_dir: output/markdown
  redbook_dir: output/redbook
```

`config/local.yaml` 和 `config/local.json` 已被 Git 忽略，适合保存本机明文密钥。也可以用环境变量：

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:GRECIS_LLM_MODEL="your-model"
$env:GRECIS_LLM_BASE_URL="https://your-provider.example/v1"
```

模型接口要求兼容 OpenAI Chat Completions 格式，例如 OpenAI、DeepSeek 兼容入口、One API、LiteLLM、本地网关等。

### 3. 导入考研真题阅读

优先推荐导入考研真题。项目支持从 `pastpapers.cn` 抓取可访问 PDF，提取 `Section II Reading Comprehension / Part A / Text 1-4`。

```powershell
uv run grecis ingest-pastpapers
uv run grecis analyze
uv run grecis export-redbook
```

当前实现会尝试导入：

```text
https://pastpapers.cn/paper/{year}-1
https://pastpapers.cn/paper/{year}-2
```

本地已验证可导入 2010-2025 英语一/英语二共 32 套、128 篇阅读文章。每篇文章都会保存 citation，例如：

```text
pastpapers.cn 2024-1 Reading Text 1: https://pastpapers.cn/paper/2024-1
```

如果你有自己的授权真题文本，也可以导入本地 JSONL/CSV/TXT：

```powershell
uv run grecis ingest-exam data/my_kaoyan_passages.jsonl
uv run grecis analyze
uv run grecis export-redbook
```

JSONL 示例：

```json
{"id":"kaoyan-2024-text1","year":"2024","section":"reading-text-1","title":"...","field":"science","original_source":"...","citation":"2024 English I Text 1","text":"..."}
```

### 4. 构建高质量外刊语料

默认来源在 `config/sources.yaml`。现在不再只依赖 RSS，而是按下面的顺序发现候选文章：

```text
显式文章 URL
↓
archive / section / topic 栏目页
↓
由考研真题抽出的主题词站内搜索
↓
RSS 兜底
```

推荐直接运行一键构建命令：

```powershell
uv run grecis build-corpus --second-tier-limit 100 --third-tier-limit 20
```

这会执行：

```text
导入 pastpapers.cn 真题阅读
↓
从真题抽取主题查询词，例如 climate change / supreme court / social media
↓
The Christian Science Monitor / The Guardian / The Atlantic 每源最多 100 篇
↓
其他来源每源最多 20 篇
↓
本地 NLP 分析
↓
Markdown + 红宝书导出
```

如果已经配置 OpenAI-compatible 模型 API，可以启用 LLM 深度分析：

```powershell
uv run grecis build-corpus --second-tier-limit 100 --third-tier-limit 20 --use-llm
```

LLM 分析会对文章做词汇、修辞结构、考研价值评估，调用量约等于待分析文章数的 3 倍。若只想先扩充语料，先不加 `--use-llm`，完成后再运行 `uv run grecis analyze --use-llm`。

仍然可以单独抓某个来源：

```powershell
uv run grecis fetch-sources --source "The Guardian" --limit 100
uv run grecis update-corpus --source "The Atlantic" --limit 100
```

### 5. 清洗低质量文章

先预览将删除多少篇：

```powershell
uv run grecis curate-corpus --dry-run
```

确认后执行：

```powershell
uv run grecis curate-corpus
```

筛选依据包括：

- `quality_score`
- `exam_value`
- `difficulty`
- 是否命中体育、娱乐、填字游戏、短快讯等低价值题材

### 6. 生成复习资料

生成红宝书：

```powershell
uv run grecis export-redbook
```

输出：

```text
output/redbook/GRECIS-考研外刊词汇红宝书.md
```

红宝书当前包含：

- 快速背诵清单
- 政治法律、经贸金融、学术科技、环境气候、教育社会心理分章（已深度整合种子词条与本地语料词条）
- 词条智能归类（熟词生义、高频短语、领域术语、学术词汇）
- 自动获取标准音标（来自 DictionaryAPI.dev / Youdao API 与本地缓存）
- 词条释义、简明英英义、核心中文义、常见义、考研义
- 熟词生义与误译风险提示
- 高频搭配（在一行中紧凑展示）与近义辨析
- 经典真题例句与本地语料库溯源例句（自动对目标词汇及其变体如时态进行高亮加粗）
- 7 天复习安排

生成完整 Markdown 知识库：

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
```

### 7. 常用命令速查

```powershell
uv run grecis run-demo
uv run grecis ingest-pastpapers
uv run grecis ingest-exam data/my_kaoyan_passages.jsonl
uv run grecis fetch-sources --source "The Guardian" --limit 10
uv run grecis update-corpus --source "The Atlantic" --limit 50 --use-llm
uv run grecis analyze
uv run grecis curate-corpus --dry-run
uv run grecis export
uv run grecis export-redbook
```

## 资料获取可靠度

### 来源优先级

项目当前明确采用三层优先级。

第一层：考研真题语料

- `pastpapers.cn` PDF 解析导入
- 用户本地授权真题 JSONL/CSV/TXT
- 质量分固定为最高优先级
- 红宝书例句优先使用 citation

第二层：高相似外刊来源

- The Christian Science Monitor
- The Guardian
- The Atlantic

这些来源更贴近考研阅读常见的社会文化、教育、公共议题、评论性文章风格，因此质量权重高于其他外刊。

第三层：其他外刊和报刊

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

这些来源用于扩展领域覆盖，但质量权重低于真题和第二层来源。

### 来源配置

每个来源在 `config/sources.yaml` 中配置：

```yaml
sources:
  - name: The Guardian
    enabled: true
    field_hint: politics
    category: society_culture
    reliability: 0.9
    quality_weight: 1.1
    prefer_keywords: [comment, analysis, environment, science, business, education]
    exclude_keywords: [football, sport, live, minute-by-minute, crossword]
    feed_urls:
      - https://www.theguardian.com/world/rss
```

### 质量筛选算法

质量评分在 `src/grecis/quality.py` 中实现。主要考虑：

- 来源层级和来源可靠度
- 正文长度
- 平均句长
- 是否包含考研常见题材关键词
- 是否命中排除关键词
- 熟词生义密度
- 句式和论证结构密度
- 是否像短快讯或通讯社简讯

考研真题语料直接标记为：

```text
quality_score = 10.0
quality_keep = true
quality_reasons = ["kaoyan_exam_corpus"]
```

外刊文章会保存：

```text
quality_score
quality_keep
quality_reasons
token_count
sentence_count
avg_sentence_len
polysemy_count
pattern_count
```

### 版权和本地使用说明

项目用于本地学习和研究。外刊和真题材料可能受版权保护：

- 不建议把抓取到的全文提交到 Git
- 不建议公开分发生成的全文语料数据库
- 红宝书中应尽量保存短摘录、URL 和 citation
- 付费墙内容应只保存你有权访问和保存的材料

## 技术架构

### 总体流程

```text
config/local.yaml 或 config/sources.yaml
↓
真题 PDF / 本地语料 / RSS / URL
↓
正文提取与清洗
↓
质量评分与过滤
↓
SQLite 去重入库
↓
基础 NLP 分析
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
├── db.py           # SQLite 存储与聚合查询
├── export.py       # Markdown 和 Anki 导出
├── ingest.py       # JSONL/URL/历史栏目/主题搜索/RSS 导入
├── llm.py          # OpenAI-compatible Chat Completions 分析
├── models.py       # 数据结构
├── nlp.py          # 本地统计、词频、熟词生义、句式识别
├── pastpapers.py   # pastpapers.cn PDF 真题导入
├── quality.py      # 来源可靠度和文章质量评分
├── topics.py       # 从考研真题反向抽取语料扩展主题
└── redbook.py      # 红宝书式 Markdown 生成
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

### LLM 接口

LLM 是可选增强层。当前使用 OpenAI-compatible Chat Completions：

```python
client.chat.completions.create(...)
```

支持配置：

```yaml
llm:
  model: "provider-model-name"
  base_url: "https://your-provider.example/v1"
  api_key: "your-key"
```

未提供 API Key 时，项目仍可完成抓取、基础分析和红宝书生成。红宝书的成书不依赖 LLM 在线调用，LLM 仅用于补充分析结果。

### 测试与质量检查

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

### 词典释义与音标集成

项目已内置了一套高效、高容错的音标与释义查询系统：

1. **多数据源集成**：结合了 **Youdao Suggest API**（快速获取简明汉译）与 **DictionaryAPI.dev**（标准 IPA 音标及英文释义）。
2. **本地文件缓存**：查询结果会自动写入并缓存于 `data/dict_cache.json` 中，再次运行导出命令时直接从缓存读取，实现 0 秒毫秒级渲染并支持完全离线运行。
3. **网络断路器保护 (Circuit Breaker)**：默认网络超时时间缩短为 1.0s，且若网络连接失败或超时连续达到 3 次，系统将自动切断网络并转换为离线导出模式，防止编译挂起。
4. **例句高亮高还原**：在生成的单词卡片中，真题及语料库例句中的目标词汇（包括其不规则时态及分词变体，如 `hold` -> `held`）会自动替换为 `**word**` 加粗高亮。
5. **本地 MDX 词典（预留）**：如需替换为更权威的出版级词汇库，您可以本地引入 `readmdict` 模块，直接解析个人拥有的离线 `.mdx` 词典数据。

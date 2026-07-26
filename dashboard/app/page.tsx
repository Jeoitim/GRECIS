"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type View = "reader" | "library" | "vocabulary" | "history";
type Level = "learning" | "familiar" | "mastered";
type Health = {
  counts: { articles: number; analyses: number; vocabulary: number; collocations: number };
  unique_words: number;
  fields: string[];
};
type ArticleSummary = {
  id: string;
  title: string;
  source: string;
  url: string;
  published_at: string;
  field: string;
  created_at: string;
  difficulty: number | null;
  exam_value: number | null;
  progress: number;
  last_read_at: string;
  word_count: number;
  snippet: string;
};
type VocabularyItem = {
  word: string;
  lemma: string;
  field?: string;
  fields?: string;
  category?: string;
  categories?: string;
  frequency: number;
  importance: number;
  article_count?: number;
  example_sentence?: string;
  mastery?: Level | null;
};
type ArticleDetail = ArticleSummary & {
  text: string;
  metadata: Record<string, unknown>;
  analysis: {
    field: string;
    difficulty: number;
    exam_value: number;
    created_at: string;
  };
  digest: {
    insight: string;
    structure: string;
    domain: string;
    note: string;
    model: string;
    rhetoric_count: number;
  };
  vocabulary: VocabularyItem[];
  collocations: Array<{ expression: string; meaning: string; importance: number }>;
  polysemy: Array<{ word: string; contextual_meaning: string }>;
  sentence_patterns: Array<{ type: string; function: string; sentence: string }>;
};
type HistoryItem = {
  article_id: string;
  title: string;
  source: string;
  field: string;
  difficulty: number;
  exam_value: number;
  created_at: string;
  mode: string;
  model: string;
};
type Settings = { model: string; base_url: string; api_key_set: boolean };
type Tooltip = {
  word: string;
  x: number;
  y: number;
  phonetic: string;
  pos: string;
  zh: string;
  en: string;
  loading?: boolean;
};

const PAGE_SIZE = 24;
const WORD_PAGE_SIZE = 40;
const HISTORY_PAGE_SIZE = 24;
const API_ROOT = "http://127.0.0.1:8765/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `请求失败（${response.status}）`);
  return data as T;
}

function formatDate(value: string) {
  if (!value) return "日期未知";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric" }).format(date);
}

function readingMinutes(words: number) {
  return Math.max(1, Math.round(words / 180));
}

function paragraphsFrom(text: string) {
  const blocks = text.split(/\n\s*\n|\r\n\s*\r\n/).map((item) => item.trim()).filter(Boolean);
  if (blocks.length > 1) return blocks;
  const sentences = text.match(/[^.!?]+[.!?]+(?:["’”])?/g) || [text];
  const grouped: string[] = [];
  for (let index = 0; index < sentences.length; index += 4) {
    grouped.push(sentences.slice(index, index + 4).join(" ").trim());
  }
  return grouped.filter(Boolean);
}

function Icon({ children }: { children: React.ReactNode }) {
  return <span className="icon" aria-hidden="true">{children}</span>;
}

export default function Home() {
  const [view, setView] = useState<View>("reader");
  const [health, setHealth] = useState<Health | null>(null);
  const [recent, setRecent] = useState<ArticleSummary[]>([]);
  const [detail, setDetail] = useState<ArticleDetail | null>(null);
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [articleTotal, setArticleTotal] = useState(0);
  const [articlePage, setArticlePage] = useState(0);
  const [articleQuery, setArticleQuery] = useState("");
  const [articleField, setArticleField] = useState("");
  const [words, setWords] = useState<VocabularyItem[]>([]);
  const [wordTotal, setWordTotal] = useState(0);
  const [wordPage, setWordPage] = useState(0);
  const [wordQuery, setWordQuery] = useState("");
  const [masteryFilter, setMasteryFilter] = useState("");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(0);
  const [levels, setLevels] = useState<Record<string, Level>>({});
  const [settings, setSettings] = useState<Settings>({ model: "", base_url: "", api_key_set: false });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [dark, setDark] = useState(() => {
    if (typeof window === "undefined") return false;
    const stored = window.localStorage.getItem("grecis-theme");
    return stored === "dark" || (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches);
  });
  const [focus, setFocus] = useState(false);
  const [dictionary, setDictionary] = useState(true);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);
  const [fontSize, setFontSize] = useState(19);
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const hoverTimer = useRef<number | null>(null);
  const closeTimer = useRef<number | null>(null);
  const lookupRequest = useRef<AbortController | null>(null);

  const viewLabels: Record<View, string> = {
    reader: "阅读台",
    library: "语料库",
    vocabulary: "词汇簿",
    history: "分析记录",
  };

  const lemmaMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const item of detail?.vocabulary || []) {
      map[item.word.toLowerCase()] = item.lemma.toLowerCase();
      map[item.lemma.toLowerCase()] = item.lemma.toLowerCase();
    }
    return map;
  }, [detail]);

  const masteryStats = useMemo(() => {
    const values = Object.values(levels);
    return {
      learning: values.filter((level) => level === "learning").length,
      familiar: values.filter((level) => level === "familiar").length,
      mastered: values.filter((level) => level === "mastered").length,
    };
  }, [levels]);

  async function loadInitial() {
    setBusy("initial");
    setError("");
    try {
      const [healthData, recentData, settingsData] = await Promise.all([
        request<Health>("/health"),
        request<{ items: ArticleSummary[]; total: number }>("/articles?limit=12"),
        request<Settings>("/settings"),
      ]);
      setHealth(healthData);
      setRecent(recentData.items);
      setSettings(settingsData);
      if (recentData.items[0]) await openArticle(recentData.items[0].id, false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法连接本地语料服务");
    } finally {
      setBusy("");
    }
  }

  async function loadArticles() {
    setBusy("library");
    try {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(articlePage * PAGE_SIZE),
      });
      if (articleQuery) params.set("q", articleQuery);
      if (articleField) params.set("field", articleField);
      const data = await request<{ items: ArticleSummary[]; total: number }>(`/articles?${params}`);
      setArticles(data.items);
      setArticleTotal(data.total);
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "语料加载失败", true);
    } finally {
      setBusy("");
    }
  }

  async function loadWords() {
    setBusy("vocabulary");
    try {
      const params = new URLSearchParams({
        limit: String(WORD_PAGE_SIZE),
        offset: String(wordPage * WORD_PAGE_SIZE),
      });
      if (wordQuery) params.set("q", wordQuery);
      if (masteryFilter) params.set("mastery", masteryFilter);
      const data = await request<{ items: VocabularyItem[]; total: number }>(`/vocabulary?${params}`);
      setWords(data.items);
      setWordTotal(data.total);
      setLevels((current) => {
        const next = { ...current };
        for (const item of data.items) {
          if (item.mastery) next[item.lemma] = item.mastery;
          else delete next[item.lemma];
        }
        return next;
      });
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "词汇加载失败", true);
    } finally {
      setBusy("");
    }
  }

  async function loadHistory() {
    setBusy("history");
    try {
      const data = await request<{ items: HistoryItem[]; total: number }>(
        `/analysis-history?limit=${HISTORY_PAGE_SIZE}&offset=${historyPage * HISTORY_PAGE_SIZE}`,
      );
      setHistory(data.items);
      setHistoryTotal(data.total);
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "记录加载失败", true);
    } finally {
      setBusy("");
    }
  }

  async function openArticle(id: string, switchView = true) {
    clearPendingLookup();
    setTooltip(null);
    if (switchView) setView("reader");
    setBusy("article");
    try {
      const data = await request<ArticleDetail>(`/articles/${encodeURIComponent(id)}`);
      setDetail(data);
      setRecent((items) => [
        { ...data, progress: Math.max(data.progress, 1), last_read_at: new Date().toISOString() },
        ...items.filter((item) => item.id !== data.id),
      ].slice(0, 12));
      const nextLevels: Record<string, Level> = {};
      for (const item of data.vocabulary) {
        if (item.mastery) nextLevels[item.lemma.toLowerCase()] = item.mastery;
      }
      setLevels(nextLevels);
      void request(`/articles/${encodeURIComponent(id)}/progress`, {
        method: "PUT",
        body: JSON.stringify({ progress: Math.max(data.progress, 1) }),
      });
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "文章加载失败", true);
    } finally {
      setBusy("");
    }
  }

  function showToast(message: string, failed = false) {
    setToast(`${failed ? "!" : "✓"}|${message}`);
    window.setTimeout(() => setToast(""), 3200);
  }

  function clearPendingLookup() {
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
    hoverTimer.current = null;
    lookupRequest.current?.abort();
    lookupRequest.current = null;
  }

  function scheduleClose() {
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
    hoverTimer.current = null;
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => {
      lookupRequest.current?.abort();
      setTooltip(null);
    }, 180);
  }

  function keepPopoverOpen() {
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
  }

  function scheduleLookup(raw: string, rect: DOMRect, delay = 1250) {
    if (!dictionary) return;
    clearPendingLookup();
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
    setTooltip(null);
    hoverTimer.current = window.setTimeout(() => void lookup(raw, rect), delay);
  }

  async function lookup(raw: string, rect: DOMRect) {
    const word = raw.toLowerCase().replace(/[^a-z'-]/g, "");
    if (word.length < 2) return;
    setTooltip({
      word, x: rect.left + rect.width / 2, y: rect.bottom + 10,
      phonetic: "", pos: "", zh: "正在查询本地词典…", en: "", loading: true,
    });
    const controller = new AbortController();
    lookupRequest.current = controller;
    try {
      const data = await request<{ word: string; phonetic: string; pos: string; zh: string; en: string }>(
        `/dictionary/${encodeURIComponent(word)}`,
        { signal: controller.signal },
      );
      setTooltip({ ...data, x: rect.left + rect.width / 2, y: rect.bottom + 10 });
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setTooltip({
        word, x: rect.left + rect.width / 2, y: rect.bottom + 10, phonetic: "", pos: "",
        zh: "暂未查到释义", en: reason instanceof Error ? reason.message : "",
      });
    }
  }

  async function cycleLevel(raw: string) {
    const lemma = (lemmaMap[raw.toLowerCase()] || raw).toLowerCase();
    const order: Array<Level | undefined> = [undefined, "learning", "familiar", "mastered"];
    const next = order[(order.indexOf(levels[lemma]) + 1) % order.length];
    setLevels((current) => {
      const copy = { ...current };
      if (next) copy[lemma] = next;
      else delete copy[lemma];
      return copy;
    });
    setWords((items) => items.map((item) => item.lemma === lemma ? { ...item, mastery: next || null } : item));
    setTooltip(null);
    try {
      await request(`/vocabulary/${encodeURIComponent(lemma)}/mastery`, {
        method: "PUT",
        body: JSON.stringify({ level: next || null }),
      });
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "掌握度保存失败", true);
    }
  }

  function renderParagraph(text: string) {
    return text.split(/(\b[A-Za-z][A-Za-z'-]*\b)/g).map((part, index) => {
      if (!/^[A-Za-z]/.test(part)) return part;
      const raw = part.toLowerCase();
      const lemma = lemmaMap[raw] || raw;
      return (
        <span
          key={`${raw}-${index}`}
          className={`word ${levels[lemma] ? `level-${levels[lemma]}` : ""}`}
          onMouseEnter={(event) => scheduleLookup(part, event.currentTarget.getBoundingClientRect())}
          onMouseLeave={scheduleClose}
          onFocus={(event) => scheduleLookup(part, event.currentTarget.getBoundingClientRect(), 0)}
          onBlur={scheduleClose}
          onClick={() => void cycleLevel(lemma)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") void cycleLevel(lemma);
          }}
          tabIndex={0}
        >{part}</span>
      );
    });
  }

  async function saveSettings(event: FormEvent) {
    event.preventDefault();
    setBusy("settings-save");
    try {
      const data = await request<Settings>("/settings", {
        method: "PUT",
        body: JSON.stringify({ model: settings.model, base_url: settings.base_url, api_key: apiKey || null }),
      });
      setSettings(data);
      setApiKey("");
      setSettingsOpen(false);
      showToast("模型设置已写入 config/local.yaml");
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "设置保存失败", true);
    } finally {
      setBusy("");
    }
  }

  async function testConnection() {
    setBusy("settings-test");
    try {
      const data = await request<{ ok: boolean; message: string }>("/settings/test", {
        method: "POST",
        body: JSON.stringify({ model: settings.model, base_url: settings.base_url, api_key: apiKey || null }),
      });
      showToast(data.message);
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "连接失败", true);
    } finally {
      setBusy("");
    }
  }

  async function analyzeCurrent() {
    if (!detail) return;
    setBusy("analyze");
    try {
      const data = await request<ArticleDetail>(
        `/articles/${encodeURIComponent(detail.id)}/analyze?use_llm=true`,
        { method: "POST" },
      );
      setDetail(data);
      showToast("Python NLP + LLM 分析已完成并写入数据库");
      void loadHistory();
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "分析失败", true);
    } finally {
      setBusy("");
    }
  }

  async function addArticle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy("add");
    try {
      const data = await request<ArticleDetail>("/articles", {
        method: "POST",
        body: JSON.stringify({
          title: String(form.get("title") || ""),
          source: String(form.get("source") || "manual"),
          url: String(form.get("url") || ""),
          text: String(form.get("text") || ""),
          use_llm: form.get("use_llm") === "on",
        }),
      });
      setAddOpen(false);
      setRecent((items) => [data, ...items.filter((item) => item.id !== data.id)].slice(0, 12));
      setHealth((current) => current ? {
        ...current,
        counts: { ...current.counts, articles: current.counts.articles + 1, analyses: current.counts.analyses + 1 },
      } : current);
      setDetail(data);
      setView("reader");
      showToast("文章已由 Python 语料链路导入并分析");
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "文章导入失败", true);
    } finally {
      setBusy("");
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadInitial();
    // Initial corpus connection should run once when the reading desk mounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("grecis-theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (view === "library") void loadArticles();
    // The query state below is the intentional refresh boundary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, articlePage, articleQuery, articleField]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (view === "vocabulary") void loadWords();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, wordPage, wordQuery, masteryFilter]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (view === "history") void loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, historyPage]);

  const author = String(detail?.metadata.author || detail?.metadata.byline || detail?.source || "Corpus");
  const titleParts = detail?.title.split(" ") || [];
  const masteryLabel = (level?: Level | null) =>
    level === "learning" ? "待掌握" : level === "familiar" ? "似曾相识" : level === "mastered" ? "已掌握" : "未标记";

  if (error) {
    return (
      <main className="connection-page">
        <div className="brand-mark">G</div>
        <span className="eyebrow">LOCAL CORPUS OFFLINE</span>
        <h1>尚未连接 Python 语料服务</h1>
        <p>{error}</p>
        <code>uv run grecis-web</code>
        <button onClick={() => void loadInitial()}>重新连接</button>
      </main>
    );
  }

  return (
    <div className={`app-shell ${focus ? "focus-mode" : ""}`}>
      <aside className="sidebar">
        <div className="brand-row">
          <div className="brand-mark">G</div>
          <div><strong>GRECIS</strong><span>阅读语料研究室</span></div>
        </div>

        <nav className="primary-nav" aria-label="主导航">
          <button className={view === "reader" ? "nav-active" : ""} onClick={() => setView("reader")}><Icon>◫</Icon> 阅读台 <kbd>R</kbd></button>
          <button className={view === "library" ? "nav-active" : ""} onClick={() => setView("library")}><Icon>◇</Icon> 语料库 <span className="nav-count">{health?.counts.articles || "—"}</span></button>
          <button className={view === "vocabulary" ? "nav-active" : ""} onClick={() => setView("vocabulary")}><Icon>✣</Icon> 词汇簿 <span className="nav-count">{health?.unique_words.toLocaleString() || "—"}</span></button>
          <button className={view === "history" ? "nav-active" : ""} onClick={() => setView("history")}><Icon>≋</Icon> 分析记录 <span className="nav-count">{health?.counts.analyses || "—"}</span></button>
        </nav>

        <div className="library-heading"><span>最近篇目</span><button onClick={() => setAddOpen(true)} aria-label="增加文章">＋</button></div>
        <div className="article-list">
          {recent.map((article) => (
            <button key={article.id} className={`article-item ${detail?.id === article.id && view === "reader" ? "active" : ""}`} onClick={() => void openArticle(article.id)}>
              <span className="article-topic">{article.field}</span>
              <strong>{article.title}</strong>
              <span>{article.source} · {readingMinutes(article.word_count)} 分钟</span>
              <i><b style={{ width: `${article.progress}%` }} /></i>
            </button>
          ))}
        </div>

        <button className="settings-entry" onClick={() => setSettingsOpen(true)}>
          <Icon>⚙</Icon><span>模型与 API</span><small>{settings.model || "加载中"}</small>
        </button>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="breadcrumbs"><span>{view === "reader" ? detail?.analysis.field || "语料" : "GRECIS"}</span><b>/</b><span>{viewLabels[view]}</span></div>
          <div className="top-actions">
            {view === "reader" && <button className={`text-button ${dictionary ? "is-on" : ""}`} onClick={() => { setDictionary(!dictionary); clearPendingLookup(); setTooltip(null); }}><i />悬停查词 · 1.25s</button>}
            <button className="circle-button" onClick={() => setFocus(!focus)} aria-label="切换专注模式">{focus ? "↙" : "↗"}</button>
            <button className="circle-button" onClick={() => setDark(!dark)} aria-label="切换深色模式">{dark ? "☀" : "◐"}</button>
          </div>
        </header>

        {view === "reader" && detail && (
          <div className="reading-layout" key={detail.id}>
            <article className="reader">
              <div className="article-kicker"><span>{detail.source} · CORPUS</span><i /></div>
              <h1>{titleParts.slice(0, -1).join(" ")} <em>{titleParts.at(-1)}</em></h1>
              <p className="deck">{detail.snippet}</p>
              <div className="byline">
                <div className="avatar">{author.split(/\s+/).slice(0, 2).map((name) => name[0]).join("").toUpperCase()}</div>
                <div><strong>{author}</strong><span>{detail.source} · {formatDate(detail.published_at || detail.created_at)}</span></div>
                <div className="reading-meta"><b>{detail.word_count.toLocaleString()}</b><span>WORDS</span></div>
                <div className="reading-meta"><b>{readingMinutes(detail.word_count)} min</b><span>READ</span></div>
              </div>

              <div className="reader-rule" />
              <div className="reader-toolbar">
                <div className="legend">
                  <button><i className="dot learning" />待掌握 <b>{masteryStats.learning}</b></button>
                  <button><i className="dot familiar" />似曾相识 <b>{masteryStats.familiar}</b></button>
                  <button><i className="dot mastered" />已掌握 <b>{masteryStats.mastered}</b></button>
                </div>
                <div className="font-control">
                  <button onClick={() => setFontSize(Math.max(16, fontSize - 1))}>A−</button><span>{fontSize}</span>
                  <button onClick={() => setFontSize(Math.min(24, fontSize + 1))}>A＋</button>
                </div>
              </div>
              <div className="prose" style={{ fontSize }}>
                {paragraphsFrom(detail.text).map((paragraph, index) => <p key={index}>{renderParagraph(paragraph)}</p>)}
              </div>
              <div className="page-end">
                <span>{detail.vocabulary.length}</span><i /><span>WORDS TO REVIEW</span>
                <button onClick={() => {
                  const index = recent.findIndex((item) => item.id === detail.id);
                  if (recent.length) void openArticle(recent[(index + 1) % recent.length].id);
                }}>下一篇 <b>→</b></button>
              </div>
            </article>

            <aside className="margin-panel">
              <div className="analysis-card">
                <div className="card-heading"><span>本篇洞察</span><small>{detail.digest.model ? "LLM" : "NLP"}</small></div>
                <p>{detail.digest.insight}</p>
                <div className="score-ring"><b>{Math.round((detail.analysis.exam_value || 0) * 10)}</b><span>阅读价值</span></div>
                <dl>
                  <div><dt>论证结构</dt><dd>{detail.digest.structure}</dd></div>
                  <div><dt>核心领域</dt><dd>{detail.digest.domain}</dd></div>
                  <div><dt>语言难度</dt><dd>{Number(detail.analysis.difficulty || 0).toFixed(1)} / 10</dd></div>
                </dl>
              </div>
              <div className="margin-note"><span>精读提示 01</span><p>{detail.digest.note}</p></div>
              <button className="analyze-button" onClick={() => void analyzeCurrent()} disabled={busy === "analyze"}>
                <Icon>{busy === "analyze" ? "◌" : "✦"}</Icon>
                <span><strong>{busy === "analyze" ? "Python 正在分析…" : "重新进行 LLM + NLP 分析"}</strong><small>{settings.model} · 写入 SQLite</small></span>
              </button>
              <div className="corpus-note"><b>{detail.collocations.length}</b> 个搭配 · <b>{detail.polysemy.length}</b> 个熟词生义 · <b>{detail.sentence_patterns.length}</b> 个句式</div>
            </aside>
          </div>
        )}

        {view === "reader" && !detail && <div className="page-loading">正在从本地语料库读取文章…</div>}

        {view === "library" && (
          <section className="workspace-page">
            <div className="workspace-title">
              <div><span className="eyebrow">CORPUS · SQLITE</span><h1>语料库</h1><p>全部内容动态读取自 data/grecis.sqlite。</p></div>
              <button className="solid-action" onClick={() => setAddOpen(true)}>＋ 加入文章</button>
            </div>
            <div className="summary-grid">
              <div><span>全部语料</span><b>{health?.counts.articles || 0}</b><small>篇文章</small></div>
              <div><span>已分析</span><b>{health?.counts.analyses || 0}</b><small>份结果</small></div>
              <div><span>词汇记录</span><b>{health?.counts.vocabulary.toLocaleString() || 0}</b><small>{health?.unique_words.toLocaleString()} 个词元</small></div>
            </div>
            <div className="query-bar">
              <input value={articleQuery} onChange={(event) => { setArticlePage(0); setArticleQuery(event.target.value); }} placeholder="搜索标题、来源或正文…" />
              <select value={articleField} onChange={(event) => { setArticlePage(0); setArticleField(event.target.value); }}>
                <option value="">全部领域</option>{health?.fields.map((field) => <option key={field}>{field}</option>)}
              </select>
            </div>
            <div className="data-sheet">
              <div className="sheet-toolbar"><strong>{busy === "library" ? "读取中…" : `找到 ${articleTotal} 篇`}</strong><span>第 {articlePage + 1} 页</span></div>
              {articles.map((article, index) => (
                <button className="library-row" key={article.id} onClick={() => void openArticle(article.id)}>
                  <span className="row-index">{String(articlePage * PAGE_SIZE + index + 1).padStart(3, "0")}</span>
                  <span className="row-title"><strong>{article.title}</strong><small>{article.source} · {formatDate(article.published_at || article.created_at)}</small></span>
                  <span className="topic-pill">{article.field}</span>
                  <span className="row-score">{Math.round((article.exam_value || 0) * 10)}<small>价值</small></span>
                  <span className="row-progress"><i><b style={{ width: `${article.progress}%` }} /></i><small>{article.progress}%</small></span>
                  <span>→</span>
                </button>
              ))}
            </div>
            <div className="pagination">
              <button disabled={articlePage === 0} onClick={() => setArticlePage((page) => page - 1)}>← 上一页</button>
              <span>{articlePage + 1} / {Math.max(1, Math.ceil(articleTotal / PAGE_SIZE))}</span>
              <button disabled={(articlePage + 1) * PAGE_SIZE >= articleTotal} onClick={() => setArticlePage((page) => page + 1)}>下一页 →</button>
            </div>
          </section>
        )}

        {view === "vocabulary" && (
          <section className="workspace-page">
            <div className="workspace-title">
              <div><span className="eyebrow">VOCABULARY · SQLITE</span><h1>词汇簿</h1><p>{health?.counts.vocabulary.toLocaleString()} 条文章词汇记录，共 {health?.unique_words.toLocaleString()} 个去重词元。</p></div>
            </div>
            <div className="query-bar">
              <input value={wordQuery} onChange={(event) => { setWordPage(0); setWordQuery(event.target.value); }} placeholder="搜索词或词元…" />
              <select value={masteryFilter} onChange={(event) => { setWordPage(0); setMasteryFilter(event.target.value); }}>
                <option value="">全部掌握度</option><option value="unmarked">未标记</option><option value="learning">待掌握</option><option value="familiar">似曾相识</option><option value="mastered">已掌握</option>
              </select>
            </div>
            <div className="word-grid">
              {words.map((item, index) => (
                <button className="word-card" key={item.lemma} onClick={() => void cycleLevel(item.lemma)}>
                  <span className="word-number">{String(wordPage * WORD_PAGE_SIZE + index + 1).padStart(4, "0")}</span>
                  <div><strong>{item.lemma}</strong><small>{item.categories || item.category} · 出现于 {item.article_count} 篇</small><p>{item.example_sentence || item.fields || item.field}</p></div>
                  <span className={`mastery-label ${levels[item.lemma] || "unmarked"}`}>{masteryLabel(levels[item.lemma])}</span>
                </button>
              ))}
            </div>
            <div className="pagination">
              <button disabled={wordPage === 0} onClick={() => setWordPage((page) => page - 1)}>← 上一页</button>
              <span>{busy === "vocabulary" ? "读取中…" : `${wordPage + 1} / ${Math.max(1, Math.ceil(wordTotal / WORD_PAGE_SIZE))}`}</span>
              <button disabled={(wordPage + 1) * WORD_PAGE_SIZE >= wordTotal} onClick={() => setWordPage((page) => page + 1)}>下一页 →</button>
            </div>
          </section>
        )}

        {view === "history" && (
          <section className="workspace-page">
            <div className="workspace-title">
              <div><span className="eyebrow">ANALYSIS · SQLITE</span><h1>分析记录</h1><p>{historyTotal} 条实际分析结果，按数据库时间倒序排列。</p></div>
            </div>
            <div className="timeline">
              {history.map((item) => (
                <div className="timeline-item" key={item.article_id}>
                  <span className="timeline-dot" />
                  <div className="timeline-time"><strong>{formatDate(item.created_at)}</strong><small>{new Date(item.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</small></div>
                  <div className="timeline-card">
                    <div><span>{item.mode}</span><small>{item.model || "local"}</small></div>
                    <h2>{item.title}</h2>
                    <p>{item.field} · 难度 <b>{item.difficulty.toFixed(1)}</b> · 阅读价值 <b>{item.exam_value.toFixed(1)}</b></p>
                    <button onClick={() => void openArticle(item.article_id)}>查看文章 →</button>
                  </div>
                </div>
              ))}
            </div>
            <div className="pagination">
              <button disabled={historyPage === 0} onClick={() => setHistoryPage((page) => page - 1)}>← 上一页</button>
              <span>{busy === "history" ? "读取中…" : `${historyPage + 1} / ${Math.max(1, Math.ceil(historyTotal / HISTORY_PAGE_SIZE))}`}</span>
              <button disabled={(historyPage + 1) * HISTORY_PAGE_SIZE >= historyTotal} onClick={() => setHistoryPage((page) => page + 1)}>下一页 →</button>
            </div>
          </section>
        )}
      </main>

      {tooltip && (
        <div className="dictionary-popover" style={{ left: Math.min(window.innerWidth - 290, Math.max(16, tooltip.x - 130)), top: tooltip.y }} onMouseEnter={keepPopoverOpen} onMouseLeave={scheduleClose}>
          <div className="dictionary-top"><strong>{tooltip.word}</strong><button aria-label="播放发音">◖))</button></div>
          <div className="phonetic">{tooltip.phonetic} <i>{tooltip.pos}</i></div>
          <p className={tooltip.loading ? "loading" : ""}>{tooltip.zh || "暂无中文释义"}</p>
          {tooltip.en && <small>{tooltip.en}</small>}
          <div className="popover-actions"><span>释义由 Python 本地词典链路返回</span><button onClick={() => void cycleLevel(tooltip.word)}>标记 ＋</button></div>
        </div>
      )}

      {settingsOpen && (
        <div className="modal-backdrop" onMouseDown={() => setSettingsOpen(false)}>
          <form className="modal" onSubmit={saveSettings} onMouseDown={(event) => event.stopPropagation()}>
            <button type="button" className="modal-close" onClick={() => setSettingsOpen(false)}>×</button>
            <span className="eyebrow">LOCAL MODEL CONFIG</span>
            <h2>模型与 API</h2>
            <p>设置由 Python 后端写入 `config/local.yaml`。网页不会读取或回显密钥。</p>
            <label>模型<input value={settings.model} onChange={(event) => setSettings({ ...settings, model: event.target.value })} /></label>
            <label>API Base URL<input value={settings.base_url} onChange={(event) => setSettings({ ...settings, base_url: event.target.value })} placeholder="https://api.openai.com/v1" /></label>
            <label>API Key<div className="key-input"><input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={settings.api_key_set ? "已配置；留空则保持不变" : "尚未配置"} /><span>{settings.api_key_set ? "已配置" : "未配置"}</span></div></label>
            <div className="modal-actions">
              <button type="button" onClick={() => void testConnection()} disabled={busy === "settings-test"}>{busy === "settings-test" ? "正在真实连接…" : "测试真实连接"}</button>
              <button type="submit" disabled={busy === "settings-save"}>{busy === "settings-save" ? "保存中…" : "写入本地配置"}</button>
            </div>
          </form>
        </div>
      )}

      {addOpen && (
        <div className="modal-backdrop" onMouseDown={() => setAddOpen(false)}>
          <form className="modal" onSubmit={addArticle} onMouseDown={(event) => event.stopPropagation()}>
            <button type="button" className="modal-close" onClick={() => setAddOpen(false)}>×</button>
            <span className="eyebrow">PYTHON CORPUS INGEST</span>
            <h2>加入一篇新文章</h2>
            <p>链接会交给 Python 正文提取器；粘贴正文则直接写入 SQLite 并运行分析。</p>
            <label>文章标题<input name="title" required placeholder="文章标题" /></label>
            <label>来源<input name="source" placeholder="The Guardian / local" /></label>
            <label>文章链接<input name="url" type="url" placeholder="https://…" /></label>
            <label>正文（与链接至少填写一项）<textarea name="text" rows={6} placeholder="粘贴有权保存和学习的正文…" /></label>
            <label className="check-label"><input name="use_llm" type="checkbox" /> 导入后使用本地配置的 LLM 深度分析</label>
            <div className="modal-actions"><button type="button" onClick={() => setAddOpen(false)}>取消</button><button type="submit" disabled={busy === "add"}>{busy === "add" ? "Python 正在导入…" : "导入语料库"}</button></div>
          </form>
        </div>
      )}

      {busy === "article" && <div className="loading-line" />}
      {toast && <div className={`toast ${toast.startsWith("!") ? "toast-error" : ""}`}><span>{toast.split("|")[0]}</span>{toast.split("|").slice(1).join("|")}</div>}
    </div>
  );
}

"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type View = "reader" | "library" | "vocabulary" | "history";
type Level = "learning" | "familiar" | "mastered";
type HighlightScope = "review" | "all";
type VocabularyTier = "high_school" | "core" | "key" | "gre" | "rare";
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
  tier?: VocabularyTier;
};
type VocabularyHighlight = {
  word: string;
  lemma: string;
  tier: "core" | "key" | "gre" | "specialized";
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
    status: "valid" | "invalid" | "local";
    rhetoric_count: number;
  };
  vocabulary: VocabularyItem[];
  vocabulary_highlights: VocabularyHighlight[];
  collocations: Array<{ expression: string; meaning: string; importance: number }>;
  polysemy: Array<{ word: string; contextual_meaning: string }>;
  sentence_patterns: Array<{ type: string; function: string; sentence: string }>;
  mastery_words: Array<{ lemma: string; level: Level }>;
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
type CrawlerOptions = {
  sources: Array<{ name: string; field: string; category: string; enabled: boolean }>;
  defaults: {
    limit: number;
    request_timeout_seconds: number;
    delay_seconds: number;
    min_text_chars: number;
    min_quality_score: number;
  };
};
type Tooltip = {
  word: string;
  x: number;
  y: number;
  placement: "above" | "below";
  phonetic: string;
  pos: string;
  zh: string;
  en: string;
  loading?: boolean;
};
type TaskNotice = {
  id: number;
  title: string;
  steps: string[];
  expectedSeconds: number;
  elapsedSeconds: number;
  progress: number;
  status: "running" | "success" | "error";
  result: string;
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

function formatElapsed(seconds: number) {
  if (seconds < 60) return `${seconds} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
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

function UiIcon({ name }: { name: "add" | "trash" | "settings" }) {
  return (
    <svg className="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {name === "add" && <><path d="M12 5v14" /><path d="M5 12h14" /></>}
      {name === "trash" && <><path d="M4 7h16" /><path d="M9 3h6l1 4H8l1-4Z" /><path d="m7 7 1 14h8l1-14" /><path d="M10 11v6M14 11v6" /></>}
      {name === "settings" && <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.86 2.86-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21H9.5v-.1A1.7 1.7 0 0 0 8.4 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.86-2.86.06-.06A1.7 1.7 0 0 0 4 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H2V9.5h.3A1.7 1.7 0 0 0 4 8.4a1.7 1.7 0 0 0-.34-1.88l-.06-.06L6.46 3.6l.06.06A1.7 1.7 0 0 0 8.4 4a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V2h4.1v.3A1.7 1.7 0 0 0 15 4a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.86 2.86-.06.06A1.7 1.7 0 0 0 19.4 8.4a1.7 1.7 0 0 0 .6 1 1.7 1.7 0 0 0 1.1.4h.3v4.1h-.3A1.7 1.7 0 0 0 19.4 15Z" /></>}
    </svg>
  );
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
  const [addMode, setAddMode] = useState<"manual" | "crawler">("manual");
  const [crawlerOptions, setCrawlerOptions] = useState<CrawlerOptions | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [dark, setDark] = useState(false);
  const [focus, setFocus] = useState(false);
  const [dictionary, setDictionary] = useState(true);
  const [highlightScope, setHighlightScope] = useState<HighlightScope>("review");
  const [highlightVisibility, setHighlightVisibility] = useState({
    core: true,
    key: true,
    gre: true,
    specialized: true,
  });
  const [preferencesReady, setPreferencesReady] = useState(false);
  const [markingWord, setMarkingWord] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);
  const [fontSize, setFontSize] = useState(19);
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState("");
  const [taskNotice, setTaskNotice] = useState<TaskNotice | null>(null);
  const [error, setError] = useState("");
  const hoverTimer = useRef<number | null>(null);
  const closeTimer = useRef<number | null>(null);
  const lookupRequest = useRef<AbortController | null>(null);
  const globalLookupTarget = useRef<{ node: Text; start: number; end: number } | null>(null);
  const readerRef = useRef<HTMLElement | null>(null);
  const displayedProgress = useRef(0);
  const activeTaskId = useRef(0);
  const taskDismissTimer = useRef<number | null>(null);

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
    for (const item of detail?.vocabulary_highlights || []) {
      map[item.word.toLowerCase()] = item.lemma.toLowerCase();
    }
    return map;
  }, [detail]);

  const activeVocabularyHighlights = useMemo(() => {
    const highlights = detail?.vocabulary_highlights || [];
    if (highlightScope === "all") return highlights;
    const reviewLemmas = new Set<string>();
    for (const item of detail?.vocabulary || []) {
      reviewLemmas.add(item.lemma.toLowerCase());
      reviewLemmas.add(item.word.toLowerCase());
    }
    return highlights.filter((item) =>
      reviewLemmas.has(item.lemma.toLowerCase()) || reviewLemmas.has(item.word.toLowerCase()));
  }, [detail, highlightScope]);

  const vocabularyTierMap = useMemo(() => {
    const map: Record<string, "core" | "key" | "gre" | "specialized"> = {};
    for (const item of activeVocabularyHighlights) {
      map[item.word.toLowerCase()] = item.tier;
      map[item.lemma.toLowerCase()] = item.tier;
    }
    return map;
  }, [activeVocabularyHighlights]);

  const vocabularyTierStats = useMemo(() => {
    const tiersByLemma = new Map<string, VocabularyHighlight["tier"]>();
    for (const item of activeVocabularyHighlights) {
      tiersByLemma.set(item.lemma.toLowerCase(), item.tier);
    }
    const values = Array.from(tiersByLemma.values());
    return {
      core: values.filter((tier) => tier === "core").length,
      key: values.filter((tier) => tier === "key").length,
      gre: values.filter((tier) => tier === "gre").length,
      specialized: values.filter((tier) => tier === "specialized").length,
    };
  }, [activeVocabularyHighlights]);

  async function loadInitial() {
    setBusy("initial");
    setError("");
    try {
      const [healthData, recentData, settingsData] = await Promise.all([
        request<Health>("/health"),
        request<{ items: ArticleSummary[]; total: number }>("/recent-articles?limit=12"),
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
      const initialProgress = Math.max(data.progress, 1);
      window.scrollTo({ top: 0, behavior: "auto" });
      displayedProgress.current = initialProgress;
      setDetail({ ...data, progress: initialProgress });
      setRecent((items) => [
        { ...data, progress: initialProgress, last_read_at: new Date().toISOString() },
        ...items.filter((item) => item.id !== data.id),
      ].slice(0, 12));
      const nextLevels: Record<string, Level> = {};
      for (const item of data.mastery_words) {
        nextLevels[item.lemma.toLowerCase()] = item.level;
      }
      setLevels(nextLevels);
      void request(`/articles/${encodeURIComponent(id)}/progress`, {
        method: "PUT",
        body: JSON.stringify({ progress: initialProgress }),
      });
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "文章加载失败", true);
    } finally {
      setBusy("");
    }
  }

  async function clearRecent() {
    if (!recent.length) return;
    try {
      const result = await request<{ deleted: number }>("/reading-progress", { method: "DELETE" });
      setRecent([]);
      showToast(`已清除 ${result.deleted} 条最近阅读记录`);
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "最近记录清除失败", true);
    }
  }

  async function showAddDialog() {
    setAddOpen(true);
    if (crawlerOptions) return;
    try {
      setCrawlerOptions(await request<CrawlerOptions>("/crawler/options"));
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "爬虫参数加载失败", true);
    }
  }

  function showToast(message: string, failed = false) {
    setToast(`${failed ? "!" : "✓"}|${message}`);
    window.setTimeout(() => setToast(""), 3200);
  }

  function startTask(
    title: string,
    steps: string[],
    expectedSeconds: number,
  ) {
    if (taskDismissTimer.current) window.clearTimeout(taskDismissTimer.current);
    const id = activeTaskId.current + 1;
    activeTaskId.current = id;
    setToast("");
    setTaskNotice({
      id,
      title,
      steps,
      expectedSeconds,
      elapsedSeconds: 0,
      progress: 4,
      status: "running",
      result: "",
    });
  }

  function finishTask(result: string, failed = false) {
    const id = activeTaskId.current;
    setTaskNotice((current) => current?.id === id ? {
      ...current,
      progress: failed ? current.progress : 100,
      status: failed ? "error" : "success",
      result,
    } : current);
    taskDismissTimer.current = window.setTimeout(() => {
      setTaskNotice((current) => current?.id === id ? null : current);
    }, failed ? 8000 : 5200);
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

  function scheduleLookup(raw: string, rect: DOMRect, delay = 500) {
    if (!dictionary) return;
    clearPendingLookup();
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
    setTooltip(null);
    hoverTimer.current = window.setTimeout(() => void lookup(raw, rect), delay);
  }

  function wordAtPoint(x: number, y: number) {
    const element = document.elementFromPoint(x, y);
    if (!element || element.closest("input, textarea, select, option, code, kbd, [data-dictionary-ignore], .dictionary-popover")) {
      return null;
    }
    const lookupDocument = document as Document & {
      caretPositionFromPoint?: (clientX: number, clientY: number) => { offsetNode: Node; offset: number } | null;
      caretRangeFromPoint?: (clientX: number, clientY: number) => Range | null;
    };
    const caretPosition = lookupDocument.caretPositionFromPoint?.(x, y);
    const caretRange = caretPosition ? null : lookupDocument.caretRangeFromPoint?.(x, y);
    const node = caretPosition?.offsetNode || caretRange?.startContainer || null;
    let offset = caretPosition?.offset ?? caretRange?.startOffset ?? 0;
    if (!node || node.nodeType !== 3) return null;
    const textNode = node as Text;
    const text = textNode.data;
    if (offset >= text.length || !/[A-Za-z'’‘-]/.test(text[offset] || "")) offset -= 1;
    if (offset < 0 || !/[A-Za-z]/.test(text[offset] || "")) return null;
    let start = offset;
    let end = offset + 1;
    while (start > 0 && /[A-Za-z'’‘-]/.test(text[start - 1])) start -= 1;
    while (end < text.length && /[A-Za-z'’‘-]/.test(text[end])) end += 1;
    const word = text.slice(start, end).replace(/[’‘]/g, "'");
    if (!/^[A-Za-z][A-Za-z'-]+$/.test(word)) return null;
    const range = document.createRange();
    range.setStart(textNode, start);
    range.setEnd(textNode, end);
    const rect = range.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    return { word, rect, node: textNode, start, end };
  }

  function handleGlobalLookupMove(event: React.MouseEvent<HTMLDivElement>) {
    if (!dictionary) return;
    const target = wordAtPoint(event.clientX, event.clientY);
    if (!target) {
      if (globalLookupTarget.current) {
        globalLookupTarget.current = null;
        scheduleClose();
      }
      return;
    }
    const current = globalLookupTarget.current;
    if (current?.node === target.node && current.start === target.start && current.end === target.end) return;
    globalLookupTarget.current = { node: target.node, start: target.start, end: target.end };
    scheduleLookup(target.word, target.rect);
  }

  async function lookup(raw: string, rect: DOMRect) {
    const word = raw.toLowerCase().replace(/[^a-z'-]/g, "");
    if (word.length < 2) return;
    const placement = window.innerHeight - rect.bottom < 280 && rect.top > 280 ? "above" : "below";
    const anchor = {
      x: rect.left + rect.width / 2,
      y: placement === "above" ? rect.top - 10 : rect.bottom + 10,
      placement,
    } as const;
    setTooltip({
      word, ...anchor,
      phonetic: "", pos: "", zh: "正在查询本地词典…", en: "", loading: true,
    });
    const controller = new AbortController();
    lookupRequest.current = controller;
    try {
      const data = await request<{ word: string; phonetic: string; pos: string; zh: string; en: string }>(
        `/dictionary/${encodeURIComponent(word)}`,
        { signal: controller.signal },
      );
      setTooltip({ ...data, ...anchor });
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setTooltip({
        word, ...anchor, phonetic: "", pos: "",
        zh: "暂未查到释义", en: reason instanceof Error ? reason.message : "",
      });
    }
  }

  function openWordMark(raw: string) {
    const lemma = (lemmaMap[raw.toLowerCase()] || raw).toLowerCase();
    clearPendingLookup();
    setTooltip(null);
    setMarkingWord(lemma);
  }

  async function applyWordMark(next: Level | null) {
    if (!markingWord) return;
    const lemma = markingWord;
    setLevels((current) => {
      const copy = { ...current };
      if (next) copy[lemma] = next;
      else delete copy[lemma];
      return copy;
    });
    setWords((items) => items.map((item) => item.lemma === lemma ? { ...item, mastery: next || null } : item));
    setMarkingWord(null);
    setTooltip(null);
    try {
      await request(`/vocabulary/${encodeURIComponent(lemma)}/mastery`, {
        method: "PUT",
        body: JSON.stringify({
          level: next,
          article_id: detail?.id || "",
          word: lemma,
        }),
      });
      if (next) showToast(`${lemma} 已加入词汇簿`);
    } catch (reason) {
      showToast(reason instanceof Error ? reason.message : "掌握度保存失败", true);
    }
  }

  function renderParagraph(text: string) {
    return text.split(/(\b[A-Za-z][A-Za-z'’‘-]*\b)/g).map((part, index) => {
      if (!/^[A-Za-z]/.test(part)) return part;
      const raw = part.toLowerCase().replace(/[’‘]/g, "'");
      const lemma = lemmaMap[raw] || raw;
      const tier = vocabularyTierMap[lemma];
      return (
        <span
          key={`${raw}-${index}`}
          className={`word ${tier ? `candidate tier-${tier}` : ""} ${levels[lemma] ? `level-${levels[lemma]}` : ""}`}
          onFocus={(event) => scheduleLookup(part, event.currentTarget.getBoundingClientRect(), 0)}
          onBlur={scheduleClose}
          onClick={() => openWordMark(lemma)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") openWordMark(lemma);
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
    startTask(
      "文章重新分析",
      ["整理正文与提示词", "等待 LLM 推理", "解析修辞与词汇结果", "写入本地数据库"],
      90,
    );
    try {
      const data = await request<ArticleDetail>(
        `/articles/${encodeURIComponent(detail.id)}/analyze?use_llm=true`,
        { method: "POST" },
      );
      setDetail(data);
      finishTask("Python NLP + LLM 分析已完成并写入数据库");
      void loadHistory();
    } catch (reason) {
      finishTask(reason instanceof Error ? reason.message : "分析失败", true);
    } finally {
      setBusy("");
    }
  }

  async function addArticle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const useLlm = form.get("use_llm") === "on";
    const hasText = Boolean(String(form.get("text") || "").trim());
    setBusy("add");
    startTask(
      "添加文章",
      [
        hasText ? "整理手动输入的正文" : "获取并抽取网页正文",
        "运行本地 NLP 分析",
        ...(useLlm ? ["等待 LLM 深度分析"] : []),
        "写入本地语料库",
      ],
      useLlm ? 85 : 12,
    );
    try {
      const data = await request<ArticleDetail>("/articles", {
        method: "POST",
        body: JSON.stringify({
          title: String(form.get("title") || ""),
          source: String(form.get("source") || "manual"),
          url: String(form.get("url") || ""),
          text: String(form.get("text") || ""),
          use_llm: useLlm,
        }),
      });
      setAddOpen(false);
      displayedProgress.current = data.progress;
      setRecent((items) => [data, ...items.filter((item) => item.id !== data.id)].slice(0, 12));
      setHealth((current) => current ? {
        ...current,
        counts: { ...current.counts, articles: current.counts.articles + 1, analyses: current.counts.analyses + 1 },
      } : current);
      setDetail(data);
      setView("reader");
      finishTask("文章已由 Python 语料链路导入并分析");
    } catch (reason) {
      finishTask(reason instanceof Error ? reason.message : "文章导入失败", true);
    } finally {
      setBusy("");
    }
  }

  async function crawlArticles(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const limit = Number(form.get("limit") || 3);
    const useLlm = form.get("crawler_use_llm") === "on";
    setBusy("crawl");
    startTask(
      "扩充语料库",
      [
        "检索来源与候选文章",
        "抽取并筛选正文",
        "逐篇运行本地 NLP",
        ...(useLlm ? ["逐篇等待 LLM 深度分析"] : []),
        "写入本地语料库",
      ],
      Math.max(18, limit * (useLlm ? 75 : 8)),
    );
    try {
      const result = await request<{
        imported: number;
        analyzed: number;
        errors: string[];
      }>("/crawler/fetch", {
        method: "POST",
        body: JSON.stringify({
          source: String(form.get("crawler_source") || ""),
          limit,
          topic_query: String(form.get("topic_query") || ""),
          request_timeout_seconds: Number(form.get("request_timeout_seconds") || 20),
          delay_seconds: Number(form.get("delay_seconds") || 1),
          min_text_chars: Number(form.get("min_text_chars") || 800),
          min_quality_score: Number(form.get("min_quality_score") || 6),
          use_llm: useLlm,
        }),
      });
      setAddOpen(false);
      setHealth(await request<Health>("/health"));
      if (view === "library") void loadArticles();
      const suffix = result.errors.length ? `；${result.errors.length} 篇 LLM 分析失败，已保留 NLP 结果` : "";
      finishTask(result.imported
        ? `自动抓取并分析了 ${result.analyzed} 篇文章${suffix}`
        : "没有发现符合条件的新文章");
    } catch (reason) {
      finishTask(reason instanceof Error ? reason.message : "自动抓取失败", true);
    } finally {
      setBusy("");
    }
  }

  const runningTaskId = taskNotice?.status === "running" ? taskNotice.id : null;

  useEffect(() => {
    if (!runningTaskId) return;
    const timer = window.setInterval(() => {
      setTaskNotice((current) => {
        if (!current || current.id !== runningTaskId || current.status !== "running") return current;
        const elapsedSeconds = current.elapsedSeconds + 1;
        const ratio = elapsedSeconds / current.expectedSeconds;
        const progress = Math.min(94, Math.round(4 + 90 * (1 - Math.exp(-ratio * 1.7))));
        return { ...current, elapsedSeconds, progress };
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [runningTaskId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadInitial();
    // Initial corpus connection should run once when the reading desk mounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const storedTheme = window.localStorage.getItem("grecis-theme");
      const preferredDark = storedTheme === "dark"
        || (!storedTheme && window.matchMedia("(prefers-color-scheme: dark)").matches);
      setDark(preferredDark);
      setHighlightScope(
        window.localStorage.getItem("grecis-highlight-scope") === "all" ? "all" : "review",
      );
      setHighlightVisibility({
        core: window.localStorage.getItem("grecis-highlight-core") !== "off",
        key: window.localStorage.getItem("grecis-highlight-key") !== "off",
        gre: window.localStorage.getItem("grecis-highlight-gre") !== "off",
        specialized: window.localStorage.getItem("grecis-highlight-specialized") !== "off",
      });
      setPreferencesReady(true);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!preferencesReady) return;
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("grecis-theme", dark ? "dark" : "light");
  }, [dark, preferencesReady]);

  useEffect(() => {
    if (!preferencesReady) return;
    localStorage.setItem("grecis-highlight-scope", highlightScope);
  }, [highlightScope, preferencesReady]);

  useEffect(() => {
    if (!preferencesReady) return;
    localStorage.setItem("grecis-highlight-core", highlightVisibility.core ? "on" : "off");
    localStorage.setItem("grecis-highlight-key", highlightVisibility.key ? "on" : "off");
    localStorage.setItem("grecis-highlight-gre", highlightVisibility.gre ? "on" : "off");
    localStorage.setItem("grecis-highlight-specialized", highlightVisibility.specialized ? "on" : "off");
  }, [highlightVisibility, preferencesReady]);

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

  useEffect(() => {
    if (view !== "reader" || !detail?.id) return;

    const articleId = detail.id;
    let saveTimer: number | null = null;
    let dirty = false;

    const persistProgress = () => {
      if (!dirty) return;
      dirty = false;
      void request(`/articles/${encodeURIComponent(articleId)}/progress`, {
        method: "PUT",
        body: JSON.stringify({ progress: displayedProgress.current }),
      });
    };

    const updateProgress = () => {
      const reader = readerRef.current;
      if (!reader) return;
      const rect = reader.getBoundingClientRect();
      const articleTop = window.scrollY + rect.top;
      const articleHeight = Math.max(reader.offsetHeight, 1);
      const readingLine = window.scrollY + window.innerHeight * 0.8;
      const calculated = Math.min(100, Math.max(1, Math.round(
        ((readingLine - articleTop) / articleHeight) * 100,
      )));
      const next = Math.max(displayedProgress.current, calculated);
      if (next === displayedProgress.current) return;

      displayedProgress.current = next;
      dirty = true;
      setDetail((current) => current?.id === articleId ? { ...current, progress: next } : current);
      setRecent((items) => items.map((item) => item.id === articleId
        ? { ...item, progress: next, last_read_at: new Date().toISOString() }
        : item));
      if (saveTimer) window.clearTimeout(saveTimer);
      saveTimer = window.setTimeout(persistProgress, 650);
    };

    window.addEventListener("scroll", updateProgress, { passive: true });
    window.addEventListener("resize", updateProgress);
    const initialFrame = window.requestAnimationFrame(updateProgress);
    return () => {
      window.cancelAnimationFrame(initialFrame);
      window.removeEventListener("scroll", updateProgress);
      window.removeEventListener("resize", updateProgress);
      if (saveTimer) window.clearTimeout(saveTimer);
      persistProgress();
    };
  }, [detail?.id, view]);

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
    <div
      className={`app-shell ${focus ? "focus-mode" : ""}`}
      onMouseMove={handleGlobalLookupMove}
      onMouseLeave={() => {
        globalLookupTarget.current = null;
        scheduleClose();
      }}
    >
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

        <div className="library-heading">
          <span>最近篇目</span>
          <div className="library-actions">
            <button onClick={() => void clearRecent()} aria-label="清空最近篇目" title="清空最近篇目" disabled={!recent.length}><UiIcon name="trash" /></button>
            <button onClick={() => void showAddDialog()} aria-label="增加文章" title="增加文章"><UiIcon name="add" /></button>
          </div>
        </div>
        <div className="article-list">
          {recent.map((article) => (
            <button key={article.id} className={`article-item ${detail?.id === article.id && view === "reader" ? "active" : ""}`} onClick={() => void openArticle(article.id)}>
              <span className="article-topic">{article.field}</span>
              <strong>{article.title}</strong>
              <span>{article.source} · {readingMinutes(article.word_count)} 分钟</span>
              <i><b style={{ width: `${article.progress}%` }} /></i>
            </button>
          ))}
          {!recent.length && <p className="recent-empty">尚无最近阅读记录<br />请从语料库选择一篇文章</p>}
        </div>

        <button className="settings-entry" onClick={() => setSettingsOpen(true)}>
          <UiIcon name="settings" /><span>模型与 API</span><small>{settings.model || "加载中"}</small>
        </button>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="breadcrumbs"><span>{view === "reader" ? detail?.analysis.field || "语料" : "GRECIS"}</span><b>/</b><span>{viewLabels[view]}</span></div>
          <div className="top-actions">
            <button className={`text-button ${dictionary ? "is-on" : ""}`} onClick={() => { setDictionary(!dictionary); clearPendingLookup(); setTooltip(null); }}><i />全页查词 · 0.5s</button>
            <button className="circle-button" onClick={() => setFocus(!focus)} aria-label="切换专注模式">{focus ? "↙" : "↗"}</button>
            <button className="circle-button" onClick={() => setDark(!dark)} aria-label="切换深色模式">{dark ? "☀" : "◐"}</button>
          </div>
        </header>

        {view === "reader" && detail && (
          <div
            className={`reading-layout ${highlightVisibility.core ? "" : "hide-core-highlight"} ${highlightVisibility.key ? "" : "hide-key-highlight"} ${highlightVisibility.gre ? "" : "hide-gre-highlight"} ${highlightVisibility.specialized ? "" : "hide-specialized-highlight"}`}
            key={detail.id}
          >
            <article className="reader" ref={readerRef}>
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
                  <button
                    className={highlightVisibility.core ? "" : "is-off"}
                    title={`${highlightVisibility.core ? "关闭" : "开启"}核心词高亮`}
                    aria-pressed={highlightVisibility.core}
                    onClick={() => setHighlightVisibility((current) => ({ ...current, core: !current.core }))}
                  ><i className="dot core" />考研核心 <b>{vocabularyTierStats.core}</b></button>
                  <button
                    className={highlightVisibility.key ? "" : "is-off"}
                    title={`${highlightVisibility.key ? "关闭" : "开启"}重点词高亮`}
                    aria-pressed={highlightVisibility.key}
                    onClick={() => setHighlightVisibility((current) => ({ ...current, key: !current.key }))}
                  ><i className="dot key" />常用进阶 <b>{vocabularyTierStats.key}</b></button>
                  <button
                    className={highlightVisibility.gre ? "" : "is-off"}
                    title={`${highlightVisibility.gre ? "关闭" : "开启"} GRE 拓展词高亮`}
                    aria-pressed={highlightVisibility.gre}
                    onClick={() => setHighlightVisibility((current) => ({ ...current, gre: !current.gre }))}
                  ><i className="dot gre" />GRE 拓展 <b>{vocabularyTierStats.gre}</b></button>
                  <button
                    className={highlightVisibility.specialized ? "" : "is-off"}
                    title={`${highlightVisibility.specialized ? "关闭" : "开启"}专业与熟词生义高亮`}
                    aria-pressed={highlightVisibility.specialized}
                    onClick={() => setHighlightVisibility((current) => ({ ...current, specialized: !current.specialized }))}
                  ><i className="dot specialized" />专业／生义 <b>{vocabularyTierStats.specialized}</b></button>
                </div>
                <div className="reader-tools">
                  <div className="highlight-scope" aria-label="荧光标记范围">
                    <button className={highlightScope === "review" ? "active" : ""} aria-pressed={highlightScope === "review"} onClick={() => setHighlightScope("review")}>重点词</button>
                    <button className={highlightScope === "all" ? "active" : ""} aria-pressed={highlightScope === "all"} onClick={() => setHighlightScope("all")}>全文词库</button>
                  </div>
                  <div className="font-control">
                    <button onClick={() => setFontSize(Math.max(16, fontSize - 1))}>A−</button><span>{fontSize}</span>
                    <button onClick={() => setFontSize(Math.min(24, fontSize + 1))}>A＋</button>
                  </div>
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
                <div className="card-heading"><span>本篇洞察</span><small>{
                  detail.digest.status === "valid" ? "LLM" : detail.digest.status === "invalid" ? "LLM 异常" : "NLP"
                }</small></div>
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
              <details className="language-notes" open>
                <summary>
                  <span>精读语言点</span>
                  <small>
                    <b>{detail.collocations.length}</b> 搭配 · <b>{detail.polysemy.length}</b> 生义 · <b>{detail.sentence_patterns.length}</b> 句式
                  </small>
                </summary>
                <div className="language-note-groups">
                  <details open>
                    <summary><span>搭配</span><b>{detail.collocations.length}</b></summary>
                    <ol>
                      {detail.collocations.map((item, index) => (
                        <li key={`${item.expression}-${index}`}>
                          <strong>{item.expression}</strong>
                          {item.meaning && <p>{item.meaning}</p>}
                        </li>
                      ))}
                    </ol>
                    {!detail.collocations.length && <p className="language-note-empty">本篇暂无搭配记录</p>}
                  </details>
                  <details open>
                    <summary><span>熟词生义</span><b>{detail.polysemy.length}</b></summary>
                    <ol>
                      {detail.polysemy.map((item, index) => (
                        <li key={`${item.word}-${index}`}>
                          <strong>{item.word}</strong>
                          <p>{item.contextual_meaning}</p>
                        </li>
                      ))}
                    </ol>
                    {!detail.polysemy.length && <p className="language-note-empty">本篇暂无熟词生义记录</p>}
                  </details>
                  <details open>
                    <summary><span>句式</span><b>{detail.sentence_patterns.length}</b></summary>
                    <ol>
                      {detail.sentence_patterns.map((item, index) => (
                        <li key={`${item.type}-${index}`}>
                          <strong>{item.type}</strong>
                          {item.function && <p>{item.function}</p>}
                          <blockquote>{item.sentence}</blockquote>
                        </li>
                      ))}
                    </ol>
                    {!detail.sentence_patterns.length && <p className="language-note-empty">本篇暂无句式记录</p>}
                  </details>
                </div>
              </details>
            </aside>
          </div>
        )}

        {view === "reader" && !detail && <div className="page-loading">正在从本地语料库读取文章…</div>}

        {view === "library" && (
          <section className="workspace-page">
            <div className="workspace-title">
              <div><span className="eyebrow">CORPUS · SQLITE</span><h1>语料库</h1><p>全部内容动态读取自 data/grecis.sqlite。</p></div>
              <button className="solid-action" onClick={() => void showAddDialog()}>＋ 加入文章</button>
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
                <button className="word-card" key={item.lemma} onClick={() => openWordMark(item.lemma)}>
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
        <div
          className={`dictionary-popover ${tooltip.placement === "above" ? "popover-above" : ""}`}
          style={{
            left: Math.min(window.innerWidth - 290, Math.max(16, tooltip.x - 130)),
            ...(tooltip.placement === "above"
              ? { bottom: Math.max(16, window.innerHeight - tooltip.y) }
              : { top: tooltip.y }),
          }}
          onMouseEnter={keepPopoverOpen}
          onMouseLeave={scheduleClose}
        >
          <div className="dictionary-top"><strong>{tooltip.word}</strong><button aria-label="播放发音">◖))</button></div>
          <div className="phonetic">{tooltip.phonetic} <i>{tooltip.pos}</i></div>
          <p className={tooltip.loading ? "loading" : ""}>{tooltip.zh || "暂无中文释义"}</p>
          {tooltip.en && <small>{tooltip.en}</small>}
          <div className="popover-actions"><span>释义由 Python 本地词典链路返回</span><button onClick={() => openWordMark(tooltip.word)}>标记 ＋</button></div>
        </div>
      )}

      {markingWord && (
        <div className="modal-backdrop" onMouseDown={() => setMarkingWord(null)}>
          <div className="modal word-mark-modal" role="dialog" aria-modal="true" aria-labelledby="word-mark-title" onMouseDown={(event) => event.stopPropagation()}>
            <button type="button" className="modal-close" onClick={() => setMarkingWord(null)}>×</button>
            <span className="eyebrow">PERSONAL VOCABULARY MARK</span>
            <h2 id="word-mark-title">{markingWord}</h2>
            <p>选择掌握程度与下划线颜色。标记后会加入词汇簿，并在其他文章中沿用。</p>
            <div className="underline-options">
              <button type="button" className={`learning ${levels[markingWord] === "learning" ? "selected" : ""}`} onClick={() => void applyWordMark("learning")}><i />待掌握<span>玫瑰红下划线</span></button>
              <button type="button" className={`familiar ${levels[markingWord] === "familiar" ? "selected" : ""}`} onClick={() => void applyWordMark("familiar")}><i />似曾相识<span>琥珀色下划线</span></button>
              <button type="button" className={`mastered ${levels[markingWord] === "mastered" ? "selected" : ""}`} onClick={() => void applyWordMark("mastered")}><i />已掌握<span>墨绿色下划线</span></button>
            </div>
            <button type="button" className="remove-underline" onClick={() => void applyWordMark(null)}>取消下划线并移出个人词汇标记</button>
          </div>
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
          <form
            className="modal ingest-modal"
            onSubmit={addMode === "manual" ? addArticle : crawlArticles}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <button type="button" className="modal-close" onClick={() => setAddOpen(false)}>×</button>
            <span className="eyebrow">PYTHON CORPUS INGEST</span>
            <h2>扩充阅读语料</h2>
            <div className="ingest-tabs" role="tablist" aria-label="文章导入方式">
              <button type="button" role="tab" aria-selected={addMode === "manual"} className={addMode === "manual" ? "active" : ""} onClick={() => setAddMode("manual")}>手动导入</button>
              <button type="button" role="tab" aria-selected={addMode === "crawler"} className={addMode === "crawler" ? "active" : ""} onClick={() => setAddMode("crawler")}>自动抓取</button>
            </div>

            {addMode === "manual" ? (
              <>
                <p className="ingest-description">链接会交给 Python 正文提取器；粘贴正文则直接写入 SQLite 并运行分析。</p>
                <label>文章标题<input name="title" required placeholder="文章标题" /></label>
                <label>来源<input name="source" placeholder="The Guardian / local" /></label>
                <label>文章链接<input name="url" type="url" placeholder="https://…" /></label>
                <label>正文（与链接至少填写一项）<textarea name="text" rows={6} placeholder="粘贴有权保存和学习的正文…" /></label>
                <label className="check-label"><input name="use_llm" type="checkbox" /> 导入后使用本地配置的 LLM 深度分析</label>
              </>
            ) : (
              <>
                <p className="ingest-description">由 Python 从来源配置的 RSS、栏目页与搜索页发现正文，质量筛选后写入 SQLite。</p>
                {!crawlerOptions ? <div className="crawler-loading">正在读取 Python 来源配置…</div> : (
                  <>
                    <label>文章来源
                      <select name="crawler_source" required defaultValue={crawlerOptions.sources[0]?.name || ""}>
                        <option value="all">全部已启用来源（数量按每个来源计算）</option>
                        {crawlerOptions.sources.map((source) => (
                          <option key={source.name} value={source.name}>{source.name} · {source.field}</option>
                        ))}
                      </select>
                    </label>
                    <label>检索主题（可选）<input name="topic_query" placeholder="climate policy / education reform" /></label>
                    <div className="parameter-grid">
                      <label>每个来源篇数<input name="limit" type="number" min="1" max="20" defaultValue={crawlerOptions.defaults.limit} /></label>
                      <label>请求超时（秒）<input name="request_timeout_seconds" type="number" min="5" max="120" defaultValue={crawlerOptions.defaults.request_timeout_seconds} /></label>
                      <label>请求间隔（秒）<input name="delay_seconds" type="number" min="0" max="10" step="0.1" defaultValue={crawlerOptions.defaults.delay_seconds} /></label>
                      <label>正文最少字符<input name="min_text_chars" type="number" min="200" max="20000" step="100" defaultValue={crawlerOptions.defaults.min_text_chars} /></label>
                      <label>最低质量分<input name="min_quality_score" type="number" min="0" max="10" step="0.1" defaultValue={crawlerOptions.defaults.min_quality_score} /></label>
                    </div>
                    <label className="check-label"><input name="crawler_use_llm" type="checkbox" /> 抓取后同时进行 LLM 深度分析（始终运行本地 NLP）</label>
                  </>
                )}
              </>
            )}

            <div className="modal-actions">
              <button type="button" onClick={() => setAddOpen(false)}>取消</button>
              <button type="submit" disabled={busy === "add" || busy === "crawl" || (addMode === "crawler" && !crawlerOptions)}>
                {busy === "add" ? "Python 正在导入…" : busy === "crawl" ? "Python 正在抓取…" : addMode === "manual" ? "导入语料库" : "开始自动抓取"}
              </button>
            </div>
          </form>
        </div>
      )}

      {busy === "article" && <div className="loading-line" />}
      {taskNotice && (() => {
        const stepIndex = Math.min(
          taskNotice.steps.length - 1,
          Math.floor((taskNotice.progress / 96) * taskNotice.steps.length),
        );
        const running = taskNotice.status === "running";
        return (
          <aside
            className={`task-notice task-${taskNotice.status}`}
            role={taskNotice.status === "error" ? "alert" : "status"}
            aria-live="polite"
          >
            <div className="task-notice-top">
              <span className="task-state"><i />{
                running ? "任务进行中" : taskNotice.status === "success" ? "任务已完成" : "任务未完成"
              }</span>
              {!running && <button type="button" aria-label="关闭任务提示" onClick={() => setTaskNotice(null)}>×</button>}
            </div>
            <strong>{taskNotice.title}</strong>
            <p>{running ? taskNotice.steps[stepIndex] : taskNotice.result}</p>
            {running && stepIndex + 1 < taskNotice.steps.length && (
              <small>下一步 · {taskNotice.steps[stepIndex + 1]}</small>
            )}
            <div
              className="task-progress"
              role="progressbar"
              aria-label={`${taskNotice.title}估算进度`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={taskNotice.progress}
            ><i style={{ width: `${taskNotice.progress}%` }} /></div>
            <div className="task-meta">
              <span>{running ? `估算 ${taskNotice.progress}%` : taskNotice.status === "success" ? "100%" : "已停止"}</span>
              <span>已用 {formatElapsed(taskNotice.elapsedSeconds)}</span>
            </div>
            {running && (
              <div className="task-steps" aria-hidden="true">
                {taskNotice.steps.map((step, index) => <i key={step} className={index <= stepIndex ? "active" : ""} />)}
              </div>
            )}
          </aside>
        );
      })()}
      {toast && <div className={`toast ${toast.startsWith("!") ? "toast-error" : ""} ${taskNotice ? "toast-raised" : ""}`}><span>{toast.split("|")[0]}</span>{toast.split("|").slice(1).join("|")}</div>}
    </div>
  );
}

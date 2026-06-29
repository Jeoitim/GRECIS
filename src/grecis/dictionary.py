from __future__ import annotations

import json
import os
import re
import socket
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

# Set global socket timeout to 1.0s to prevent any DNS or connection hangs
socket.setdefaulttimeout(1.0)


def safe_print(msg: str, end: str = "\n", flush: bool = True) -> None:
    try:
        print(msg, end=end, flush=flush)
    except UnicodeEncodeError:
        try:
            import sys

            encoding = sys.stdout.encoding or "utf-8"
            encoded_bytes = (msg + end).encode(encoding, errors="backslashreplace")
            sys.stdout.buffer.write(encoded_bytes)
            if flush:
                sys.stdout.flush()
        except Exception:
            try:
                ascii_msg = msg.encode("ascii", errors="backslashreplace").decode("ascii")
                print(ascii_msg, end=end, flush=flush)
            except Exception:
                pass


CACHE_FILE = Path("data/dict_cache.json")
EMPTY_ENTRY = {"phonetic": "", "zh": "", "en": "", "pos": ""}
NEGATIVE_CACHE_POLICY = "phrase_llm_v1"
_LLM_EMPTY_RESPONSE_WARNED = False

# In-memory global cache to avoid repetitive disk read/write operations
_CACHE_IN_MEMORY: dict[str, Any] | None = None

# Circuit breaker to disable network queries if they fail repeatedly (e.g., when offline or blocked)
_CONSECUTIVE_FAILURES = 0
_CIRCUIT_BROKEN = False


def load_cache() -> dict[str, Any]:
    global _CACHE_IN_MEMORY
    if _CACHE_IN_MEMORY is not None:
        return _CACHE_IN_MEMORY

    if not CACHE_FILE.exists():
        _CACHE_IN_MEMORY = {}
        return _CACHE_IN_MEMORY

    try:
        _CACHE_IN_MEMORY = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        _CACHE_IN_MEMORY = {}
    return _CACHE_IN_MEMORY


def save_cache(cache: dict[str, Any]) -> None:
    global _CACHE_IN_MEMORY
    _CACHE_IN_MEMORY = cache
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def empty_entry(**extra: Any) -> dict[str, Any]:
    data = dict(EMPTY_ENTRY)
    data.update(extra)
    return data


def is_negative_cache_entry(value: Any, word_key: str = "") -> bool:
    if not isinstance(value, dict) or not value.get("_not_found"):
        return False
    if is_phrase_like(word_key):
        return value.get("_not_found_policy") == NEGATIVE_CACHE_POLICY
    return True


def is_stale_negative_cache_entry(value: Any, word_key: str = "") -> bool:
    return (
        isinstance(value, dict)
        and bool(value.get("_not_found"))
        and not is_negative_cache_entry(value, word_key)
    )


def is_phrase_like(word_key: str) -> bool:
    return " " in word_key or "-" in word_key or "'" in word_key


def should_query_remote_dictionary(word_key: str) -> bool:
    if is_phrase_like(word_key):
        return False
    if not re.fullmatch(r"[a-z]{3,24}", word_key):
        return False
    return True


def should_use_llm_fallback(word_key: str) -> bool:
    if is_phrase_like(word_key):
        return 2 <= len(re.findall(r"[a-z]+", word_key)) <= 6
    return os.getenv("GRECIS_DICT_LLM_FALLBACK", "").lower() in {
        "1",
        "true",
        "yes",
    } and should_query_remote_dictionary(word_key)


def normalize_openai_base_url(base_url: str) -> str:
    value = (base_url or "").strip()
    for suffix in ("/chat/completions", "/completions"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    if "11434" in value and not value.endswith("/v1") and not value.endswith("/v1/"):
        value = value.rstrip("/") + "/v1"
    return value.rstrip("/")


def fetch_from_youdao(word: str) -> str:
    """Fetch basic Chinese translation from Youdao Suggest API with tight timeout."""
    global _CONSECUTIVE_FAILURES, _CIRCUIT_BROKEN
    if _CIRCUIT_BROKEN:
        return ""

    url = f"https://dict.youdao.com/suggest?q={urllib.parse.quote(word)}&num=1&doctype=json"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=1.0) as response:
            data = json.loads(response.read().decode("utf-8"))
            entries = data.get("data", {}).get("entries", [])
            if entries:
                _CONSECUTIVE_FAILURES = 0  # Reset on success
                return str(entries[0].get("explain", "")).strip()
    except Exception:
        pass

    _CONSECUTIVE_FAILURES += 1
    if _CONSECUTIVE_FAILURES >= 3:
        _CIRCUIT_BROKEN = True
        print(
            "[WARNING] Dictionary queries failed repeatedly. Entering offline circuit-breaker mode."
        )
    return ""


def fetch_from_dictionary_api(word: str) -> dict[str, str]:
    """Fetch phonetic symbol and English definition from DictionaryAPI.dev with tight timeout."""
    global _CONSECUTIVE_FAILURES, _CIRCUIT_BROKEN
    if _CIRCUIT_BROKEN:
        return {"phonetic": "", "definition": ""}

    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    result = {"phonetic": "", "definition": ""}
    try:
        with urllib.request.urlopen(req, timeout=1.0) as response:
            data = json.loads(response.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 0:
                entry = data[0]
                result["phonetic"] = entry.get("phonetic") or ""
                if not result["phonetic"] and entry.get("phonetics"):
                    for p in entry["phonetics"]:
                        if p.get("text"):
                            result["phonetic"] = p["text"]
                            break

                meanings = entry.get("meanings", [])
                if meanings:
                    definitions = meanings[0].get("definitions", [])
                    if definitions:
                        result["definition"] = definitions[0].get("definition", "")
                _CONSECUTIVE_FAILURES = 0  # Reset on success
                return result
    except Exception:
        pass

    _CONSECUTIVE_FAILURES += 1
    if _CONSECUTIVE_FAILURES >= 3:
        _CIRCUIT_BROKEN = True
        print(
            "[WARNING] Dictionary queries failed repeatedly. Entering offline circuit-breaker mode."
        )
    return result


def get_oxford_path() -> str:
    try:
        from .config import load_config

        config = load_config()
        return config.mdict.oxford_path
    except Exception:
        return (
            r"C:\baidunetdiskdownload\mdict\牛津高阶（第10版 英汉双解）V5.0（含机翻）"
            r"\牛津高阶（第10版 英汉双解） V5_0.mdx"
        )


def get_collins_path() -> str:
    try:
        from .config import load_config

        config = load_config()
        return config.mdict.collins_path
    except Exception:
        return r"C:\baidunetdiskdownload\mdict\柯林斯\Collins COBUILD (CN - HD).mdx"


def clean_text(text):
    if not text:
        return ""
    return " ".join(text.split()).strip()


def parse_oxford(html):
    if not html:
        return None
    try:
        soup = BeautifulSoup(html, "html.parser")

        # 1. Phonetics (only from webtop or headword section to avoid inflections)
        phonetics = []
        webtop = soup.find(class_="webtop")
        if webtop:
            phon_tags = webtop.find_all("span", class_="phon")
        else:
            phon_tags = []
            for tag in soup.find_all("span", class_="phon"):
                if not tag.find_parent(class_=["verb_forms_table", "unbox"]):
                    phon_tags.append(tag)

        for tag in phon_tags:
            text = clean_text(tag.get_text())
            if text and text not in phonetics:
                phonetics.append(text)
        phonetic_str = " | ".join(phonetics) if phonetics else ""

        # 2. Chinese definitions
        zh_defs = []
        deft_tags = soup.find_all("deft")
        for tag in deft_tags:
            text = clean_text(tag.get_text())
            if text and text not in zh_defs:
                zh_defs.append(text)

        if not zh_defs:
            for tag in soup.find_all("chn"):
                if not tag.find_parent("xt"):
                    text = clean_text(tag.get_text())
                    if text and len(text) < 40 and text not in zh_defs:
                        zh_defs.append(text)

        zh_str = "；".join(zh_defs) if zh_defs else ""

        # 3. English definitions
        en_defs = []
        for def_tag in soup.find_all(class_="def"):
            def_copy = BeautifulSoup(str(def_tag), "html.parser")
            for decomp in def_copy.find_all(["chn", "deft", "xt"]):
                decomp.decompose()
            text = clean_text(def_copy.get_text())
            if text and len(text) > 3 and text not in en_defs:
                en_defs.append(text)

        if not en_defs:
            for sense_tag in soup.find_all(class_="sense"):
                sense_copy = BeautifulSoup(str(sense_tag), "html.parser")
                for decomp in sense_copy.find_all(["chn", "xt", "deft", "ul", "span", "div"]):
                    decomp.decompose()
                text = clean_text(sense_copy.get_text())
                text = (
                    text.replace("[transitive, intransitive]", "")
                    .replace("[transitive]", "")
                    .replace("[intransitive]", "")
                )
                text = clean_text(text)
                if text and len(text) > 5 and text not in en_defs:
                    en_defs.append(text)

        en_str = "; ".join(en_defs) if en_defs else ""

        pos_list = []
        for tag in soup.find_all(class_="pos"):
            text = clean_text(tag.get_text())
            if text and text not in pos_list:
                pos_list.append(text)
        pos_str = " / ".join(pos_list) if pos_list else ""

        return {"phonetic": phonetic_str, "zh": zh_str, "en": en_str, "pos": pos_str}
    except Exception:
        return None


def parse_collins(html):
    if not html:
        return None
    try:
        soup = BeautifulSoup(html, "html.parser")

        # 1. Phonetics
        phonetic_str = ""

        # 2. Chinese definitions
        zh_defs = []
        for tag in soup.find_all("span", class_="C1_text_blue"):
            text = clean_text(tag.get_text())
            if (
                text
                and len(text) < 40
                and not any(char in text for char in "。！？!?")
                and text not in zh_defs
            ):
                text = text.rstrip("；; ")
                if text and text not in zh_defs:
                    zh_defs.append(text)
        zh_str = "；".join(zh_defs) if zh_defs else ""

        # 3. English definitions
        en_defs = []
        for box in soup.find_all(class_="C1_explanation_box"):
            box_copy = BeautifulSoup(str(box), "html.parser")
            for decomp in box_copy.find_all(["span", "a"]):
                decomp.decompose()
            text = clean_text(box_copy.get_text())
            if text and len(text) > 5 and text not in en_defs:
                en_defs.append(text)

        en_str = "; ".join(en_defs) if en_defs else ""

        pos_list = []
        for tag in soup.find_all(class_=re.compile(r"(pos|word_class|class)", re.I)):
            text = clean_text(tag.get_text())
            if text and len(text) < 15 and text not in pos_list:
                pos_list.append(text)
        pos_str = " / ".join(pos_list) if pos_list else ""

        return {"phonetic": phonetic_str, "zh": zh_str, "en": en_str, "pos": pos_str}
    except Exception:
        return None


_OXFORD_MDX = None
_OXFORD_KEY_MAP = None
_COLLINS_MDX = None
_COLLINS_KEY_MAP = None


def get_oxford():
    global _OXFORD_MDX, _OXFORD_KEY_MAP
    if _OXFORD_MDX is None:
        path = get_oxford_path()
        if os.path.exists(path):
            try:
                from mdict_utils.reader import MDX

                _OXFORD_MDX = MDX(path)
                _OXFORD_KEY_MAP = {}
                for x, (offset, key) in enumerate(_OXFORD_MDX._key_list):
                    _OXFORD_KEY_MAP[key.lower()] = (x, offset, key)
            except Exception:
                pass
    return _OXFORD_MDX, _OXFORD_KEY_MAP


def get_collins():
    global _COLLINS_MDX, _COLLINS_KEY_MAP
    if _COLLINS_MDX is None:
        path = get_collins_path()
        if os.path.exists(path):
            try:
                from mdict_utils.reader import MDX

                _COLLINS_MDX = MDX(path)
                _COLLINS_KEY_MAP = {}
                for x, (offset, key) in enumerate(_COLLINS_MDX._key_list):
                    _COLLINS_KEY_MAP[key.lower()] = (x, offset, key)
            except Exception:
                pass
    return _COLLINS_MDX, _COLLINS_KEY_MAP


def query_mdx_cached(md, key_map, word_key: str) -> str | None:
    if not md or not key_map:
        return None
    word_bytes = word_key.encode("utf-8")
    if word_bytes not in key_map:
        return None
    try:
        from mdict_utils.reader import get_record

        x, offset, key = key_map[word_bytes]
        if (x + 1) < len(md._key_list):
            length = md._key_list[x + 1][0] - offset
        else:
            length = -1
        return get_record(md, key, offset, length)
    except Exception:
        return None


def query_word_local(word_key: str) -> dict[str, str] | None:
    # Oxford first
    md_ox, map_ox = get_oxford()
    if md_ox:
        html = query_mdx_cached(md_ox, map_ox, word_key)
        if html:
            res = parse_oxford(html)
            if res and (res["zh"] or res["en"]):
                return res

    # Collins second
    md_co, map_co = get_collins()
    if md_co:
        html = query_mdx_cached(md_co, map_co, word_key)
        if html:
            res = parse_collins(html)
            if res and (res["zh"] or res["en"]):
                return res

    return None


_LLM_CLIENT = None


def get_llm_client():
    global _LLM_CLIENT
    if _LLM_CLIENT is None:
        try:
            from .config import load_config

            config = load_config()
            if config.llm.api_key or config.llm.base_url:
                from openai import OpenAI

                base_url = normalize_openai_base_url(config.llm.base_url)

                api_key = config.llm.api_key or "ollama"
                _LLM_CLIENT = OpenAI(
                    api_key=api_key,
                    base_url=base_url or None,
                    max_retries=0,
                    timeout=5.0,
                )
        except Exception:
            pass
    return _LLM_CLIENT


def post_chat_completion_raw(
    url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout: float = 30.0,
) -> str:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


def fetch_from_llm(word: str) -> dict[str, str]:
    """Fetch compact dictionary fields from LLM as a final fallback."""
    global _LLM_EMPTY_RESPONSE_WARNED
    client = get_llm_client()
    if not client:
        return {"phonetic": "", "zh": "", "en": "", "pos": ""}
    try:
        from .config import load_config

        config = load_config()
        kind = "短语" if is_phrase_like(word) else "单词"
        pos_hint = "phrase" if is_phrase_like(word) else ""
        prompt = (
            f"请翻译英语{kind} {word}。只返回JSON："
            f'{{"phonetic":"","zh":"","en":"","pos":"{pos_hint}"}}'
        )

        payload = {
            "model": config.llm.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 800,
            "stream": False,
        }
        content = ""
        if config.llm.base_url.strip().endswith("/chat/completions"):
            content = post_chat_completion_raw(
                config.llm.base_url.strip(), config.llm.api_key, payload
            )
        else:
            response = client.chat.completions.create(**payload)
            content = (response.choices[0].message.content or "").strip()
        if not content:
            if not _LLM_EMPTY_RESPONSE_WARNED:
                safe_print(" [LLM empty response]", end="", flush=True)
                _LLM_EMPTY_RESPONSE_WARNED = True
            return dict(EMPTY_ENTRY)

        from .llm import parse_jsonish

        data = parse_jsonish(content)
        if isinstance(data, dict) and "raw" in data:
            extracted = extract_dictionary_fields(content, word)
            if extracted["zh"] or extracted["en"]:
                return extracted
            if len(content) <= 80:
                return {
                    "phonetic": "",
                    "zh": content,
                    "en": "",
                    "pos": "phrase" if is_phrase_like(word) else "",
                }
        if isinstance(data, dict):
            return {
                "phonetic": str(data.get("phonetic", "")).strip(),
                "zh": str(data.get("zh", "")).strip(),
                "en": str(data.get("en", "")).strip(),
                "pos": str(data.get("pos", "")).strip(),
            }
    except Exception:
        pass
    return dict(EMPTY_ENTRY)


def extract_dictionary_fields(content: str, word: str) -> dict[str, str]:
    def field(name: str) -> str:
        match = re.search(rf'"{name}"\s*:\s*"([^"]*)"', content)
        return match.group(1).strip() if match else ""

    return {
        "phonetic": field("phonetic"),
        "zh": field("zh"),
        "en": field("en"),
        "pos": field("pos") or ("phrase" if is_phrase_like(word) else ""),
    }


def query_word(word: str) -> dict[str, str]:
    """Query word details with in-memory caching and fast fallback."""
    word_key = word.strip().lower()
    if not word_key:
        return dict(EMPTY_ENTRY)

    cache = load_cache()
    if word_key in cache:
        cached = cache[word_key]
        if is_negative_cache_entry(cached, word_key):
            return dict(EMPTY_ENTRY)
        if is_stale_negative_cache_entry(cached, word_key):
            cache.pop(word_key, None)
        else:
            return cached

    safe_print(f"[Dict] Querying '{word_key}'...", end="", flush=True)

    # 1. Attempt local MDX queries first
    local_res = query_word_local(word_key)
    if local_res:
        safe_print(" [Local MDX]", flush=True)
        entry_data = {
            "phonetic": local_res.get("phonetic", ""),
            "zh": local_res.get("zh", ""),
            "en": local_res.get("en", ""),
            "pos": local_res.get("pos", ""),
        }
        cache[word_key] = entry_data
        save_cache(cache)
        return entry_data

    # 2. Attempt dictionary APIs for simple words only. Phrases are handled by seed/LLM metadata.
    if not _CIRCUIT_BROKEN and should_query_remote_dictionary(word_key):
        try:
            safe_print(" [API...]", end="", flush=True)
            youdao_zh = fetch_from_youdao(word_key)
            dict_api = fetch_from_dictionary_api(word_key)
            entry_data = {
                "phonetic": dict_api["phonetic"],
                "zh": youdao_zh,
                "en": dict_api["definition"],
                "pos": "",  # Dictionary API usually doesn't have clean general POS
            }
            if entry_data["zh"] or entry_data["en"]:
                safe_print(" [API Found]", flush=True)
                cache[word_key] = entry_data
                save_cache(cache)
                return entry_data
        except Exception:
            pass

    # 3. Final fallback: LLM
    if should_use_llm_fallback(word_key):
        safe_print(" [LLM fallback...]", end="", flush=True)
        llm_res = fetch_from_llm(word_key)
        if llm_res and (llm_res["zh"] or llm_res["en"]):
            safe_print(" [LLM Found]", flush=True)
            cache[word_key] = llm_res
            save_cache(cache)
            return llm_res

    safe_print(" [Not Found]", flush=True)
    cache[word_key] = empty_entry(_not_found=True, _not_found_policy=NEGATIVE_CACHE_POLICY)
    save_cache(cache)
    return dict(EMPTY_ENTRY)

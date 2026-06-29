from __future__ import annotations

import json
import urllib.request
import urllib.parse
import socket
from pathlib import Path
from typing import Any

# Set global socket timeout to 1.0s to prevent any DNS or connection hangs
socket.setdefaulttimeout(1.0)

CACHE_FILE = Path("data/dict_cache.json")

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
            data = json.loads(response.read().decode('utf-8'))
            entries = data.get("data", {}).get("entries", [])
            if entries:
                _CONSECUTIVE_FAILURES = 0  # Reset on success
                return str(entries[0].get("explain", "")).strip()
    except Exception:
        pass
        
    _CONSECUTIVE_FAILURES += 1
    if _CONSECUTIVE_FAILURES >= 3:
        _CIRCUIT_BROKEN = True
        print("[WARNING] Dictionary queries failed repeatedly. Entering offline circuit-breaker mode.")
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
            data = json.loads(response.read().decode('utf-8'))
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
        print("[WARNING] Dictionary queries failed repeatedly. Entering offline circuit-breaker mode.")
    return result

import os
import re
from bs4 import BeautifulSoup

def get_oxford_path() -> str:
    try:
        from .config import load_config
        config = load_config()
        return config.mdict.oxford_path
    except Exception:
        return r"C:\baidunetdiskdownload\mdict\牛津高阶（第10版 英汉双解）V5.0（含机翻）\牛津高阶（第10版 英汉双解） V5_0.mdx"

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
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. Phonetics (only from webtop or headword section to avoid inflections)
        phonetics = []
        webtop = soup.find(class_='webtop')
        if webtop:
            phon_tags = webtop.find_all('span', class_='phon')
        else:
            phon_tags = []
            for tag in soup.find_all('span', class_='phon'):
                if not tag.find_parent(class_=['verb_forms_table', 'unbox']):
                    phon_tags.append(tag)
                    
        for tag in phon_tags:
            text = clean_text(tag.get_text())
            if text and text not in phonetics:
                phonetics.append(text)
        phonetic_str = " | ".join(phonetics) if phonetics else ""
        
        # 2. Chinese definitions
        zh_defs = []
        deft_tags = soup.find_all('deft')
        for tag in deft_tags:
            text = clean_text(tag.get_text())
            if text and text not in zh_defs:
                zh_defs.append(text)
                
        if not zh_defs:
            for tag in soup.find_all('chn'):
                if not tag.find_parent('xt'):
                    text = clean_text(tag.get_text())
                    if text and len(text) < 40 and text not in zh_defs:
                        zh_defs.append(text)
                        
        zh_str = "；".join(zh_defs) if zh_defs else ""
        
        # 3. English definitions
        en_defs = []
        for def_tag in soup.find_all(class_='def'):
            def_copy = BeautifulSoup(str(def_tag), 'html.parser')
            for decomp in def_copy.find_all(['chn', 'deft', 'xt']):
                decomp.decompose()
            text = clean_text(def_copy.get_text())
            if text and len(text) > 3 and text not in en_defs:
                en_defs.append(text)
                
        if not en_defs:
            for sense_tag in soup.find_all(class_='sense'):
                sense_copy = BeautifulSoup(str(sense_tag), 'html.parser')
                for decomp in sense_copy.find_all(['chn', 'xt', 'deft', 'ul', 'span', 'div']):
                    decomp.decompose()
                text = clean_text(sense_copy.get_text())
                text = text.replace('[transitive, intransitive]', '').replace('[transitive]', '').replace('[intransitive]', '')
                text = clean_text(text)
                if text and len(text) > 5 and text not in en_defs:
                    en_defs.append(text)
                    
        en_str = "; ".join(en_defs) if en_defs else ""
        
        pos_list = []
        for tag in soup.find_all(class_='pos'):
            text = clean_text(tag.get_text())
            if text and text not in pos_list:
                pos_list.append(text)
        pos_str = " / ".join(pos_list) if pos_list else ""
        
        return {
            "phonetic": phonetic_str,
            "zh": zh_str,
            "en": en_str,
            "pos": pos_str
        }
    except Exception:
        return None

def parse_collins(html):
    if not html:
        return None
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # 1. Phonetics
        phonetic_str = ""
        
        # 2. Chinese definitions
        zh_defs = []
        for tag in soup.find_all('span', class_='C1_text_blue'):
            text = clean_text(tag.get_text())
            if text and len(text) < 40 and not any(char in text for char in '。！？!?') and text not in zh_defs:
                text = text.rstrip('；; ')
                if text and text not in zh_defs:
                    zh_defs.append(text)
        zh_str = "；".join(zh_defs) if zh_defs else ""
        
        # 3. English definitions
        en_defs = []
        for box in soup.find_all(class_='C1_explanation_box'):
            box_copy = BeautifulSoup(str(box), 'html.parser')
            for decomp in box_copy.find_all(['span', 'a']):
                decomp.decompose()
            text = clean_text(box_copy.get_text())
            if text and len(text) > 5 and text not in en_defs:
                en_defs.append(text)
                
        en_str = "; ".join(en_defs) if en_defs else ""
        
        pos_list = []
        for tag in soup.find_all(class_=re.compile(r'(pos|word_class|class)', re.I)):
            text = clean_text(tag.get_text())
            if text and len(text) < 15 and text not in pos_list:
                pos_list.append(text)
        pos_str = " / ".join(pos_list) if pos_list else ""
        
        return {
            "phonetic": phonetic_str,
            "zh": zh_str,
            "en": en_str,
            "pos": pos_str
        }
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
    word_bytes = word_key.encode('utf-8')
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
            if config.llm.api_key:
                from openai import OpenAI
                _LLM_CLIENT = OpenAI(
                    api_key=config.llm.api_key,
                    base_url=config.llm.base_url or None,
                    max_retries=0,
                    timeout=5.0
                )
        except Exception:
            pass
    return _LLM_CLIENT

def fetch_from_llm(word: str) -> dict[str, str]:
    """Fetch translation, phonetics, part of speech, and English gloss from LLM as a final fallback."""
    client = get_llm_client()
    if not client:
        return {"phonetic": "", "zh": "", "en": "", "pos": ""}
    try:
        from .config import load_config
        config = load_config()
        prompt = (
            "You are a lexicographer helping Chinese postgraduate students prepare for English exams.\n"
            f"Provide details for the English word: '{word}'.\n"
            "Return a JSON object with the following fields:\n"
            "1. 'phonetic': the IPA phonetic symbol (e.g. '/æˈbændən/')\n"
            "2. 'zh': the core Chinese meanings separated by semicolons (e.g. '放弃；遗弃')\n"
            "3. 'en': the core English definition (e.g. 'to leave a place, thing, or person forever')\n"
            "4. 'pos': the part of speech (e.g. 'noun', 'verb', 'adjective')\n"
            "Do NOT return any markdown wrapping or extra text. Return compact JSON only."
        )
        
        response = client.chat.completions.create(
            model=config.llm.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )
        content = (response.choices[0].message.content or "").strip()
        
        from .llm import parse_jsonish
        data = parse_jsonish(content)
        if isinstance(data, dict):
            return {
                "phonetic": str(data.get("phonetic", "")).strip(),
                "zh": str(data.get("zh", "")).strip(),
                "en": str(data.get("en", "")).strip(),
                "pos": str(data.get("pos", "")).strip()
            }
    except Exception:
        pass
    return {"phonetic": "", "zh": "", "en": "", "pos": ""}

def query_word(word: str) -> dict[str, str]:
    """Query word details with in-memory caching and fast fallback."""
    word_key = word.strip().lower()
    if not word_key:
        return {"phonetic": "", "zh": "", "en": "", "pos": ""}
    
    cache = load_cache()
    if word_key in cache:
        return cache[word_key]
        
    print(f"[Dict] Querying '{word_key}'...", end="", flush=True)
    
    # 1. Attempt local MDX queries first
    local_res = query_word_local(word_key)
    if local_res:
        print(" [Local MDX]", flush=True)
        entry_data = {
            "phonetic": local_res.get("phonetic", ""),
            "zh": local_res.get("zh", ""),
            "en": local_res.get("en", ""),
            "pos": local_res.get("pos", "")
        }
        cache[word_key] = entry_data
        save_cache(cache)
        return entry_data
        
    # 2. Attempt dictionary APIs
    if not _CIRCUIT_BROKEN:
        try:
            print(" [API...]", end="", flush=True)
            youdao_zh = fetch_from_youdao(word_key)
            dict_api = fetch_from_dictionary_api(word_key)
            entry_data = {
                "phonetic": dict_api["phonetic"],
                "zh": youdao_zh,
                "en": dict_api["definition"],
                "pos": ""  # Dictionary API usually doesn't have clean general POS
            }
            if entry_data["zh"] or entry_data["en"]:
                print(" [API Found]", flush=True)
                cache[word_key] = entry_data
                save_cache(cache)
                return entry_data
        except Exception:
            pass
            
    # 3. Final fallback: LLM
    print(" [LLM fallback...]", end="", flush=True)
    llm_res = fetch_from_llm(word_key)
    if llm_res and (llm_res["zh"] or llm_res["en"]):
        print(" [LLM Found]", flush=True)
        cache[word_key] = llm_res
        save_cache(cache)
        return llm_res
        
    print(" [Not Found]", flush=True)
    return {"phonetic": "", "zh": "", "en": "", "pos": ""}

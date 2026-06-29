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

def query_word(word: str) -> dict[str, str]:
    """Query word details with in-memory caching and fast fallback."""
    word_key = word.strip().lower()
    if not word_key:
        return {"phonetic": "", "zh": "", "en": ""}
    
    cache = load_cache()
    if word_key in cache:
        return cache[word_key]
        
    if _CIRCUIT_BROKEN:
        return {"phonetic": "", "zh": "", "en": ""}
    
    # Fetch from APIs
    youdao_zh = fetch_from_youdao(word_key)
    dict_api = fetch_from_dictionary_api(word_key)
    
    entry_data = {
        "phonetic": dict_api["phonetic"],
        "zh": youdao_zh,
        "en": dict_api["definition"]
    }
    
    cache[word_key] = entry_data
    save_cache(cache)
    return entry_data

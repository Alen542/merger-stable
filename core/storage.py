import json
import os
import logging

logger = logging.getLogger(__name__)

DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "intro.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

def _ensure_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def _load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"settings.json unreadable, using defaults: {e}")
            settings = {}
        # Guarantee required keys always exist (prevents KeyError)
        settings.setdefault("replacements", {})
        settings.setdefault("prefixes", [])
        return settings
    return {"replacements": {}, "prefixes": []}

def _save_settings(settings: dict):
    _ensure_dir()
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)

def add_replacement(old_word: str, new_word: str):
    settings = _load_settings()
    settings["replacements"][old_word] = new_word
    _save_settings(settings)

def get_replacements() -> dict:
    return _load_settings().get("replacements", {})

def del_replacement(word: str) -> bool:
    settings = _load_settings()
    if word in settings["replacements"]:
        del settings["replacements"][word]
        _save_settings(settings)
        return True
    return False

def add_prefix(prefix: str):
    settings = _load_settings()
    if prefix not in settings["prefixes"]:
        settings["prefixes"].append(prefix)
        _save_settings(settings)

def get_prefixes() -> list:
    return _load_settings().get("prefixes", [])

def del_prefix(prefix: str) -> bool:
    settings = _load_settings()
    if prefix in settings["prefixes"]:
        settings["prefixes"].remove(prefix)
        _save_settings(settings)
        return True
    return False

def _write_intro_data(data: dict):
    _ensure_dir()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def load_intro() -> dict | None:
    """Load intro data from JSON."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"intro.json unreadable: {e}")
            return None
    return None

def save_intro(file_id: str, file_name: str):
    """Save intro file_id and name to JSON, preserving any saved thumbnail."""
    data = load_intro() or {}
    data["file_id"] = file_id
    data["file_name"] = file_name
    _write_intro_data(data)

def delete_intro() -> bool:
    """Delete the intro entry, preserving any saved thumbnail."""
    data = load_intro()
    if not data or "file_id" not in data:
        return False
    data.pop("file_id", None)
    data.pop("file_name", None)
    if data:
        # Other keys remain (e.g. thumb_id) — keep the file
        _write_intro_data(data)
    else:
        os.remove(DATA_FILE)
    return True

def save_thumb(file_id: str):
    """Save thumbnail file_id to JSON, preserving intro data."""
    data = load_intro() or {}
    data["thumb_id"] = file_id
    _write_intro_data(data)

def get_thumb() -> str | None:
    """Get saved thumb file_id."""
    data = load_intro()
    return data.get("thumb_id") if data else None

def delete_thumb() -> bool:
    """Clear the thumbnail from JSON, preserving intro data."""
    data = load_intro()
    if data and "thumb_id" in data:
        del data["thumb_id"]
        if data:
            _write_intro_data(data)
        else:
            os.remove(DATA_FILE)
        return True
    return False

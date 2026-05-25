import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"


def load_llm_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_provider() -> str:
    cfg = load_llm_config()
    return (cfg.get("llm_provider") or "ollama").lower()


def save_llm_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = load_llm_config()
    existing.update(data)
    CONFIG_PATH.write_text(json.dumps(existing, indent=4), encoding="utf-8")

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
    from core.secrets import encrypt_secret

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = load_llm_config()
    secret_keys = ("gemini_api_key", "openai_api_key", "anthropic_api_key")
    for k, v in data.items():
        if k in secret_keys and v and not str(v).startswith("enc:"):
            sv = str(v).strip()
            if sv and "••••" not in sv:
                existing[k] = encrypt_secret(sv)
            continue
        existing[k] = v
    CONFIG_PATH.write_text(json.dumps(existing, indent=4), encoding="utf-8")


def provider_settings_public() -> dict:
    from core.secrets import decrypt_secret, mask_secret

    cfg = load_llm_config()
    return {
        "llm_provider": cfg.get("llm_provider") or "ollama",
        "ollama_model": cfg.get("ollama_model") or "qwen2.5:7b",
        "gemini_model": cfg.get("gemini_model") or "gemini-2.0-flash-lite",
        "openai_model": cfg.get("openai_model") or "gpt-4o-mini",
        "anthropic_model": cfg.get("anthropic_model") or "claude-3-5-haiku-latest",
        "enable_ollama": cfg.get("enable_ollama", True) is not False,
        "enable_gemini": bool(cfg.get("enable_gemini", True)),
        "enable_openai": bool(cfg.get("enable_openai", False)),
        "enable_anthropic": bool(cfg.get("enable_anthropic", False)),
        "cloud_token_budget": int(cfg.get("cloud_token_budget") or 1200),
        "cloud_max_output_tokens": int(cfg.get("cloud_max_output_tokens") or 220),
        "provider_daily_limits": cfg.get("provider_daily_limits") or {},
        "gemini_api_key_set": bool(decrypt_secret(str(cfg.get("gemini_api_key") or ""))),
        "openai_api_key_set": bool(decrypt_secret(str(cfg.get("openai_api_key") or ""))),
        "anthropic_api_key_set": bool(decrypt_secret(str(cfg.get("anthropic_api_key") or ""))),
        "gemini_api_key_masked": mask_secret(decrypt_secret(str(cfg.get("gemini_api_key") or ""))),
        "openai_api_key_masked": mask_secret(decrypt_secret(str(cfg.get("openai_api_key") or ""))),
        "anthropic_api_key_masked": mask_secret(decrypt_secret(str(cfg.get("anthropic_api_key") or ""))),
    }

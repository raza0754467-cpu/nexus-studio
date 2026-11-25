import json
import os
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = BASE_DIR / "projects"
BROWSER_SHOTS_DIR = DATA_DIR / "browser_shots"
CONFIG_FILE = DATA_DIR / "config.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
BROWSER_SHOTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CUSTOM_MODELS: List[Dict[str, Any]] = [
    {
        "id": "instant",
        "name": "Instant",
        "tagline": "Ultra-fast replies for everyday chat",
        "badge": "⚡",
        "temperature": 0.55,
        "groq_model": "openai/gpt-oss-20b",
        "cerebras_model": "llama3.1-8b",
        "gemini_model": "gemini-3.1-flash-lite",
        "openrouter_model": "nvidia/nemotron-3.5-lightning:free",
        "builtin": True,
    },
    {
        "id": "fast",
        "name": "Fast",
        "tagline": "Balanced intelligence & creative studio",
        "badge": "✦",
        "temperature": 0.65,
        "groq_model": "qwen/qwen3.8-27b",
        "cerebras_model": "llama-3.3-70b",
        "gemini_model": "gemini-flash-latest",
        "openrouter_model": "google/gemma-4-26b-a4b-it:free",
        "builtin": True,
    },
    {
        "id": "medium",
        "name": "Medium",
        "tagline": "Deep reasoning, strategy & studio scripts",
        "badge": "◆",
        "temperature": 0.72,
        "groq_model": "openai/gpt-oss-120b",
        "cerebras_model": "llama-3.3-70b",
        "gemini_model": "gemini-3-flash-preview",
        "openrouter_model": "google/gemma-4-31b-it:free",
        "builtin": True,
    },
]

USAGE_FILE = DATA_DIR / "usage.json"

SAAS_PLANS: Dict[str, Dict[str, Any]] = {
    "owner": {
        "id": "owner",
        "name": "Owner Studio",
        "price": "Unlocked",
        "daily_video_limit": 9999,
        "free_trial_videos": 9999,
        "max_duration_sec": 600,
        "allow_all_models": True,
        "allow_custom_models": True,
        "allow_approval_mode": True,
        "allow_seo_radar": True,
        "watermark": False,
    },
    "free": {
        "id": "free",
        "name": "Free Trial",
        "price": "$0",
        "daily_video_limit": 1,
        "free_trial_videos": 1,
        "max_duration_sec": 45,
        "allow_all_models": True,
        "allow_custom_models": False,
        "allow_approval_mode": False,
        "allow_seo_radar": True,
        "watermark": False,
    },
    "pro": {
        "id": "pro",
        "name": "Creator Pro",
        "price": "$19 / mo",
        "daily_video_limit": 30,
        "free_trial_videos": 9999,
        "max_duration_sec": 600,
        "allow_all_models": True,
        "allow_custom_models": True,
        "allow_approval_mode": True,
        "allow_seo_radar": True,
        "watermark": False,
    },
    "agency": {
        "id": "agency",
        "name": "Agency Studio",
        "price": "$49 / mo",
        "daily_video_limit": 999,
        "free_trial_videos": 9999,
        "max_duration_sec": 600,
        "allow_all_models": True,
        "allow_custom_models": True,
        "allow_approval_mode": True,
        "allow_seo_radar": True,
        "watermark": False,
    },
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "cerebras_api_key": "",
    "cerebras_model": "llama-3.3-70b",
    "groq_api_key": "",
    "groq_model": "qwen/qwen3.8-27b",
    "gemini_api_key": "",
    "gemini_model": "gemini-flash-latest",
    "openrouter_api_key": "",
    "openrouter_model": "google/gemma-4-31b-it:free",
    "custom_api_name": "",
    "custom_api_url": "",
    "custom_api_key": "",
    "custom_api_model": "",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "",
    "pollinations_enabled": True,
    "pexels_api_key": "",
    "pixabay_api_key": "",
    "google_client_id": "",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_pass": "",
    "smtp_from": "",
    "active_plan": "owner",
    "provider_order": ["groq", "gemini", "cerebras", "openrouter", "custom", "ollama", "pollinations"],
    "custom_models": DEFAULT_CUSTOM_MODELS,
}


def load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                cfg.update(saved)
        except Exception:
            pass
    env_map = {
        "cerebras_api_key": "CEREBRAS_API_KEY",
        "groq_api_key": "GROQ_API_KEY",
        "gemini_api_key": "GEMINI_API_KEY",
        "openrouter_api_key": "OPENROUTER_API_KEY",
        "pexels_api_key": "PEXELS_API_KEY",
        "pixabay_api_key": "PIXABAY_API_KEY",
        "google_client_id": "GOOGLE_CLIENT_ID",
        "smtp_host": "SMTP_HOST",
        "smtp_user": "SMTP_USER",
        "smtp_pass": "SMTP_PASS",
        "smtp_from": "SMTP_FROM",
    }
    for k, env_name in env_map.items():
        if not cfg.get(k) and os.environ.get(env_name):
            cfg[k] = os.environ[env_name].strip()
    return cfg


def save_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_config()
    for k, v in updates.items():
        if k in DEFAULT_CONFIG:
            if isinstance(v, str):
                # Do not overwrite real key with masked placeholder
                if "•" in v and k.endswith("_api_key"):
                    continue
                cfg[k] = v.strip()
            else:
                cfg[k] = v
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg


def masked_config() -> Dict[str, Any]:
    cfg = load_config()
    key_fields = [
        "cerebras_api_key",
        "groq_api_key",
        "gemini_api_key",
        "openrouter_api_key",
        "custom_api_key",
        "pexels_api_key",
        "pixabay_api_key",
        "smtp_pass",
    ]
    out: Dict[str, Any] = {
        "cerebras_model": cfg["cerebras_model"],
        "groq_model": cfg["groq_model"],
        "gemini_model": cfg["gemini_model"],
        "openrouter_model": cfg["openrouter_model"],
        "custom_api_name": cfg.get("custom_api_name", ""),
        "custom_api_url": cfg.get("custom_api_url", ""),
        "custom_api_model": cfg.get("custom_api_model", ""),
        "ollama_url": cfg["ollama_url"],
        "ollama_model": cfg["ollama_model"],
        "pollinations_enabled": cfg.get("pollinations_enabled", True),
        "google_client_id": cfg.get("google_client_id", ""),
        "smtp_host": cfg.get("smtp_host", "smtp.gmail.com"),
        "smtp_port": cfg.get("smtp_port", 587),
        "smtp_user": cfg.get("smtp_user", ""),
        "smtp_from": cfg.get("smtp_from", ""),
        "active_plan": cfg.get("active_plan", "owner"),
        "provider_order": cfg.get("provider_order", DEFAULT_CONFIG["provider_order"]),
        "custom_models": cfg.get("custom_models") or DEFAULT_CUSTOM_MODELS,
        "configured": {k: bool(cfg.get(k)) for k in key_fields},
    }
    for k in key_fields:
        val = cfg.get(k, "")
        if len(val) > 10:
            out[k] = val[:4] + "•" * 8 + val[-4:]
        elif val:
            out[k] = "•" * len(val)
        else:
            out[k] = ""
    return out


def list_projects() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not PROJECTS_DIR.exists():
        return items
    for folder in sorted(PROJECTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not folder.is_dir():
            continue
        meta_file = folder / "project.json"
        if not meta_file.exists():
            continue
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            items.append(
                {
                    "id": data.get("id", folder.name),
                    "topic": data.get("topic", "Untitled"),
                    "status": data.get("status", "idle"),
                    "format": data.get("format", "9:16"),
                    "language": data.get("language", "Urdu"),
                    "created_at": data.get("created_at", ""),
                    "has_video": (folder / "final_video.mp4").exists(),
                    "has_thumbnail": (folder / "thumbnail.png").exists(),
                }
            )
        except Exception:
            continue
    return items

import asyncio
import json
import os
import re
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx

from auth_manager import (
    check_video_quota,
    get_user_by_token,
    login_user,
    logout_token,
    record_video_usage,
    register_user,
    update_user_plan,
)
from config_manager import (
    BASE_DIR,
    BROWSER_SHOTS_DIR,
    DATA_DIR,
    PROJECTS_DIR,
    SAAS_PLANS,
    list_projects,
    load_config,
    masked_config,
    save_config,
)
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BASE_DIR / ".browsers"))
from employees.boss_chat import classify_intent, generate_pro_reply, generate_scene_edit
from employees.browser_agent import run_autonomous_browser_agent, run_live_browser_task
from employees.emp1_researcher import run_researcher
from employees.emp2_strategist import run_strategist
from employees.emp3_scriptwriter import run_scriptwriter
from employees.emp4_producer import VOICE_PRESETS, generate_voice_clip, run_producer
from employees.emp5_editor import run_editor
from employees.llm_router import MultiProviderLLM
from employees.seo_engine import fetch_google_trends_rss, run_million_search_seo

app = FastAPI(title="NEXUS STUDIO — 5-Employee AI Video & Browser Command Center")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/media/projects", StaticFiles(directory=str(PROJECTS_DIR)), name="project_media")
app.mount("/media/browser", StaticFiles(directory=str(BROWSER_SHOTS_DIR)), name="browser_media")

# In-memory live state cache for ultra-fast polling
LIVE_PROJECTS: Dict[str, Dict[str, Any]] = {}
RUNNING_TASKS: Dict[str, asyncio.Task] = {}


def _now_str() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return (s[:36] or "video")


PROJECT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{4,120}$")


def _validate_project_id(project_id: str) -> str:
    if not PROJECT_ID_RE.match(project_id or ""):
        raise HTTPException(status_code=400, detail="Invalid project ID")
    return project_id


def _require_localhost(request: Request) -> None:
    # Block remote traffic coming through tunnels (localhost.run / Cloudflare) or cloud reverse proxies
    if request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for"):
        raise HTTPException(status_code=403, detail="Admin access is restricted to direct localhost only.")
    host_hdr = (request.headers.get("host") or "").split(":")[0].strip().lower()
    if host_hdr and host_hdr not in ("127.0.0.1", "localhost", "::1", "testserver"):
        raise HTTPException(status_code=403, detail="Admin access is restricted to direct localhost only.")
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(status_code=403, detail="Admin access is restricted to localhost.")


def _project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / _validate_project_id(project_id)


def _save_project(proj: Dict[str, Any]) -> None:
    pdir = _project_dir(proj["id"])
    pdir.mkdir(parents=True, exist_ok=True)
    LIVE_PROJECTS[proj["id"]] = proj
    (pdir / "project.json").write_text(json.dumps(proj, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_project(project_id: str) -> Optional[Dict[str, Any]]:
    if project_id in LIVE_PROJECTS:
        return LIVE_PROJECTS[project_id]
    pfile = _project_dir(project_id) / "project.json"
    if pfile.exists():
        try:
            data = json.loads(pfile.read_text(encoding="utf-8"))
            LIVE_PROJECTS[project_id] = data
            return data
        except Exception:
            return None
    return None


def _init_employees_state() -> Dict[str, Dict[str, Any]]:
    return {
        "emp1": {"name": "Researcher", "role": "Social Media & Browser Intel", "status": "idle", "provider": "", "elapsed": 0},
        "emp2": {"name": "Strategist", "role": "Multi-Platform Master Plan", "status": "idle", "provider": "", "elapsed": 0},
        "emp3": {"name": "Scriptwriter", "role": "Viral Script & SEO Pack", "status": "idle", "provider": "", "elapsed": 0},
        "emp4": {"name": "Producer", "role": "Neural Voice & HD Visuals", "status": "idle", "provider": "", "elapsed": 0},
        "emp5": {"name": "Editor", "role": "Cinema Render & Captions", "status": "idle", "provider": "", "elapsed": 0},
    }


def _pick_default_voice(language: str, gender: str = "female") -> str:
    lang = (language or "english").lower()
    mapping = {
        "urdu": ("urdu_female_noor", "urdu_male_asad"),
        "hindi": ("hindi_female_ananya", "hindi_male_aarav"),
        "arabic": ("ar_zariyah_sa", "ar_hamed_sa"),
        "spanish": ("es_dalia_mx", "es_jorge_mx"),
        "french": ("fr_denise", "fr_henri"),
        "german": ("de_katja", "de_conrad"),
        "portuguese": ("pt_francisca_br", "pt_antonio_br"),
        "turkish": ("tr_emel", "tr_ahmet"),
        "indonesian": ("id_gadis", "id_ardi"),
        "italian": ("it_elsa", "it_diego"),
        "japanese": ("ja_nanami", "ja_nanami"),
        "korean": ("ko_sunhi", "ko_sunhi"),
        "chinese": ("zh_xiaoxiao", "zh_xiaoxiao"),
        "russian": ("ru_svetlana", "ru_svetlana"),
    }
    for key, (fem, mal) in mapping.items():
        if key in lang:
            return fem if gender == "female" else mal
    return "en_ava_multi" if gender == "female" else "en_andrew_multi"


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateProjectRequest(BaseModel):
    topic: str
    format: str = "9:16"
    language: str = "English"
    voice: str = "auto"
    duration_sec: int = 35
    visual_style: str = "Viral Typography"
    caption_animation: str = "pop"
    visual_mode: str = "hybrid"
    model_profile: str = "fast"
    approval_mode: bool = False
    use_live_browser: bool = False
    visible_browser: bool = False
    enable_captions: bool = True
    enable_music: bool = True


class CustomModelRequest(BaseModel):
    id: Optional[str] = None
    name: str
    tagline: str = "Custom studio preset"
    badge: str = "✨"
    temperature: float = 0.65
    groq_model: str = "qwen/qwen3.8-27b"
    cerebras_model: str = "llama-3.3-70b"
    gemini_model: str = "gemini-flash-latest"
    openrouter_model: str = "google/gemma-4-31b-it:free"


class UpdateScenesRequest(BaseModel):
    scenes: List[Dict[str, Any]]
    video_title: Optional[str] = None
    thumbnail_headline: Optional[str] = None
    thumbnail_subline: Optional[str] = None
    rerender: bool = True


class BrowserRunRequest(BaseModel):
    url_or_query: str
    mode: str = "auto"
    visible: bool = False


class AutonomousBrowserRequest(BaseModel):
    goal: str
    start_url: str = ""
    max_steps: int = 6
    visible: bool = False


class SeoRadarRequest(BaseModel):
    topic: str
    geo: str = "PK"


class PlanSwitchRequest(BaseModel):
    plan_id: str


class ChatRequest(BaseModel):
    message: str
    history: List[Dict[str, str]] = []
    active_project_id: Optional[str] = None
    model_profile: str = "instant"
    force_browser: bool = False
    visible_browser: bool = False


class ConfigUpdateRequest(BaseModel):
    cerebras_api_key: Optional[str] = None
    cerebras_model: Optional[str] = None
    groq_api_key: Optional[str] = None
    groq_model: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openrouter_model: Optional[str] = None
    custom_api_name: Optional[str] = None
    custom_api_url: Optional[str] = None
    custom_api_key: Optional[str] = None
    custom_api_model: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    pollinations_enabled: Optional[bool] = None
    pexels_api_key: Optional[str] = None
    pixabay_api_key: Optional[str] = None
    active_plan: Optional[str] = None


async def _run_production_stages_4_5(proj: Dict[str, Any]) -> None:
    pdir = _project_dir(proj["id"])
    cfg = load_config()

    def log(msg: str) -> None:
        proj["logs"].append({"time": _now_str(), "msg": msg})
        proj["logs"] = proj["logs"][-160:]
        _save_project(proj)

    try:
        # Employee 4: Voice & Visual Producer
        proj["status"] = "running"
        proj["employees"]["emp4"]["status"] = "working"
        t0 = time.time()
        _save_project(proj)

        producer_data = await run_producer(
            script_data=proj["script"],
            project_dir=pdir,
            video_format=proj["format"],
            voice_key=proj["voice"],
            visual_mode=proj["visual_mode"],
            config=cfg,
            log_fn=log,
            visual_style=proj.get("visual_style", "Realistic Cinema"),
        )
        proj["producer"] = producer_data
        proj["employees"]["emp4"]["status"] = "done"
        proj["employees"]["emp4"]["provider"] = "Studio Audio + Visuals"
        proj["employees"]["emp4"]["elapsed"] = round(time.time() - t0, 1)
        _save_project(proj)

        # Employee 5: Cinema Video Editor
        proj["employees"]["emp5"]["status"] = "working"
        t0 = time.time()
        _save_project(proj)

        editor_data = await run_editor(
            project_dir=pdir,
            topic=proj["topic"],
            script_data=proj["script"],
            producer_data=producer_data,
            video_format=proj["format"],
            enable_captions=proj.get("enable_captions", True),
            enable_music=proj.get("enable_music", True),
            log_fn=log,
            visual_style=proj.get("visual_style", "Realistic Cinema"),
            caption_animation=proj.get("caption_animation", "pop"),
        )
        proj["editor"] = editor_data
        proj["employees"]["emp5"]["status"] = "done"
        proj["employees"]["emp5"]["provider"] = "FFmpeg Cinema"
        proj["employees"]["emp5"]["elapsed"] = round(time.time() - t0, 1)
        proj["status"] = "completed"
        log("ALL 5 EMPLOYEES COMPLETED! Final video & social upload pack are ready.")
        _save_project(proj)
    except Exception as exc:
        proj["status"] = "error"
        proj["error"] = str(exc)
        for ek in ("emp4", "emp5"):
            if proj["employees"][ek]["status"] == "working":
                proj["employees"][ek]["status"] = "error"
        log(f"ERROR: {exc}")
        _save_project(proj)


def _apply_model_profile(cfg: Dict[str, Any], profile_id: str) -> Dict[str, Any]:
    out = dict(cfg)
    models = cfg.get("custom_models") or []
    for m in models:
        if m.get("id") == profile_id:
            for k in ("groq_model", "cerebras_model", "gemini_model", "openrouter_model"):
                if m.get(k):
                    out[k] = m[k]
            break
    return out


async def _run_full_pipeline(proj: Dict[str, Any]) -> None:
    pdir = _project_dir(proj["id"])
    cfg = _apply_model_profile(load_config(), proj.get("model_profile", "fast"))

    def log(msg: str) -> None:
        proj["logs"].append({"time": _now_str(), "msg": msg})
        proj["logs"] = proj["logs"][-160:]
        _save_project(proj)

    llm = MultiProviderLLM(cfg, log_fn=log)

    try:
        proj["status"] = "running"
        _save_project(proj)

        # Employee 1: Social Media Researcher (+ Live Browser Agent)
        proj["employees"]["emp1"]["status"] = "working"
        t0 = time.time()
        _save_project(proj)

        dossier = await run_researcher(
            topic=proj["topic"],
            language=proj["language"],
            project_dir=pdir,
            use_live_browser=proj.get("use_live_browser", True),
            visible_browser=proj.get("visible_browser", False),
            llm=llm,
            log_fn=log,
        )
        proj["research"] = dossier
        proj["employees"]["emp1"]["status"] = "done"
        proj["employees"]["emp1"]["provider"] = dossier.get("provider_used", "").upper()
        proj["employees"]["emp1"]["elapsed"] = round(time.time() - t0, 1)
        _save_project(proj)

        # Employee 2: Content Strategist & Planner
        proj["employees"]["emp2"]["status"] = "working"
        t0 = time.time()
        _save_project(proj)

        plan = await run_strategist(
            topic=proj["topic"],
            research_dossier=dossier,
            video_format=proj["format"],
            duration_sec=proj["duration_sec"],
            language=proj["language"],
            visual_style=proj["visual_style"],
            llm=llm,
            log_fn=log,
        )
        proj["strategy"] = plan
        proj["employees"]["emp2"]["status"] = "done"
        proj["employees"]["emp2"]["provider"] = plan.get("provider_used", "").upper()
        proj["employees"]["emp2"]["elapsed"] = round(time.time() - t0, 1)
        _save_project(proj)

        # Employee 3: Viral Scriptwriter & SEO Pack
        proj["employees"]["emp3"]["status"] = "working"
        t0 = time.time()
        _save_project(proj)

        script_data = await run_scriptwriter(
            topic=proj["topic"],
            research_dossier=dossier,
            strategy_plan=plan,
            video_format=proj["format"],
            duration_sec=proj["duration_sec"],
            language=proj["language"],
            visual_style=proj["visual_style"],
            llm=llm,
            log_fn=log,
        )
        proj["script"] = script_data
        proj["employees"]["emp3"]["status"] = "done"
        proj["employees"]["emp3"]["provider"] = script_data.get("provider_used", "").upper()
        proj["employees"]["emp3"]["elapsed"] = round(time.time() - t0, 1)
        _save_project(proj)

        # Boss Approval Checkpoint?
        if proj.get("approval_mode"):
            proj["status"] = "awaiting_approval"
            log("PAUSED FOR BOSS APPROVAL: Review/edit the script & scenes in Tab 03, then click 'Approve & Render Video'!")
            _save_project(proj)
            return

        await _run_production_stages_4_5(proj)

    except Exception as exc:
        proj["status"] = "error"
        proj["error"] = str(exc)
        for ek in proj["employees"]:
            if proj["employees"][ek]["status"] == "working":
                proj["employees"][ek]["status"] = "error"
        log(f"PIPELINE ERROR: {exc}")
        _save_project(proj)


@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
@app.get("/signup", response_class=HTMLResponse)
@app.get("/chat", response_class=HTMLResponse)
@app.get("/studio", response_class=HTMLResponse)
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>NEXUS is loading...</h1>")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/admin", response_class=HTMLResponse)
async def serve_admin(request: Request):
    _require_localhost(request)
    admin_path = STATIC_DIR / "admin.html"
    if not admin_path.exists():
        return HTMLResponse("<h1>Admin panel missing</h1>")
    return HTMLResponse(admin_path.read_text(encoding="utf-8"))


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return "User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: /sitemap.xml\n"


@app.get("/sitemap.xml")
async def sitemap_xml():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://nexus-studio.app/</loc><priority>1.0</priority></url>
  <url><loc>https://nexus-studio.app/#video-factory</loc><priority>0.9</priority></url>
  <url><loc>https://nexus-studio.app/#seo-radar</loc><priority>0.9</priority></url>
  <url><loc>https://nexus-studio.app/#browser-lab</loc><priority>0.8</priority></url>
  <url><loc>https://nexus-studio.app/#plans</loc><priority>0.8</priority></url>
</urlset>"""
    return Response(content=xml, media_type="application/xml")


@app.get("/api/meta")
async def get_meta():
    """Public metadata — exposes ONLY branded NEXUS model names (zero backend provider leakage!)."""
    cfg = load_config()
    active_plan_id = cfg.get("active_plan", "owner")
    public_models = [
        {
            "id": m.get("id"),
            "name": m.get("name"),
            "tagline": m.get("tagline", ""),
            "badge": m.get("badge", "✦"),
            "builtin": m.get("builtin", False),
        }
        for m in (cfg.get("custom_models") or [])
    ]
    return {
        "voices": VOICE_PRESETS,
        "models": public_models,
        "active_plan": SAAS_PLANS.get(active_plan_id, SAAS_PLANS["owner"]),
        "plans": SAAS_PLANS,
    }


@app.post("/api/plans/mode")
async def switch_plan_mode(req: PlanSwitchRequest, request: Request):
    _require_localhost(request)
    if req.plan_id not in SAAS_PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan_id")
    save_config({"active_plan": req.plan_id})
    return {"ok": True, "active_plan": SAAS_PLANS[req.plan_id]}


@app.post("/api/seo/radar")
async def api_seo_radar(req: SeoRadarRequest):
    logs: List[str] = []
    data = await run_million_search_seo(req.topic.strip(), geo=req.geo, log_fn=lambda m: logs.append(m))
    data["logs"] = logs
    return data


@app.get("/api/seo/trends")
async def api_seo_trends(geo: str = "PK"):
    trends = await fetch_google_trends_rss(geo=geo)
    return {"geo": geo, "trends": trends}


@app.post("/api/models/sync")
async def api_sync_live_models(request: Request):
    _require_localhost(request)
    """
    Lifetime Protection: Dynamically discovers active models from Groq, OpenRouter, Gemini & Ollama
    so NEXUS STUDIO stays up-to-date even years from now.
    """
    cfg = load_config()
    discovered: Dict[str, List[str]] = {"groq": [], "openrouter_free": [], "gemini": [], "ollama": []}
    async with httpx.AsyncClient(timeout=15.0) as client:
        if cfg.get("groq_api_key"):
            try:
                r = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {cfg['groq_api_key']}"},
                )
                if r.status_code == 200:
                    discovered["groq"] = [m["id"] for m in r.json().get("data", []) if "whisper" not in m["id"]][:16]
            except Exception:
                pass
        if cfg.get("openrouter_api_key"):
            try:
                r = await client.get("https://openrouter.ai/api/v1/models")
                if r.status_code == 200:
                    discovered["openrouter_free"] = [
                        m["id"] for m in r.json().get("data", []) if ":free" in m.get("id", "")
                    ][:20]
            except Exception:
                pass
        if cfg.get("gemini_api_key"):
            try:
                r = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={cfg['gemini_api_key']}"
                )
                if r.status_code == 200:
                    discovered["gemini"] = [
                        m["name"].replace("models/", "")
                        for m in r.json().get("models", [])
                        if "gemini" in m.get("name", "")
                    ][:14]
            except Exception:
                pass
        try:
            base = (cfg.get("ollama_url") or "http://localhost:11434").rstrip("/")
            r = await client.get(f"{base}/api/tags", timeout=3.0)
            if r.status_code == 200:
                discovered["ollama"] = [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass
    return {"ok": True, "discovered": discovered}


@app.post("/api/browser/agent")
async def api_browser_agent(req: AutonomousBrowserRequest):
    cfg = load_config()
    plan = SAAS_PLANS.get(cfg.get("active_plan", "owner"), SAAS_PLANS["owner"])
    steps_cap = min(req.max_steps, int(plan.get("max_browser_steps", 8)))
    logs: List[str] = []
    llm = MultiProviderLLM(cfg, log_fn=lambda m: logs.append(m))
    res = await run_autonomous_browser_agent(
        goal=req.goal.strip(),
        start_url=req.start_url.strip(),
        save_dir=BROWSER_SHOTS_DIR,
        llm=llm,
        max_steps=steps_cap,
        visible=req.visible,
        log_fn=lambda m: logs.append(m),
    )
    res["logs"] = logs
    for s in res.get("screenshots", []):
        s["media_url"] = f"/media/browser/{s['filename']}"
    return res


@app.post("/api/models")
async def add_custom_model(req: CustomModelRequest, request: Request):
    _require_localhost(request)
    cfg = load_config()
    models = list(cfg.get("custom_models") or [])
    mid = (req.id or _slugify(req.name)).lower()
    entry = {
        "id": mid,
        "name": req.name.strip()[:24],
        "tagline": req.tagline.strip()[:60],
        "badge": (req.badge or "✨")[:4],
        "temperature": max(0.0, min(1.2, float(req.temperature))),
        "groq_model": req.groq_model.strip(),
        "cerebras_model": req.cerebras_model.strip(),
        "gemini_model": req.gemini_model.strip(),
        "openrouter_model": req.openrouter_model.strip(),
        "builtin": False,
    }
    models = [m for m in models if m.get("id") != mid]
    models.append(entry)
    save_config({"custom_models": models})
    return {"ok": True, "custom_models": models}


@app.delete("/api/models/{model_id}")
async def delete_custom_model(model_id: str, request: Request):
    _require_localhost(request)
    cfg = load_config()
    models = list(cfg.get("custom_models") or [])
    models = [m for m in models if not (m.get("id") == model_id and not m.get("builtin"))]
    save_config({"custom_models": models})
    return {"ok": True, "custom_models": models}


@app.get("/api/config")
async def get_config(request: Request):
    _require_localhost(request)
    return masked_config()


@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest, request: Request):
    _require_localhost(request)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    save_config(updates)
    return {"ok": True, "config": masked_config()}


@app.post("/api/config/test")
async def test_all_keys(request: Request):
    _require_localhost(request)
    cfg = load_config()
    llm = MultiProviderLLM(cfg)
    results = []
    for p in ["groq", "gemini", "cerebras", "openrouter", "custom", "ollama", "pollinations"]:
        if p == "cerebras" and not cfg.get("cerebras_api_key"):
            continue
        if p == "groq" and not cfg.get("groq_api_key"):
            continue
        if p == "gemini" and not cfg.get("gemini_api_key"):
            continue
        if p == "openrouter" and not cfg.get("openrouter_api_key"):
            continue
        if p == "custom" and not (cfg.get("custom_api_url") and cfg.get("custom_api_key")):
            continue
        if p == "ollama" and not cfg.get("ollama_model"):
            continue
        if p == "pollinations" and not cfg.get("pollinations_enabled", True):
            continue
        results.append(await llm.test_provider(p))
    return {"results": results}


@app.get("/api/projects")
async def api_list_projects():
    return {"projects": list_projects()}


@app.get("/api/showcase")
async def api_showcase():
    """Returns curated real playable showcase videos for the public NEXUS Homepage Gallery."""
    items: List[Dict[str, Any]] = []
    showcase_dir = STATIC_DIR / "showcase"
    bundled = [
        ("creator_showcase.mp4", "creator_showcase.jpg", "Viral Kinetic Typography Reel", "Expressive 3-font captions & warm editorial studio canvas", "Viral Typography", "Urdu", "31s", "Featured Creation"),
        ("urdu_viral_typography.mp4", "urdu_viral_typography.png", "Best Free AI Voice Tools 2026", "Warm parchment canvas, 3D character art & natural Urdu voice", "Viral Typography", "Urdu", "29s", "Viral Typography"),
        ("english_realistic_cinema.mp4", "english_realistic_cinema.png", "3 AI Tools Replacing Full Agencies", "Editorial photography & active-word karaoke pop captions", "Realistic Cinema", "English", "33s", "Realistic Cinema"),
        ("uk_motion_glow.mp4", "uk_motion_glow.png", "Why 90% Stay Stuck — 5-Minute Reset", "British narration & neon glow pulse kinetic captions", "Motion Graphics Pro", "English (UK)", "32s", "Motion Graphics"),
    ]
    for vfile, pfile, title, sub, style, lang, dur, badge in bundled:
        if (showcase_dir / vfile).exists():
            items.append(
                {
                    "id": vfile.rsplit(".", 1)[0],
                    "title": title,
                    "subtitle": sub,
                    "style": style,
                    "language": lang,
                    "format": "9:16",
                    "duration": dur,
                    "video_url": f"/static/showcase/{vfile}",
                    "poster_url": f"/static/showcase/{pfile}" if (showcase_dir / pfile).exists() else "",
                    "badge": badge,
                }
            )

    # Also include latest newly created local studio videos if fewer than 6
    seen_titles = {x["title"].lower() for x in items}
    for proj in list_projects():
        if len(items) >= 6:
            break
        if not proj.get("has_video"):
            continue
        pfull = _load_project(proj["id"]) or {}
        title = (pfull.get("script") or {}).get("video_title") or proj["topic"]
        if title.lower() in seen_titles or proj["id"] in (
            "20261125_231232_2026-ke-best-free-ai-voice-tools_d627",
            "20261125_231550_3-ai-tools-replacing-full-teams-in-2_66d7",
            "20261126_002222_why-90-percent-of-people-stay-stuck-_2772",
        ):
            continue
        ed = pfull.get("editor") or {}
        items.append(
            {
                "id": proj["id"],
                "title": title,
                "subtitle": f"{pfull.get('visual_style', 'Studio')} • {proj.get('language', 'Global')} • {ed.get('resolution', '1080x1920')}",
                "style": pfull.get("visual_style", "Studio"),
                "language": proj.get("language", "Global"),
                "format": proj.get("format", "9:16"),
                "duration": f"{int(round(float(ed.get('duration_sec') or pfull.get('duration_sec') or 30)))}s",
                "video_url": f"/media/projects/{proj['id']}/final_video.mp4",
                "poster_url": f"/media/projects/{proj['id']}/thumbnail.png" if proj.get("has_thumbnail") else "",
                "badge": pfull.get("visual_style", "AI Studio"),
            }
        )
    return {"items": items}


@app.post("/api/projects")
async def api_create_project(
    req: CreateProjectRequest,
    authorization: Optional[str] = Header(default=None),
    x_guest_id: Optional[str] = Header(default=None),
):
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    token = (authorization or "").replace("Bearer ", "").strip()
    # Enforce $0 Free Plan = 1 free trial video (Owner/Pro/Agency remain unlimited)
    allowed, reason = check_video_quota(token, x_guest_id)
    if not allowed:
        raise HTTPException(status_code=402, detail=reason)

    pid = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_slugify(topic)}_{uuid.uuid4().hex[:4]}"
    voice_key = req.voice if req.voice in VOICE_PRESETS else _pick_default_voice(req.language)

    proj: Dict[str, Any] = {
        "id": pid,
        "topic": topic,
        "format": req.format,
        "language": req.language,
        "voice": voice_key,
        "duration_sec": req.duration_sec,
        "visual_style": req.visual_style,
        "caption_animation": req.caption_animation,
        "visual_mode": req.visual_mode,
        "model_profile": req.model_profile,
        "approval_mode": req.approval_mode,
        "use_live_browser": False,
        "visible_browser": False,
        "enable_captions": req.enable_captions,
        "enable_music": req.enable_music,
        "status": "queued",
        "error": "",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "employees": _init_employees_state(),
        "research": None,
        "strategy": None,
        "script": None,
        "producer": None,
        "editor": None,
        "logs": [{"time": _now_str(), "msg": f"Studio launched 5-Agent Team for: '{topic}'"}],
    }
    _save_project(proj)
    record_video_usage(token, x_guest_id)

    task = asyncio.create_task(_run_full_pipeline(proj))
    RUNNING_TASKS[pid] = task
    return proj


@app.get("/api/projects/{project_id}")
async def api_get_project(project_id: str):
    proj = _load_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj


@app.post("/api/projects/{project_id}/approve")
async def api_approve_project(project_id: str):
    proj = _load_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    if not proj.get("script"):
        raise HTTPException(status_code=400, detail="Script is not ready yet")

    proj["employees"]["emp4"]["status"] = "idle"
    proj["employees"]["emp5"]["status"] = "idle"
    proj["logs"].append({"time": _now_str(), "msg": "Boss approved script! Launching Employee 4 & Employee 5..."})
    _save_project(proj)

    task = asyncio.create_task(_run_production_stages_4_5(proj))
    RUNNING_TASKS[project_id] = task
    return {"ok": True, "project": proj}


@app.post("/api/projects/{project_id}/scenes")
async def api_update_scenes(project_id: str, req: UpdateScenesRequest):
    proj = _load_project(project_id)
    if not proj or not proj.get("script"):
        raise HTTPException(status_code=404, detail="Project or script not found")

    proj["script"]["scenes"] = req.scenes
    if req.video_title is not None:
        proj["script"]["video_title"] = req.video_title
    if req.thumbnail_headline is not None:
        proj["script"]["thumbnail_headline"] = req.thumbnail_headline
    if req.thumbnail_subline is not None:
        proj["script"]["thumbnail_subline"] = req.thumbnail_subline

    proj["logs"].append({"time": _now_str(), "msg": "Boss updated scene storyboard."})
    _save_project(proj)

    if req.rerender:
        proj["employees"]["emp4"]["status"] = "idle"
        proj["employees"]["emp5"]["status"] = "idle"
        _save_project(proj)
        task = asyncio.create_task(_run_production_stages_4_5(proj))
        RUNNING_TASKS[project_id] = task

    return {"ok": True, "project": proj}


@app.post("/api/projects/{project_id}/open-folder")
async def api_open_folder(project_id: str):
    pdir = _project_dir(project_id)
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="Folder not found")
    try:
        os.startfile(str(pdir))  # Windows native Explorer open
    except Exception:
        subprocess.Popen(["explorer", str(pdir)])
    return {"ok": True, "path": str(pdir)}


@app.get("/api/projects/{project_id}/download/{filename}")
async def api_download_file(project_id: str, filename: str):
    safe_name = Path(filename).name
    fpath = _project_dir(project_id) / safe_name
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(fpath), filename=f"{project_id}_{safe_name}")


@app.post("/api/browser/run")
async def api_browser_run(req: BrowserRunRequest):
    logs: List[str] = []
    res = await run_live_browser_task(
        url_or_query=req.url_or_query,
        save_dir=BROWSER_SHOTS_DIR,
        mode=req.mode,
        visible=req.visible,
        log_fn=lambda m: logs.append(m),
    )
    res["logs"] = logs
    # Build browser media URLs
    for s in res.get("screenshots", []):
        s["media_url"] = f"/media/browser/{s['filename']}"
    return res


@app.post("/api/auth/register")
async def api_auth_register(req: RegisterRequest):
    try:
        return register_user(req.name, req.email, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/auth/login")
async def api_auth_login(req: LoginRequest):
    try:
        return login_user(req.email, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@app.get("/api/auth/me")
async def api_auth_me(authorization: Optional[str] = Header(default=None)):
    token = (authorization or "").replace("Bearer ", "").strip()
    return {"user": get_user_by_token(token)}


@app.post("/api/auth/logout")
async def api_auth_logout(authorization: Optional[str] = Header(default=None)):
    token = (authorization or "").replace("Bearer ", "").strip()
    logout_token(token)
    return {"ok": True}


@app.post("/api/auth/plan")
async def api_auth_plan(req: PlanSwitchRequest, authorization: Optional[str] = Header(default=None)):
    token = (authorization or "").replace("Bearer ", "").strip()
    user = update_user_plan(token, req.plan_id)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in first to update your plan.")
    return {"ok": True, "user": user}


@app.get("/api/voices/preview/{voice_key}")
async def api_voice_preview(voice_key: str):
    if voice_key not in VOICE_PRESETS:
        raise HTTPException(status_code=404, detail="Voice not found")
    samples_dir = DATA_DIR / "voice_samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    out_mp3 = samples_dir / f"{voice_key}.mp3"
    if not out_mp3.exists():
        sample_txt = VOICE_PRESETS[voice_key].get("sample", "Hello from NEXUS Studio.")
        await generate_voice_clip(sample_txt, voice_key, out_mp3)
    return FileResponse(str(out_mp3), media_type="audio/mpeg")


@app.post("/api/chat/stream")
async def api_chat_stream(
    req: ChatRequest,
    authorization: Optional[str] = Header(default=None),
    x_guest_id: Optional[str] = Header(default=None),
):
    """
    Ultra-Fast Master Conversational Stream (Zero Live Browser overhead!):
    - Everyday chat skips extra classification round-trip completely for instant responses.
    - Clean Thinking status + crisp Markdown reply OR 5-Agent Video launch OR live scene edit.
    """
    token = (authorization or "").replace("Bearer ", "").strip()
    current_user = get_user_by_token(token)
    user_name = current_user.get("name") if current_user else None

    queue: asyncio.Queue = asyncio.Queue()

    async def push(ev: Dict[str, Any]) -> None:
        await queue.put(ev)

    async def worker() -> None:
        try:
            cfg = _apply_model_profile(load_config(), req.model_profile or "instant")
            llm = MultiProviderLLM(cfg)
            active_proj = _load_project(req.active_project_id) if req.active_project_id else None

            await push({"type": "activity", "text": "Thinking..."})
            decision = await classify_intent(req.message, req.history, active_proj, llm)

            action = decision.get("action", "reply")
            params = decision.get("params") or {}

            if action == "start_video" and params.get("topic"):
                allowed, reason = check_video_quota(token, x_guest_id)
                if not allowed:
                    await push({"type": "final", "action": "quota_limit", "reply": reason})
                    return

                dur = max(30, min(600, int(params.get("duration_sec") or 35)))
                v_style = str(params.get("visual_style") or "Viral Typography")
                await push({"type": "activity", "text": f"Launching 5-Agent Video Studio ({dur}s • {v_style})..."})
                create_req = CreateProjectRequest(
                    topic=str(params.get("topic")),
                    format=str(params.get("format") or "9:16"),
                    language=str(params.get("language") or "English"),
                    duration_sec=dur,
                    visual_style=v_style,
                    model_profile=req.model_profile or "fast",
                    use_live_browser=False,
                )
                proj = await api_create_project(create_req, authorization=authorization, x_guest_id=x_guest_id)
                reply_text = (
                    f"Your **5-Agent Video Studio** is now running.\n\n"
                    f"- **Topic:** {proj['topic']}\n"
                    f"- **Style:** {v_style} • **{proj['format']}** • **~{dur}s** ({proj['language']})\n\n"
                    f"Click **Open Video Studio** below to watch all 5 agents build your video live."
                )
                await push({"type": "final", "action": "start_video", "reply": reply_text, "project": proj})

            elif action == "edit_scene" and active_proj and active_proj.get("script"):
                snum = int(params.get("scene_number") or 1)
                await push({"type": "activity", "text": f"Updating Scene {snum} & re-rendering..."})
                scenes = active_proj["script"].get("scenes") or []
                target_sc = next((s for s in scenes if int(s.get("scene_number", 0)) == snum), scenes[0] if scenes else None)
                if target_sc:
                    edited = await generate_scene_edit(req.message, target_sc, llm)
                    for field in ("narration", "subtitle_text", "visual_query", "ai_image_prompt"):
                        if edited.get(field):
                            target_sc[field] = edited[field]
                    _save_project(active_proj)
                    active_proj["employees"]["emp4"]["status"] = "idle"
                    active_proj["employees"]["emp5"]["status"] = "idle"
                    _save_project(active_proj)
                    RUNNING_TASKS[active_proj["id"]] = asyncio.create_task(_run_production_stages_4_5(active_proj))
                    await push({"type": "final", "action": "edit_scene", "reply": edited.get("confirmation", f"Scene {snum} updated!"), "project": active_proj})
                else:
                    reply_text = await generate_pro_reply(req.message, req.history, active_proj, user_name, llm)
                    await push({"type": "final", "action": "reply", "reply": reply_text})

            else:
                reply_text = await generate_pro_reply(req.message, req.history, active_proj, user_name, llm)
                await push({"type": "final", "action": "reply", "reply": reply_text})

        except Exception:
            await push({"type": "error", "message": "Unable to complete that right now. Please try again in a moment."})
        finally:
            await queue.put(None)

    asyncio.create_task(worker())

    async def event_gen():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.post("/api/chat")
async def api_boss_chat(req: ChatRequest):
    cfg = _apply_model_profile(load_config(), req.model_profile or "instant")
    llm = MultiProviderLLM(cfg)
    active_proj = _load_project(req.active_project_id) if req.active_project_id else None
    reply_text = await generate_pro_reply(req.message, req.history, active_proj, None, llm)
    return {"action": "reply", "reply": reply_text}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8765, reload=False)

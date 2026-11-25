# NEXUS — AI Chat, Live Side Browser & 5-Agent Video Studio

## Quick Start
- **Folder:** `C:\Users\Mudeer Team 4\OneDrive\Pictures\Gemi\nexus-studio`
- **Launch:** Double-click `START_NEXUS_STUDIO.bat`
- **Public App (White-Label):** `http://127.0.0.1:8765`
- **Private Admin Console (Localhost Only):** `http://127.0.0.1:8765/admin`

---

## Architecture & Capabilities

### 1. Pure-White ChatGPT-Style Workspace (`static/index.html`, `static/styles.css`, `static/app.js`)
- **100% White-Label Public UI:** Visitors on `/` see only **NEXUS** and custom model tiers (**Instant**, **Fast**, **Medium**, plus custom presets configured in `/admin`). Zero backend provider names, API keys, or internal tooling are exposed publicly.
- **Real Local Accounts & Auth (`auth_manager.py`):** PBKDF2-SHA256 password hashing (`data/users.json`, `data/sessions.json`). Guests see **Sign in** / **Create account** (no `Upgrade Plan` button while logged out); signed-in users see their profile, plan badge, personalized greeting, and upgrade options.
- **Live SSE Status & Streaming Chat (`employees/boss_chat.py`, `/api/chat/stream`):** 2-stage architecture (tiny JSON intent classifier + pure 3,800-token Markdown writer) handles long stories, tutorials, code, and strategy without JSON parse errors, while showing live working status (`Thinking...`, `Opening live browser...`, `Launching 5-agent video team...`).

### 2. Split-Screen Live Side Browser (`employees/browser_agent.py`)
- Launches portable Playwright Chromium (`.browsers/chromium-1255`) inside a real-time split-screen right pane whenever you click **Live Browser**, toggle **Browse**, or ask NEXUS to visit/research a site.
- Streams live screenshots, current URL, step actions, and clickable frame history directly to the UI over Server-Sent Events (SSE), with automatic CAPTCHA/login safety stop and plain-text recovery.

### 3. 5-Agent AI Video Production Studio (`employees/emp1–emp5`)
1. **Employee 1 — Researcher (`emp1_researcher.py` + `seo_engine.py`):** Live YouTube/Instagram/Facebook/Web research + Real-Time Google & YouTube Autocomplete + Google Trends RSS (`PK`/`US`/`IN`/`GB`/`AE`) with Roman-Urdu seed extraction.
2. **Employee 2 — Strategist (`emp2_strategist.py`):** Duration-aware scene blueprints (5 scenes for 30s–40s shorts up to 24 scenes for 5–10 minute YouTube videos) and platform playbooks (YouTube, Instagram Reels, Facebook).
3. **Employee 3 — Scriptwriter (`emp3_scriptwriter.py`):** Batched scene writing (8 scenes/batch for long-form) in Urdu, Roman Urdu, Hindi, and English with full word-for-word `subtitle_text` matching spoken `narration`, real named tools (never fake placeholders), and a full YouTube/Instagram/Facebook upload pack.
4. **Employee 4 — Producer (`emp4_producer.py`):**
   - **16 Expressive Neural Voices** (Urdu, Hindi, English Multilingual V2) with live `▶ Preview` audio and exact millisecond `WordBoundary` speech timestamps.
   - **Signature Visual Styles:**
     - **Viral Typography** (`@nr.vibes0.1` inspired): Warm creamy parchment-gold radial canvas, 2× supersampled lavender corner floral accent, rounded framed 3D character art, and warm editorial cover thumbnail.
     - **Realistic Cinema / Motion Graphics Pro / Documentary Vox / Futuristic Tech / Luxury Editorial**: Optional Pexels/Pixabay HD video footage → Clean HD photography (strictly filtering watermarked stock & UI screenshot domains like `ftcdn.net`, `shutterstock`, `istock`, `dribbble`) → Rate-limit-aware AI Cinema visuals → Motion graphics fallback.
5. **Employee 5 — Editor (`emp5_editor.py`):**
   - Millisecond word-synced **3-Font Boxless Viral Kinetic Typography** (`Brush Script` + outlined coral-red/royal-indigo `Impact` + `Segoe Print Bold`) OR **Active-Word Karaoke Pop** (boxless gold/cyan spoken word highlight + top progress bar) with zero blank caption gaps.
   - Smooth FFmpeg `xfade` video transitions + `acrossfade` audio crossfades + procedural ambient soundtrack with transition whoosh SFX.
   - Exports Full HD `1080×1920` (9:16) or `1920×1080` (16:9) `final_video.mp4`, `thumbnail.png`, `subtitles.srt`, and `social_media_pack.md`.

### 4. Hidden Admin & Multi-Provider Waterfall (`/admin`, `employees/llm_router.py`)
- Restricted strictly to localhost (`127.0.0.1` / `::1`) across `/admin`, `/api/config*`, `/api/models*`, and `/api/plans/mode`.
- Automatic 7-layer failover waterfall (`Groq` → `Gemini` → `Cerebras` → `OpenRouter :free` → `Custom OpenAI-Compatible` → `Ollama` → `Pollinations`) with 1-Click Live Model Sync.

---

## Honest Technical Boundaries (Optional Upgrades)
- **Moving Stock Video Clips:** Free out-of-the-box mode uses HD photography + Ken Burns motion + AI visuals + `xfade` transitions. Adding free **Pexels** or **Pixabay** API keys in `/admin` immediately unlocks real moving HD `.mp4` stock clips per scene.
- **Generative Text-to-Video (Veo / Runway / Kling):** Full AI-generated moving video scenes require paid external video-generation APIs or a dedicated local GPU; NEXUS achieves studio-grade pacing free via Ken Burns cinema motion, animated word-synced typography, and `xfade` transitions.
- **Anonymous AI Image Rate Limits:** Public zero-key Flux endpoints throttle rapid back-to-back calls; NEXUS automatically spaces requests and falls back cleanly to watermark-filtered HD photography so renders never stall.

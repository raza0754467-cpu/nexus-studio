---
title: NEXUS Studio
emoji: 🎬
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# NEXUS — Global AI Conversation & 5-Agent Video Studio

Pure-white global AI workspace combining fast, human-like conversational intelligence with an autonomous 5-agent Full HD video production studio (16+ languages, 38+ realistic voices, kinetic animated captions, and 20+ country Search Trend Radar).

## Free Cloud Deployment (Hugging Face Spaces — 16 GB RAM Free)
1. Create a free account on https://huggingface.co
2. Create a new **Space** → SDK: **Docker** → Hardware: **CPU basic (Free)**
3. Add Repository Secrets in Space Settings:
   - `GROQ_API_KEY`
   - `GEMINI_API_KEY`
   - `OPENROUTER_API_KEY`
   - *(Optional)* `PEXELS_API_KEY` / `PIXABAY_API_KEY` for moving stock video clips
4. Upload this folder (excluding `.venv`, `.tools`, `.browsers`, and `data/config.json`) — your permanent live URL will be ready automatically!

import re
from typing import Any, Dict, List, Optional
from employees.llm_router import MultiProviderLLM

# Fast zero-latency regex trigger: ONLY call the video/scene classifier when the message
# actually hints at creating a video or editing an active scene — makes normal chat 2x faster!
VIDEO_TRIGGER_RE = re.compile(
    r"\b(video|reel|reels|short|shorts|tiktok|youtube|typography|clip|render|banao|bana\s*do|bnado|bnwa|bna\s*dy|bna\s*de|create\s+a\s+video|make\s+a\s+video|generate\s+video|scene\s*\d+|edit\s+scene)\b",
    re.IGNORECASE,
)


async def classify_intent(
    user_message: str,
    history: List[Dict[str, str]],
    active_project: Optional[Dict[str, Any]],
    llm: MultiProviderLLM,
) -> Dict[str, Any]:
    """
    Ultra-Fast Zero-Waste Intent Router:
    - Normal conversation skips extra classifier round-trip completely (instant sub-second reply!).
    - Only invokes tiny JSON classifier when user explicitly mentions video creation or scene editing.
    - Never launches any live browser.
    """
    msg = (user_message or "").strip()
    if not VIDEO_TRIGGER_RE.search(msg):
        return {"action": "reply", "params": {}}

    proj_hint = "none"
    if active_project and (active_project.get("script") or {}).get("scenes"):
        proj_hint = f"active video '{active_project.get('topic')}' ({len(active_project['script']['scenes'])} scenes)"

    sys_prompt = (
        "Classify the user's message into ONE intent and return ONLY compact JSON (under 110 tokens). "
        "NEVER write the full answer here — only classify."
    )
    usr_prompt = f"""
ACTIVE VIDEO CONTEXT: {proj_hint}
USER MESSAGE: {msg[:500]}

Choose ONE action:
- "start_video": User explicitly asks to create/make/generate/produce a video, reel, short, or typography video right now.
- "edit_scene": Active video exists AND user explicitly asks to modify/edit a specific scene's narration, caption, or visual.
- "reply": EVERYTHING ELSE (asking questions about video, writing a script/story/caption, discussing YouTube/TikTok advice, general chat, brainstorming).

Return ONLY JSON:
{{
  "action": "reply" | "start_video" | "edit_scene",
  "params": {{
    "topic": "short clear topic if start_video",
    "format": "9:16" or "16:9",
    "language": "English" | "Urdu" | "Roman Urdu" | "Hindi" | "Arabic" | "Spanish" | "French" | "German" | "Portuguese" | "Turkish" | "Indonesian" | "Japanese" | "Korean" | "Chinese" | "Italian" | "Russian",
    "duration_sec": 35,
    "visual_style": "Viral Typography" | "Motion Graphics Pro" | "Realistic Cinema",
    "scene_number": 1
  }}
}}
Note: Default duration_sec to 35 unless user specifies longer (e.g. 60, 180, 300, 600).
"""
    try:
        data, _ = await llm.generate_json(sys_prompt, usr_prompt, temperature=0.1, max_tokens=220)
        act = str(data.get("action", "reply")).lower()
        if act not in ("reply", "start_video", "edit_scene"):
            act = "reply"
        return {"action": act, "params": data.get("params") or {}}
    except Exception:
        return {"action": "reply", "params": {}}


async def generate_pro_reply(
    user_message: str,
    history: List[Dict[str, str]],
    active_project: Optional[Dict[str, Any]],
    user_name: Optional[str],
    llm: MultiProviderLLM,
) -> str:
    """
    Master-Level Human-Like Conversational Engine (Global Multilingual, Ultra-Fast, Zero Robotic Clichés).
    """
    recent = "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content', '')[:800]}"
        for m in history[-14:]
    )
    ctx_lines = []
    if user_name:
        ctx_lines.append(f"User's name: {user_name}")
    if active_project:
        ctx_lines.append(f"Current Video Studio project: '{active_project.get('topic')}' (Status: {active_project.get('status')})")
    ctx = ("\n".join(ctx_lines) + "\n\n") if ctx_lines else ""

    system_prompt = (
        "You are NEXUS — a remarkably sharp, natural, human-like AI partner and creative strategist used by creators worldwide.\n\n"
        "CORE CONVERSATION PRINCIPLES (FOLLOW STRICTLY):\n"
        "1. Speak like a real, intelligent human — warm, confident, natural, and direct. NEVER use robotic filler like 'Certainly!', 'Great question!', 'As an AI...', or repetitive sign-offs.\n"
        "2. Deeply understand the user's real goal, subtext, mood, language, and writing script. CRITICAL SCRIPT RULE: Match the EXACT language AND script the user uses — if the user writes in Roman Urdu (Latin letters like 'bhai kesy ho', 'main soch raha hun'), ALWAYS reply in natural Roman Urdu (Latin letters), NEVER switch to Urdu/Arabic Nastaliq script unless the user themselves wrote in Urdu script! Same for Hinglish, English, Arabic, Spanish, French, German, Turkish, etc.\n"
        "3. Be crisp, clear, accurate, and relevant. Do NOT pad answers with unnecessary long explanations — keep everyday replies tight and punchy. Only go long when the user genuinely asks for a story, full guide, code, or deep breakdown.\n"
        "4. Remember the entire conversation history carefully and stay completely consistent with earlier context.\n"
        "5. Think independently — do NOT blindly agree with everything the user says. If their idea has a flaw or a smarter alternative exists, politely point it out with clear reasoning.\n"
        "6. Never make up facts, statistics, or fake certainty. If you are unsure or made a mistake, admit it honestly and directly.\n"
        "7. Explain complex technical or business topics in simple, everyday words anyone can immediately grasp.\n"
        "8. Think carefully before answering so every reply feels thoughtful, fresh, and genuinely useful.\n"
        "9. NEVER mention internal backend engines or API providers (Groq, Gemini, OpenRouter, Pollinations, FFmpeg, Edge TTS) — you are NEXUS."
    )

    user_prompt = f"""{ctx}CONVERSATION HISTORY:
{recent or "(New conversation)"}

USER:
{user_message}
"""
    text, _ = await llm.generate(system_prompt, user_prompt, temperature=0.68, max_tokens=3200)
    return text.strip()


async def generate_scene_edit(
    user_message: str,
    scene: Dict[str, Any],
    llm: MultiProviderLLM,
) -> Dict[str, Any]:
    sys_prompt = "Update the given video scene cleanly according to the user's instruction. Return ONLY valid JSON."
    usr_prompt = f"""
CURRENT SCENE: {scene}
USER EDIT INSTRUCTION: {user_message}

Return JSON with updated fields:
{{
  "narration": "updated spoken narration",
  "subtitle_text": "updated on-screen caption (Latin script, no '/' slashes)",
  "visual_query": "updated English visual query",
  "ai_image_prompt": "updated cinematic visual prompt",
  "confirmation": "Short natural confirmation in user's language"
}}
"""
    data, _ = await llm.generate_json(sys_prompt, usr_prompt, temperature=0.5, max_tokens=900)
    return data

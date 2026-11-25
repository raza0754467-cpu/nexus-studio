from typing import Any, Callable, Dict, List
from employees.llm_router import MultiProviderLLM

LANGUAGE_INSTRUCTIONS = {
    "Urdu": (
        "Write `narration` in natural, crisp, authentic Pakistani Urdu script (اردو) so the Urdu voice sounds 100% human and expressive. "
        "CRITICAL CAPTION SYNC RULE: Write `subtitle_text` as ONLY clean Roman Urdu (single language, 1:1 word-for-word match with `narration` — "
        "NEVER include a '/' slash, NEVER repeat an English translation after the Roman Urdu, and NEVER write a short 4-word title summary!)."
    ),
    "Roman Urdu": (
        "Write `narration` in natural Pakistani Urdu script (اردو) for realistic pronunciation. "
        "CRITICAL CAPTION SYNC RULE: Write `subtitle_text` as ONLY clean Roman Urdu matching `narration` word-for-word "
        "(single language, NO '/' slashes, NO duplicate English translation, NOT a short summary!)."
    ),
    "Hindi": (
        "Write `narration` in natural conversational Hindi (Devanagari script) for expressive human speech. "
        "CRITICAL CAPTION SYNC RULE: Write `subtitle_text` as ONLY clean Hinglish (Latin script) matching `narration` word-for-word "
        "(NO '/' slashes, NO duplicate English translation, NOT a short summary!)."
    ),
    "English": (
        "Write both `narration` and `subtitle_text` as identical, crisp, punchy conversational English (exact word-for-word match, NO '/' slashes!). "
        "Zero clichés like 'In today's fast-paced world' or 'Welcome back guys'."
    ),
    "Arabic": (
        "Write `narration` in natural modern conversational Arabic script (العربية) for expressive native voiceover. "
        "CRITICAL CAPTION SYNC RULE: Write `subtitle_text` as clean, punchy English/Latin-script captions matching every spoken sentence 1:1 (NO '/' slashes!) so animated kinetic typography renders crisply."
    ),
    "Spanish": (
        "Write both `narration` and `subtitle_text` as identical, punchy, natural Spanish (exact word-for-word match, NO '/' slashes!)."
    ),
    "French": (
        "Write both `narration` and `subtitle_text` as identical, crisp, natural French (exact word-for-word match, NO '/' slashes!)."
    ),
    "German": (
        "Write both `narration` and `subtitle_text` as identical, crisp, natural German (exact word-for-word match, NO '/' slashes!)."
    ),
    "Portuguese": (
        "Write both `narration` and `subtitle_text` as identical, natural Brazilian Portuguese (exact word-for-word match, NO '/' slashes!)."
    ),
    "Turkish": (
        "Write both `narration` and `subtitle_text` as identical, natural conversational Turkish (exact word-for-word match, NO '/' slashes!)."
    ),
    "Indonesian": (
        "Write both `narration` and `subtitle_text` as identical, natural conversational Indonesian (exact word-for-word match, NO '/' slashes!)."
    ),
    "Italian": (
        "Write both `narration` and `subtitle_text` as identical, natural expressive Italian (exact word-for-word match, NO '/' slashes!)."
    ),
    "Japanese": (
        "Write `narration` in natural conversational Japanese for authentic native speech. "
        "Write `subtitle_text` as clean Romaji/English matching every spoken beat 1:1 (NO '/' slashes!) for crisp kinetic typography."
    ),
    "Korean": (
        "Write `narration` in natural conversational Korean for authentic native speech. "
        "Write `subtitle_text` as clean Romanized/English captions matching every spoken beat 1:1 (NO '/' slashes!)."
    ),
    "Chinese": (
        "Write `narration` in natural conversational Mandarin Chinese for authentic native speech. "
        "Write `subtitle_text` as clean Pinyin/English captions matching every spoken beat 1:1 (NO '/' slashes!)."
    ),
    "Russian": (
        "Write `narration` in natural conversational Russian for authentic native speech. "
        "Write `subtitle_text` as clean Latin/English captions matching every spoken beat 1:1 (NO '/' slashes!)."
    ),
}

STYLE_PROMPT_MODIFIERS = {
    "Viral Typography": (
        "cute 3D Pixar-style stylized character illustration, soft warm cream parchment background #FFF5D6, "
        "friendly expressive pose, clean studio lighting, minimalist cozy aesthetic, no text, no watermark"
    ),
    "Motion Graphics Pro": (
        "sleek high-contrast 3D motion graphics studio scene, clean geometric glassmorphism shapes, "
        "cinematic depth of field, ultra-sharp 8k editorial render, no text"
    ),
    "Realistic Cinema": (
        "photorealistic 8k cinema documentary still, shot on ARRI Alexa 35mm, natural dramatic lighting, "
        "shallow depth of field, authentic human/real-world atmosphere, rich film color grading, no text"
    ),
    "Cinematic Dark": (
        "cinematic dark moody photography, dramatic rim lighting, 8k film still, shallow depth of field, no text"
    ),
    "Documentary Vox": (
        "modern editorial documentary photography, crisp studio lighting, natural tones, high visual clarity, no text"
    ),
    "Futuristic Tech": (
        "sleek futuristic technology scene, subtle glowing blue and silver reflections, dark glass studio, 8k render, no text"
    ),
    "Luxury Editorial": (
        "luxury architectural minimalism, warm golden hour lighting, Leica 35mm film aesthetic, no text"
    ),
}


async def run_scriptwriter(
    topic: str,
    research_dossier: Dict[str, Any],
    strategy_plan: Dict[str, Any],
    video_format: str,
    duration_sec: int,
    language: str,
    visual_style: str,
    llm: MultiProviderLLM,
    log_fn: Callable[[str], None],
) -> Dict[str, Any]:
    log_fn(f"Scriptwriter crafting {language} script & SEO pack (~{duration_sec}s)...")

    lang_rule = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["English"])
    style_mod = STYLE_PROMPT_MODIFIERS.get(visual_style, STYLE_PROMPT_MODIFIERS["Realistic Cinema"])
    blueprint = strategy_plan.get("scene_blueprint") or []
    scene_count = max(4, min(24, len(blueprint) if blueprint else 6))
    words_per_scene = max(14, min(68, int((duration_sec * 2.35) / scene_count)))

    system_prompt = (
        "You are an Elite Viral Video Scriptwriter & Typography Director. "
        "Every line must hook attention immediately. Never use robotic AI intros. "
        "CRITICAL RULES: "
        "1. NEVER use fake placeholders like 'Tool A', 'Tool B', 'Tool C', 'App 1', or 'Website X' — ALWAYS name REAL, authentic tools/examples! "
        "2. `subtitle_text` MUST cover the ENTIRE spoken `narration` word-for-word (NOT a 4-word headline!), so captions animate throughout the whole scene! "
        "3. `hero_emphasis` must be 1-3 UPPERCASE PUNCH WORDS that actually appear inside `subtitle_text`! "
        "4. `visual_query` must be clean, concrete photographic search keywords (e.g. 'person typing modern laptop glowing screen', 'smartphone analytics chart close up') — avoid abstract words like 'holographic subscribe button'."
    )

    # For long-form 5-10 min videos (>10 scenes), write scenes in clean batches so nothing ever truncates!
    all_scenes: List[Dict[str, Any]] = []
    batch_size = 8
    video_meta: Dict[str, Any] = {}

    for b_start in range(0, scene_count, batch_size):
        b_end = min(scene_count, b_start + batch_size)
        sub_bp = blueprint[b_start:b_end] if blueprint else [
            {"scene_number": i + 1, "role": f"Part {i + 1}", "beat_summary": topic}
            for i in range(b_start, b_end)
        ]
        is_first = b_start == 0
        log_fn(f"Writing scenes {b_start + 1}–{b_end} of {scene_count}...")

        if is_first:
            schema_extra = f"""
  "video_title": "Punchy master title",
  "thumbnail_headline": "2-4 bold words for cover (Latin script)",
  "thumbnail_subline": "3-6 word curiosity subline",
  "social_pack": {{
    "youtube": {{
      "title": "High-CTR YouTube title (max 70 chars) with top search keyword",
      "alt_titles": ["Alternative A/B title 1", "Alternative A/B title 2"],
      "description": "Engaging 3-paragraph YouTube SEO description packed with live Google/YT search terms + CTA",
      "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9", "tag10", "tag11", "tag12"],
      "pinned_comment": "Engaging pinned question"
    }},
    "instagram": {{
      "caption": "Scroll-stopping Reels caption with value & Save CTA",
      "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5", "#tag6", "#tag7", "#tag8", "#tag9", "#tag10"]
    }},
    "facebook": {{
      "post_copy": "Relatable high-share Facebook post with conversation starter",
      "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5", "#tag6"]
    }}
  }},"""
        else:
            schema_extra = ""

        user_prompt = f"""
TOPIC: {topic}
FORMAT: {video_format} | TOTAL DURATION: ~{duration_sec}s | THIS BATCH: Scenes {b_start + 1} to {b_end} of {scene_count}
WORDS PER SCENE: ~{words_per_scene} spoken words
VISUAL STYLE: {visual_style} ({style_mod})

LANGUAGE & CAPTION RULE:
{lang_rule}

STRATEGY & LIVE SEO DATA:
- Winning Angle: {strategy_plan.get('winning_angle', '')}
- Hook Strategy: {strategy_plan.get('hook_strategy', '')}
- Key Facts: {research_dossier.get('key_facts_and_insights', [])[:5]}
- Live Google Keywords: {(research_dossier.get('seo_intelligence') or {}).get('google_autocomplete', [])[:8]}
- Live YouTube Keywords: {(research_dossier.get('seo_intelligence') or {}).get('youtube_autocomplete', [])[:8]}
- Scenes to write in THIS batch: {sub_bp}

Return JSON with this EXACT schema:
{{
{schema_extra}
  "scenes": [
    {{
      "scene_number": {b_start + 1},
      "role": "Hook / Tip / Proof / CTA",
      "narration": "Natural spoken voiceover (~{words_per_scene} words)",
      "subtitle_text": "Clean punchy on-screen caption text (Latin script)",
      "hero_emphasis": "1-3 UPPERCASE PUNCH WORDS from the caption (e.g., AI VOICE READY)",
      "visual_query": "2-4 realistic real-world English photo keywords (NO software UI, NO screenshots, NO logos, NO dashboards)",
      "ai_image_prompt": "UNIQUE scene-specific visual subject/action/prop for THIS exact scene (MUST differ from every other scene!), {style_mod}"
    }}
  ]
}}
"""
        batch_data, provider = await llm.generate_json(system_prompt, user_prompt, temperature=0.65, max_tokens=4200)
        if is_first:
            video_meta = batch_data
        all_scenes.extend(batch_data.get("scenes") or [])

    for idx, sc in enumerate(all_scenes, start=1):
        sc["scene_number"] = idx
        sc.setdefault("role", f"Scene {idx}")
        sc.setdefault("narration", "")
        sc.setdefault("subtitle_text", sc.get("narration", ""))
        sc.setdefault("hero_emphasis", "")
        sc.setdefault("visual_query", topic)
        sc.setdefault("ai_image_prompt", f"Cinematic scene for {topic}, {style_mod}")

    video_meta["scenes"] = all_scenes
    video_meta["provider_used"] = provider
    log_fn(f"Scriptwriter finished {len(all_scenes)} scenes + YouTube/Instagram/Facebook upload pack.")
    return video_meta

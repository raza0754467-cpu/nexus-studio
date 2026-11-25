from typing import Any, Callable, Dict
from employees.llm_router import MultiProviderLLM


def compute_scene_count(duration_sec: int) -> int:
    if duration_sec <= 35:
        return 5
    if duration_sec <= 45:
        return 6
    if duration_sec <= 65:
        return 8
    if duration_sec <= 100:
        return 10
    if duration_sec <= 200:
        return 14
    if duration_sec <= 360:
        return 18
    return 24


async def run_strategist(
    topic: str,
    research_dossier: Dict[str, Any],
    video_format: str,
    duration_sec: int,
    language: str,
    visual_style: str,
    llm: MultiProviderLLM,
    log_fn: Callable[[str], None],
) -> Dict[str, Any]:
    log_fn("Strategist designing multi-platform plan & retention blueprint...")

    scene_count = compute_scene_count(duration_sec)
    avg_sec = max(5, round(duration_sec / scene_count))

    compact_research = {
        "executive_summary": research_dossier.get("executive_summary", ""),
        "platforms": research_dossier.get("platforms", {}),
        "key_facts_and_insights": research_dossier.get("key_facts_and_insights", []),
        "content_gaps": research_dossier.get("content_gaps", []),
        "top_keywords": research_dossier.get("top_keywords", []),
    }

    system_prompt = (
        "You are Chief Content Strategist & Viral Creative Director. "
        "Transform live social media research into a sharp multi-platform master plan "
        "(YouTube, Instagram, Facebook) plus a tight scene-by-scene retention blueprint. "
        "CRITICAL RULE: NEVER use fake placeholder names like 'Tool A', 'Tool B', 'Tool C', 'App X', or 'Company Y'. "
        "Always name REAL, concrete tools, real strategies, and specific real-world examples grounded in the research!"
    )

    user_prompt = f"""
TOPIC: {topic}
FORMAT: {video_format} ({'Vertical Shorts/Reels/TikTok' if video_format == '9:16' else 'Horizontal YouTube Widescreen'})
TARGET DURATION: ~{duration_sec} seconds ({scene_count} scenes, ~{avg_sec}s each)
TARGET LANGUAGE: {language}
VISUAL STYLE: {visual_style}

RESEARCH DOSSIER:
{compact_research}

Return a JSON object with this EXACT schema:
{{
  "winning_angle": "The single sharpest, highest-retention angle chosen from the research",
  "target_audience": "Who this video speaks to and what emotion it triggers",
  "hook_strategy": "Exact psychological hook for the first 3 seconds",
  "thumbnail_concept": {{
    "headline": "Short 2-4 word punchy headline for cover/thumbnail",
    "subline": "Short 3-6 word curiosity subtext",
    "visual_direction": "Dramatic hero visual direction"
  }},
  "platform_playbooks": {{
    "youtube": {{"goal": "Retention & CTR strategy", "best_format": "Format tip", "cta": "Subscribe/Comment trigger"}},
    "instagram": {{"goal": "Saves & Shares strategy", "pacing_tip": "Pacing advice", "cta": "Save/Share trigger"}},
    "facebook": {{"goal": "Comments & Shareability strategy", "hook_twist": "Relatable opener", "cta": "Discussion question"}}
  }},
  "scene_blueprint": [
    {{
      "scene_number": 1,
      "role": "Hook",
      "target_seconds": {avg_sec},
      "beat_summary": "What happens and why viewer stays",
      "visual_mood": "Specific visual direction"
    }}
  ]
}}

Make sure `scene_blueprint` has EXACTLY {scene_count} scenes covering Hook -> Escalation -> Core Value/Proof -> Pro Tip/Twist -> Strong CTA.
"""

    plan, provider = await llm.generate_json(system_prompt, user_prompt, temperature=0.6, max_tokens=4200)
    plan["provider_used"] = provider
    log_fn(f"Strategist completed plan ({len(plan.get('scene_blueprint', []))} scenes for ~{duration_sec}s video).")
    return plan

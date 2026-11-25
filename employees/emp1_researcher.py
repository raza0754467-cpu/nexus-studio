import asyncio
from pathlib import Path
from typing import Any, Callable, Dict, List
from employees.browser_agent import run_live_browser_task
from employees.llm_router import MultiProviderLLM
from employees.seo_engine import run_million_search_seo


def _run_ddg_research(topic: str) -> Dict[str, List[Dict[str, str]]]:
    results: Dict[str, List[Dict[str, str]]] = {
        "youtube": [],
        "instagram": [],
        "facebook": [],
        "web_trends": [],
    }

    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # type: ignore
        except ImportError:
            return results

    queries = [
        ("youtube", f"{topic} viral trending video site:youtube.com", 6),
        ("instagram", f"{topic} viral reels trend site:instagram.com", 5),
        ("facebook", f"{topic} viral post video site:facebook.com", 5),
        ("web_trends", f"{topic} latest trends facts insights 2026", 6),
    ]

    with DDGS() as ddgs:
        try:
            vids = list(ddgs.videos(topic, max_results=6))
            for v in vids:
                results["youtube"].append(
                    {
                        "title": str(v.get("title", ""))[:160],
                        "snippet": str(v.get("description", ""))[:240],
                        "url": str(v.get("content", v.get("url", ""))),
                        "meta": f"{v.get('publisher', 'YouTube')} • {v.get('duration', '')}".strip(" •"),
                    }
                )
        except Exception:
            pass

        for bucket, q, limit in queries:
            try:
                hits = list(ddgs.text(q, max_results=limit))
                for h in hits:
                    results[bucket].append(
                        {
                            "title": str(h.get("title", ""))[:160],
                            "snippet": str(h.get("body", ""))[:260],
                            "url": str(h.get("href", "")),
                            "meta": bucket.upper(),
                        }
                    )
            except Exception:
                pass

    return results


async def run_researcher(
    topic: str,
    language: str,
    project_dir: Path,
    use_live_browser: bool,
    visible_browser: bool,
    llm: MultiProviderLLM,
    log_fn: Callable[[str], None],
) -> Dict[str, Any]:
    log_fn("Employee 1 (Researcher) scanning YouTube, Instagram, Facebook, Google SEO & Web...")
    raw_data, seo_intel = await asyncio.gather(
        asyncio.to_thread(_run_ddg_research, topic),
        run_million_search_seo(topic, geo="PK", log_fn=log_fn),
    )

    browser_shots: List[Dict[str, str]] = []
    if use_live_browser:
        log_fn("Employee 1 activating Live Browser Agent on YouTube...")
        shots_dir = project_dir / "browser_shots"
        b_res = await run_live_browser_task(
            url_or_query=topic,
            save_dir=shots_dir,
            mode="youtube",
            visible=visible_browser,
            log_fn=log_fn,
        )
        browser_shots = b_res.get("screenshots", [])
        for item in b_res.get("items", [])[:8]:
            raw_data["youtube"].insert(
                0,
                {
                    "title": item.get("title", ""),
                    "snippet": f"{item.get('channel', '')} — {item.get('meta', '')}".strip(" —"),
                    "url": item.get("url", ""),
                    "meta": "LIVE BROWSER YOUTUBE",
                },
            )

    total_signals = sum(len(v) for v in raw_data.values())
    log_fn(
        f"Collected {total_signals} signals "
        f"(YouTube: {len(raw_data['youtube'])}, Instagram: {len(raw_data['instagram'])}, "
        f"Facebook: {len(raw_data['facebook'])}, Web: {len(raw_data['web_trends'])})"
    )

    system_prompt = (
        "You are Employee 1: Elite Social Media Intelligence Researcher. "
        "You analyze real YouTube, Instagram, Facebook, and web trend data to uncover what actually gets views, "
        "watch-time, shares, and comments. Be sharp, specific, and avoid generic filler."
    )

    user_prompt = f"""
TOPIC: {topic}
TARGET LANGUAGE: {language}

COLLECTED LIVE SIGNALS:
- YouTube: {raw_data['youtube'][:8]}
- Instagram: {raw_data['instagram'][:6]}
- Facebook: {raw_data['facebook'][:6]}
- Web/News: {raw_data['web_trends'][:6]}
- Live Million-Search Google Keywords: {seo_intel.get('google_autocomplete', [])[:10]}
- Live Million-Search YouTube Keywords: {seo_intel.get('youtube_autocomplete', [])[:10]}
- High-Intent Audience Questions: {seo_intel.get('high_intent_questions', [])[:8]}

Produce a deep, structured Social Media Research Dossier in this EXACT JSON format:
{{
  "executive_summary": "3-4 crisp sentences summarizing what is trending right now across YT, IG, FB for this topic",
  "platforms": {{
    "youtube": {{
      "trending_angles": ["specific angle 1", "specific angle 2", "specific angle 3"],
      "viral_title_patterns": ["high-CTR title formula 1", "high-CTR title formula 2"],
      "audience_curiosity": "Exact curiosity gap driving YouTube clicks right now"
    }},
    "instagram": {{
      "trending_angles": ["reel angle 1", "reel angle 2", "reel angle 3"],
      "reel_hooks": ["3-sec hook 1", "3-sec hook 2"],
      "visual_vibe": "Exact fast-cut / visual pacing working on Reels"
    }},
    "facebook": {{
      "trending_angles": ["shareable angle 1", "shareable angle 2", "shareable angle 3"],
      "share_triggers": ["why people share/comment 1", "why people share/comment 2"],
      "discussion_angle": "Debate or relatable question driving comments on Facebook"
    }}
  }},
  "key_facts_and_insights": ["concrete fact 1", "concrete fact 2", "concrete fact 3", "concrete fact 4", "concrete fact 5"],
  "content_gaps": ["untapped winning angle 1", "untapped winning angle 2", "untapped winning angle 3"],
  "top_keywords": ["kw1", "kw2", "kw3", "kw4", "kw5", "kw6"]
}}
"""

    dossier, provider = await llm.generate_json(system_prompt, user_prompt, temperature=0.55)
    dossier["raw_sources"] = raw_data
    dossier["seo_intelligence"] = seo_intel
    dossier["browser_screenshots"] = browser_shots
    dossier["total_signals"] = total_signals
    dossier["provider_used"] = provider
    log_fn(f"Employee 1 completed Research Dossier using {provider.upper()}.")
    return dossier

import asyncio
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List
import httpx

ROMAN_URDU_STOPWORDS = {
    "ke", "ki", "ka", "ko", "se", "sy", "me", "mein", "par", "py", "pe", "hai", "hain", "ho",
    "kya", "kia", "kaise", "kesy", "kese", "aur", "or", "jo", "wo", "ye", "ya", "ap", "aap",
    "hum", "hm", "bhi", "sab", "sb", "bahut", "bhot", "liye", "laiy", "banao", "bnana", "wala", "wali",
}


def _extract_core_search_queries(topic: str) -> List[str]:
    """
    Converts Roman Urdu / conversational long topics (e.g. '2026 ke best AI tools')
    into clean high-hit search seeds ('best AI tools 2026', 'best AI tools', 'AI tools')
    so Google & YouTube Autocomplete ALWAYS return real high-volume search phrases!
    """
    raw = topic.strip()
    tokens = [re.sub(r"[^a-zA-Z0-9+]", "", w) for w in raw.split()]
    clean = [w for w in tokens if w and w.lower() not in ROMAN_URDU_STOPWORDS]
    years = [w for w in clean if re.fullmatch(r"20\d{2}", w)]
    non_years = [w for w in clean if w not in years]

    seeds: List[str] = [raw]
    if non_years:
        core = " ".join(non_years[:4])
        seeds.append(core)
        if years:
            seeds.append(f"{core} {years[0]}")
        if len(non_years) >= 2:
            seeds.append(" ".join(non_years[-2:]))
            seeds.append(" ".join(non_years[:2]))

    # Dedupe preserving order
    seen = set()
    out = []
    for s in seeds:
        k = s.lower().strip()
        if k and k not in seen:
            seen.add(k)
            out.append(s.strip())
    return out[:5]


async def _fetch_autocomplete(client: httpx.AsyncClient, query: str, engine: str = "google") -> List[str]:
    q = urllib.parse.quote_plus(query.strip())
    if engine == "youtube":
        url = f"https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q={q}"
    else:
        url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={q}"
    try:
        r = await client.get(url, timeout=10.0)
        if r.status_code == 200:
            data = json.loads(r.text)
            if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
                return [str(item).strip() for item in data[1] if str(item).strip()]
    except Exception:
        pass
    return []


async def fetch_google_trends_rss(geo: str = "PK") -> List[Dict[str, str]]:
    geo_clean = re.sub(r"[^A-Z]", "", geo.upper()) or "PK"
    urls = [
        f"https://trends.google.com/trending/rss?geo={geo_clean}",
        f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo_clean}",
    ]
    trends: List[Dict[str, str]] = []
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for url in urls:
            try:
                r = await client.get(url)
                if r.status_code != 200 or "<item" not in r.text:
                    continue
                root = ET.fromstring(r.text)
                for item in root.findall(".//item")[:16]:
                    title = (item.findtext("title") or "").strip()
                    traffic = ""
                    for child in item:
                        if child.tag.endswith("approx_traffic") and child.text:
                            traffic = child.text.strip()
                    pub = (item.findtext("pubDate") or "").strip()
                    if title:
                        trends.append({"topic": title, "traffic": traffic or "Trending", "published": pub[:22]})
                if trends:
                    break
            except Exception:
                continue
    return trends


async def run_million_search_seo(
    topic: str,
    geo: str = "PK",
    log_fn: Callable[[str], None] = lambda m: None,
) -> Dict[str, Any]:
    log_fn(f"Scanning live Google & YouTube search demand for '{topic}'...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0"}
    seeds = _extract_core_search_queries(topic)
    primary = seeds[1] if len(seeds) > 1 else seeds[0]

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        tasks = [
            _fetch_autocomplete(client, seeds[0], "google"),
            _fetch_autocomplete(client, seeds[0], "youtube"),
            _fetch_autocomplete(client, primary, "google"),
            _fetch_autocomplete(client, primary, "youtube"),
            _fetch_autocomplete(client, f"best {primary}", "youtube"),
            _fetch_autocomplete(client, f"how to {primary}", "youtube"),
            _fetch_autocomplete(client, f"{primary} 2026", "google"),
            fetch_google_trends_rss(geo),
        ]
        g0, yt0, g1, yt1, yt_best, yt_how, g_2026, daily_trends = await asyncio.gather(*tasks)

        # Extra fallback on shortest seed if still sparse
        if len(g0 + g1) < 3 and len(seeds) >= 3:
            g_extra, yt_extra = await asyncio.gather(
                _fetch_autocomplete(client, seeds[-1], "google"),
                _fetch_autocomplete(client, seeds[-1], "youtube"),
            )
            g1 = g1 + g_extra
            yt1 = yt1 + yt_extra

    def _dedupe(items: List[str]) -> List[str]:
        seen = set()
        out = []
        for it in items:
            k = it.lower().strip()
            if k and k not in seen:
                seen.add(k)
                out.append(it.strip())
        return out

    google_keywords = _dedupe(g0 + g1 + g_2026)[:18]
    youtube_keywords = _dedupe(yt0 + yt1 + yt_best + yt_how)[:18]
    question_keywords = _dedupe(
        [k for k in (yt_how + g1 + yt1 + yt_best) if any(w in k.lower() for w in ("how", "what", "why", "best", "kaise", "kya", "free", "top"))]
    )[:12]

    all_unique = _dedupe(youtube_keywords + google_keywords)
    demand_score = min(99, max(62, 54 + len(all_unique) * 2))

    niche_tags = [f"#{''.join(re.sub(r'[^a-zA-Z0-9]', '', p) for p in kw.split()[:3])}" for kw in all_unique[:8]]
    niche_tags = [t for t in _dedupe(niche_tags) if 3 < len(t) <= 28][:8]

    log_fn(f"Extracted {len(google_keywords)} Google + {len(youtube_keywords)} YouTube live search terms (Demand Score: {demand_score}/100).")

    return {
        "topic": topic,
        "geo": geo,
        "demand_score": demand_score,
        "google_autocomplete": google_keywords,
        "youtube_autocomplete": youtube_keywords,
        "high_intent_questions": question_keywords,
        "daily_breakout_trends": daily_trends[:12],
        "recommended_hashtags": niche_tags,
        "seed_terms": seeds,
    }

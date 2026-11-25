import asyncio
import time
import urllib.parse
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional
from employees.llm_router import MultiProviderLLM

EventCallback = Callable[[Dict[str, Any]], Awaitable[None]]


async def run_live_browser_task(
    url_or_query: str,
    save_dir: Path,
    mode: str = "auto",
    visible: bool = False,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Fast single-target Live Chromium capture for Employee 1."""
    log = log_fn or (lambda m: None)
    save_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"ok": False, "error": "Browser runtime not ready.", "screenshots": [], "items": [], "page_text": ""}

    target = url_or_query.strip()
    is_url = target.startswith("http://") or target.startswith("https://")
    if mode == "youtube" and not is_url:
        target_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(target)}"
    elif is_url:
        target_url = target
    else:
        target_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(target)}"

    screenshots: List[Dict[str, str]] = []
    extracted_items: List[Dict[str, str]] = []
    page_title = ""
    page_text = ""

    log(f"Opening live browser -> {target_url}")

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=not visible,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            await page.goto(target_url, wait_until="domcontentloaded", timeout=28000)
            await asyncio.sleep(2.0)

            for label in ["Accept all", "Reject all", "I agree", "Got it"]:
                try:
                    btn = page.get_by_role("button", name=label).first
                    if await btn.is_visible(timeout=350):
                        await btn.click(timeout=900)
                        await asyncio.sleep(0.5)
                        break
                except Exception:
                    pass

            page_title = await page.title()
            ts = int(time.time() * 1000)

            shot1 = f"browser_{ts}_top.png"
            await page.screenshot(path=str(save_dir / shot1), full_page=False)
            screenshots.append({"filename": shot1, "caption": f"{page_title[:56]}", "url": page.url})

            await page.evaluate("window.scrollBy(0, 680)")
            await asyncio.sleep(1.1)

            shot2 = f"browser_{ts}_scroll.png"
            await page.screenshot(path=str(save_dir / shot2), full_page=False)
            screenshots.append({"filename": shot2, "caption": "Scrolled Feed", "url": page.url})

            if "youtube.com" in page.url:
                extracted_items = await page.evaluate(
                    """() => {
                        const out = [];
                        for (const el of document.querySelectorAll('ytd-video-renderer, ytd-reel-item-renderer')) {
                            const t = el.querySelector('#video-title');
                            const c = el.querySelector('#channel-name, ytd-channel-name');
                            const m = el.querySelector('#metadata-line');
                            if (t && t.textContent) {
                                out.push({
                                    title: t.textContent.trim().slice(0, 160),
                                    channel: c ? c.textContent.trim().slice(0, 80) : '',
                                    meta: m ? m.textContent.replace(/\\s+/g, ' ').trim().slice(0, 120) : '',
                                    url: t.href || ''
                                });
                            }
                            if (out.length >= 12) break;
                        }
                        return out;
                    }"""
                )
            else:
                generic = await page.evaluate(
                    """() => {
                        const links = [];
                        const seen = new Set();
                        for (const a of document.querySelectorAll('a[href]')) {
                            const txt = (a.innerText || '').replace(/\\s+/g, ' ').trim();
                            const href = a.href || '';
                            if (txt.length >= 18 && href.startsWith('http') && !seen.has(txt)) {
                                seen.add(txt);
                                links.push({ title: txt.slice(0, 150), url: href, meta: '' });
                            }
                            if (links.length >= 15) break;
                        }
                        return {
                            links,
                            text: (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ').trim().slice(0, 4000)
                        };
                    }"""
                )
                extracted_items = generic.get("links", [])
                page_text = generic.get("text", "")

            if not page_text:
                page_text = await page.evaluate(
                    "() => (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ').trim().slice(0, 3500)"
                )

            if visible:
                await asyncio.sleep(1.2)
            await browser.close()

        return {
            "ok": True,
            "url": target_url,
            "title": page_title,
            "screenshots": screenshots,
            "items": extracted_items,
            "page_text": page_text[:3000],
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": target_url,
            "error": str(exc)[:240],
            "screenshots": screenshots,
            "items": extracted_items,
            "page_text": page_text,
        }


async def run_autonomous_browser_agent(
    goal: str,
    start_url: str,
    save_dir: Path,
    llm: MultiProviderLLM,
    max_steps: int = 5,
    visible: bool = False,
    log_fn: Optional[Callable[[str], None]] = None,
    on_event: Optional[EventCallback] = None,
    media_prefix: str = "/media/browser",
) -> Dict[str, Any]:
    """
    REAL-TIME STREAMING Multi-Step Autonomous Browser Agent!
    Streams live URL, live screenshot frames, and step-by-step actions to the side Browser Pane as it works.
    """
    log = log_fn or (lambda m: None)
    save_dir.mkdir(parents=True, exist_ok=True)

    async def emit(ev: Dict[str, Any]) -> None:
        if on_event:
            await on_event(ev)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"ok": False, "error": "Browser runtime not ready.", "steps": [], "screenshots": [], "summary": ""}

    # Pick smart starting URL directly so step 1 is already rich & fast!
    initial_url = start_url.strip()
    if not initial_url:
        gl = goal.lower()
        if any(w in gl for w in ("youtube", "yt ", "video", "reel", "short")):
            clean_q = urllib.parse.quote_plus(goal[:100])
            initial_url = f"https://www.youtube.com/results?search_query={clean_q}"
        elif "github" in gl:
            initial_url = "https://github.com/trending"
        else:
            clean_q = urllib.parse.quote_plus(goal[:100])
            initial_url = f"https://html.duckduckgo.com/html/?q={clean_q}"
    elif not (initial_url.startswith("http://") or initial_url.startswith("https://")):
        initial_url = "https://" + initial_url

    steps_log: List[Dict[str, Any]] = []
    screenshots: List[Dict[str, str]] = []
    final_summary = ""
    extracted_items: List[Dict[str, str]] = []

    await emit({"type": "browser_open", "url": initial_url, "status": "Launching live browser..."})
    log(f"Browser Agent opening -> {initial_url}")

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=not visible,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 820},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            await emit({"type": "browser_step", "step": 0, "action": "navigate", "url": initial_url, "detail": f"Opening {initial_url}"})
            await page.goto(initial_url, wait_until="domcontentloaded", timeout=26000)
            await asyncio.sleep(1.8)

            # Soft cookie dismiss
            for label in ["Accept all", "Reject all", "I agree", "Got it"]:
                try:
                    btn = page.get_by_role("button", name=label).first
                    if await btn.is_visible(timeout=350):
                        await btn.click(timeout=900)
                        await asyncio.sleep(0.5)
                        break
                except Exception:
                    pass

            for step_idx in range(1, max_steps + 1):
                obs = await page.evaluate(
                    """() => {
                        const els = [];
                        let idx = 1;
                        const selector = 'a[href], button, input, textarea, [role="button"], [role="searchbox"], ytd-video-renderer #video-title';
                        for (const el of document.querySelectorAll(selector)) {
                            const rect = el.getBoundingClientRect();
                            if (rect.width < 10 || rect.height < 10 || rect.top < -40 || rect.top > 900) continue;
                            const style = window.getComputedStyle(el);
                            if (style.visibility === 'hidden' || style.display === 'none') continue;
                            const tag = el.tagName.toLowerCase();
                            const text = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title') || '').replace(/\\s+/g, ' ').trim();
                            if (!text && tag !== 'input' && tag !== 'textarea') continue;
                            el.setAttribute('data-nx-id', String(idx));
                            els.push({
                                id: idx,
                                tag,
                                text: text.slice(0, 95),
                                href: (el.href || '').slice(0, 120)
                            });
                            idx++;
                            if (idx > 40) break;
                        }
                        const bodyText = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ').trim();
                        return {
                            url: location.href,
                            title: document.title,
                            elements: els,
                            text: bodyText.slice(0, 2800),
                            hasCaptcha: /captcha|verify you are human|unusual traffic|robot check/i.test(bodyText.slice(0, 1400))
                        };
                    }"""
                )

                ts = int(time.time() * 1000)
                shot_name = f"agent_{ts}_s{step_idx}.png"
                await page.screenshot(path=str(save_dir / shot_name), full_page=False)
                shot_url = f"{media_prefix}/{shot_name}"
                shot_meta = {
                    "filename": shot_name,
                    "media_url": shot_url,
                    "caption": f"Step {step_idx}: {obs.get('title', '')[:48]}",
                    "url": obs.get("url", ""),
                }
                screenshots.append(shot_meta)

                # Stream live frame to side browser pane immediately!
                await emit(
                    {
                        "type": "browser_frame",
                        "step": step_idx,
                        "url": obs.get("url", ""),
                        "title": obs.get("title", ""),
                        "screenshot": shot_url,
                        "status": f"Analyzing page ({obs.get('title', '')[:38]})...",
                    }
                )

                if obs.get("hasCaptcha"):
                    final_summary = (
                        f"Stopped safely at Step {step_idx}: this website requested a human verification / CAPTCHA check. "
                        "You can complete verification directly in Visible Browser mode or try another source."
                    )
                    steps_log.append({"step": step_idx, "action": "blocked", "detail": final_summary, "screenshot": shot_url})
                    await emit({"type": "browser_step", "step": step_idx, "action": "paused", "detail": final_summary, "screenshot": shot_url})
                    break

                history_brief = [{"step": s["step"], "action": s["action"], "detail": s["detail"][:100]} for s in steps_log]
                sys_prompt = (
                    "You are an autonomous live web researcher controlling a real browser. "
                    "Analyze the current URL, visible elements, and page text to achieve the user's goal quickly and accurately. "
                    "Once you have enough real information on screen to answer thoroughly, choose action='done' and write a crisp, well-structured answer in the user's language (Roman Urdu / Urdu / English). "
                    "Never attempt to solve CAPTCHAs or bypass logins. Return ONLY valid JSON."
                )
                usr_prompt = f"""
GOAL: {goal}
STEP: {step_idx} of {max_steps}
CURRENT URL: {obs.get('url')}
PAGE TITLE: {obs.get('title')}
PREVIOUS STEPS: {history_brief}

VISIBLE INTERACTIVE ELEMENTS:
{obs.get('elements', [])[:32]}

VISIBLE PAGE TEXT:
{obs.get('text', '')[:2000]}

Return JSON with this EXACT schema:
{{
  "thought": "Brief 1-sentence reasoning",
  "action": "goto" | "click" | "type" | "scroll" | "wait" | "done",
  "url": "https:// URL if action==goto",
  "element_id": 0,
  "text": "text to type if action==type",
  "press_enter": true,
  "direction": "down" | "up",
  "summary": "If action==done, write a rich, helpful, accurate final answer in the user's language citing real titles/facts seen on the page!"
}}
"""
                try:
                    decision, _ = await llm.generate_json(sys_prompt, usr_prompt, temperature=0.2, max_tokens=1400)
                except Exception:
                    # Bulletproof recovery: never crash with JSON parse error! Summarize visible page cleanly.
                    fallback_sum, _ = await llm.generate(
                        "You are NEXUS, a helpful live web researcher. Summarize what was found on this webpage cleanly in the user's language. Never mention JSON or backend providers.",
                        f"User goal: {goal}\nPage: {obs.get('title')} ({obs.get('url')})\nVisible text:\n{obs.get('text', '')[:2200]}",
                        temperature=0.4,
                        max_tokens=900,
                    )
                    decision = {"action": "done", "thought": "Summarizing visible page", "summary": fallback_sum}

                act = str(decision.get("action", "done")).lower()
                thought = str(decision.get("thought", ""))

                if act == "done" or step_idx == max_steps:
                    final_summary = decision.get("summary") or thought or obs.get("text", "")[:700]
                    for el in obs.get("elements", [])[:12]:
                        if el.get("href") and len(el.get("text", "")) > 10:
                            extracted_items.append({"title": el["text"], "url": el["href"], "meta": el["tag"]})
                    steps_log.append({"step": step_idx, "action": "done", "detail": "Extracted findings & finished.", "screenshot": shot_url})
                    await emit({"type": "browser_step", "step": step_idx, "action": "done", "detail": "Research complete", "screenshot": shot_url})
                    break

                detail = thought
                try:
                    if act == "goto" and decision.get("url"):
                        u = str(decision["url"]).strip()
                        if not u.startswith("http"):
                            u = "https://" + u
                        detail = f"Opening {u}"
                        await emit({"type": "browser_step", "step": step_idx, "action": "goto", "url": u, "detail": detail})
                        await page.goto(u, wait_until="domcontentloaded", timeout=24000)
                        await asyncio.sleep(1.7)

                    elif act == "click" and decision.get("element_id"):
                        eid = int(decision["element_id"])
                        detail = f"Clicking item #{eid}: {thought[:55]}"
                        await emit({"type": "browser_step", "step": step_idx, "action": "click", "detail": detail})
                        loc = page.locator(f'[data-nx-id="{eid}"]').first
                        await loc.scroll_into_view_if_needed(timeout=4000)
                        await loc.click(timeout=6000)
                        await asyncio.sleep(1.7)

                    elif act == "type" and decision.get("element_id"):
                        eid = int(decision["element_id"])
                        txt = str(decision.get("text", ""))
                        detail = f"Searching '{txt}'"
                        await emit({"type": "browser_step", "step": step_idx, "action": "type", "detail": detail})
                        loc = page.locator(f'[data-nx-id="{eid}"]').first
                        await loc.click(timeout=5000)
                        await loc.fill(txt, timeout=5000)
                        if decision.get("press_enter", True):
                            await page.keyboard.press("Enter")
                        await asyncio.sleep(2.0)

                    elif act == "scroll":
                        delta = 720 if decision.get("direction", "down") == "down" else -720
                        detail = f"Scrolling {decision.get('direction', 'down')}"
                        await emit({"type": "browser_step", "step": step_idx, "action": "scroll", "detail": detail})
                        await page.evaluate(f"window.scrollBy(0, {delta})")
                        await asyncio.sleep(1.1)

                    elif act == "wait":
                        detail = "Waiting for page content"
                        await asyncio.sleep(1.8)
                except Exception as act_err:
                    detail = f"Adjusted step: {str(act_err)[:90]}"

                steps_log.append({"step": step_idx, "action": act, "detail": detail, "screenshot": shot_url})

            if visible:
                await asyncio.sleep(1.5)
            await browser.close()

        return {
            "ok": True,
            "goal": goal,
            "summary": final_summary,
            "steps": steps_log,
            "screenshots": screenshots,
            "items": extracted_items,
        }
    except Exception as exc:
        err = f"Browser encountered an error: {str(exc)[:180]}"
        await emit({"type": "browser_step", "step": 0, "action": "error", "detail": err})
        return {
            "ok": False,
            "goal": goal,
            "error": str(exc)[:240],
            "summary": err,
            "steps": steps_log,
            "screenshots": screenshots,
            "items": extracted_items,
        }

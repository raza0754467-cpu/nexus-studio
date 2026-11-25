import asyncio
import math
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Rate-limit spacer for Pollinations anonymous endpoint so multi-scene AI images succeed reliably
_LAST_POLLINATIONS_CALL = 0.0

WATERMARKED_DOMAINS = (
    "shutterstock",
    "gettyimages",
    "alamy",
    "istockphoto",
    "istock",
    "dreamstime",
    "123rf",
    "depositphotos",
    "vecteezy",
    "pngtree",
    "freepik",
    "stock.adobe",
    "ftcdn.net",
    "canstockphoto",
    "bigstockphoto",
    "pond5",
    "vectorstock",
    "megapixl",
    "colourbox",
    "envato",
    "dribbble.com",
    "cdn.dribbble",
    "behance.net",
    "mir-s3-cdn-cf.behance",
    "ui8.net",
    "pinterest",
    "pinimg",
    "canva.com",
    "figma.com",
    "watermark",
    "mockup",
)

PREFERRED_CLEAN_DOMAINS = (
    "images.unsplash.com",
    "images.pexels.com",
    "cdn.pixabay.com",
    "upload.wikimedia.org",
    "images.stockcake.com",
)

# 38 Expressive, Natural Human-Like Neural Voices Across 16 Global Languages (Free & Unlimited!)
VOICE_PRESETS: Dict[str, Dict[str, str]] = {
    # --- English (Global US / UK / AU) ---
    "en_ava_multi": {"id": "en-US-AvaMultilingualNeural", "label": "Ava — Ultra-Natural Expressive Female (US)", "group": "English", "rate": "+2%", "pitch": "+0Hz", "sample": "Here is the one creative breakthrough that keeps viewers watching until the very last second."},
    "en_andrew_multi": {"id": "en-US-AndrewMultilingualNeural", "label": "Andrew — Warm Storyteller Male (US)", "group": "English", "rate": "+1%", "pitch": "+0Hz", "sample": "Most creators spend ten hours editing when a five-agent studio finishes in minutes."},
    "en_emma_multi": {"id": "en-US-EmmaMultilingualNeural", "label": "Emma — Friendly Creator Female (US)", "group": "English", "rate": "+3%", "pitch": "+0Hz", "sample": "Stop scrolling for three seconds, because this changes everything about creating viral videos."},
    "en_brian_multi": {"id": "en-US-BrianMultilingualNeural", "label": "Brian — Documentary Narrator Male (US)", "group": "English", "rate": "-2%", "pitch": "-2Hz", "sample": "Behind every unforgettable story is clear pacing, natural voice, and intentional visuals."},
    "en_guy_viral": {"id": "en-US-GuyNeural", "label": "Marcus — High-Energy YouTube Male (US)", "group": "English", "rate": "+6%", "pitch": "+1Hz", "sample": "Wait until you see step number three — almost nobody knows this trick exists!"},
    "en_aria_warm": {"id": "en-US-AriaNeural", "label": "Aria — Smooth Podcast Female (US)", "group": "English", "rate": "+0%", "pitch": "+0Hz", "sample": "Welcome back. Today we are exploring the tools redefining modern digital creativity."},
    "en_ryan_uk": {"id": "en-GB-RyanNeural", "label": "Ryan — British Luxury Male (UK)", "group": "English", "rate": "+0%", "pitch": "+0Hz", "sample": "Simplicity is the ultimate sophistication when designing visuals for a global audience."},
    "en_sonia_uk": {"id": "en-GB-SoniaNeural", "label": "Sonia — British Editorial Female (UK)", "group": "English", "rate": "+1%", "pitch": "+0Hz", "sample": "Let us break down the exact three principles driving millions of views worldwide."},
    "en_natasha_au": {"id": "en-AU-NatashaNeural", "label": "Natasha — Crisp Australian Female (AU)", "group": "English", "rate": "+2%", "pitch": "+0Hz", "sample": "Creators across every timezone are turning single prompts into cinema-ready videos."},
    "en_william_au": {"id": "en-AU-WilliamNeural", "label": "William — Natural Australian Male (AU)", "group": "English", "rate": "+0%", "pitch": "-1Hz", "sample": "Great storytelling speaks every language when your pacing and captions stay effortless."},
    # --- Urdu (Pakistan & India) ---
    "urdu_female_noor": {"id": "ur-PK-UzmaNeural", "label": "Noor — Warm Natural Urdu Female (PK)", "group": "Urdu", "rate": "+2%", "pitch": "+2Hz", "sample": "Assalam-o-Alaikum! Kya aap apni videos ke liye bilkul natural aur realistic voice banana chahte hain?"},
    "urdu_female_aisha": {"id": "ur-PK-UzmaNeural", "label": "Aisha — Calm Storytelling Urdu Female (PK)", "group": "Urdu", "rate": "-4%", "pitch": "-2Hz", "sample": "Aaj hum ek aise secret ke baare mein baat karenge jo aapki content creation badal dega."},
    "urdu_female_zoya": {"id": "ur-IN-GulNeural", "label": "Zoya — Soft Expressive Urdu Female (IN)", "group": "Urdu", "rate": "+0%", "pitch": "+0Hz", "sample": "Ab aapki professional viral video kuch hi lamhon mein tayyar hai."},
    "urdu_male_asad": {"id": "ur-PK-AsadNeural", "label": "Asad — Deep Documentary Urdu Male (PK)", "group": "Urdu", "rate": "+1%", "pitch": "-2Hz", "sample": "Kya aap jante hain ke AI studio ab poore production team ka kaam minutes mein kar sakta hai?"},
    "urdu_male_zain": {"id": "ur-PK-AsadNeural", "label": "Zain — Energetic Viral Reels Male (PK)", "group": "Urdu", "rate": "+8%", "pitch": "+3Hz", "sample": "Ruko! Ye 3 secrets dekhe baghair apni agli video bilkul upload mat karna!"},
    "urdu_male_salman": {"id": "ur-IN-SalmanNeural", "label": "Salman — Classic Narrator Urdu Male (IN)", "group": "Urdu", "rate": "-2%", "pitch": "-2Hz", "sample": "Har kamyab creator ke peeche ek zabardast story aur sahi editing hoti hai."},
    # --- Hindi (India) ---
    "hindi_female_ananya": {"id": "hi-IN-SwaraNeural", "label": "Ananya — Warm Natural Hindi Female (IN)", "group": "Hindi", "rate": "+2%", "pitch": "+0Hz", "sample": "Namaste! Aaj main aapko dikhaungi ki aap kuch hi minutes mein pro level video kaise bana sakte hain."},
    "hindi_male_aarav": {"id": "hi-IN-MadhurNeural", "label": "Aarav — Deep Storytelling Hindi Male (IN)", "group": "Hindi", "rate": "+0%", "pitch": "-2Hz", "sample": "Duniya badal rahi hai, aur aaj ke sabse smart creators AI ko apni team bana rahe hain."},
    # --- Arabic (Saudi, UAE, Egypt) ---
    "ar_zariyah_sa": {"id": "ar-SA-ZariyahNeural", "label": "Zariyah — Warm Arabic Female (Saudi)", "group": "Arabic", "rate": "+1%", "pitch": "+0Hz", "sample": "مرحباً بكم! اكتشفوا كيف تصنعون فيديوهات احترافية في دقائق معدودة."},
    "ar_hamed_sa": {"id": "ar-SA-HamedNeural", "label": "Hamed — Deep Arabic Male (Saudi)", "group": "Arabic", "rate": "+0%", "pitch": "-1Hz", "sample": "الإبداع الحقيقي يبدأ بفكرة واضحة وإخراج بصري مذهل."},
    "ar_fatima_ae": {"id": "ar-AE-FatimaNeural", "label": "Fatima — Modern Gulf Female (UAE)", "group": "Arabic", "rate": "+2%", "pitch": "+0Hz", "sample": "أهلاً بكم في عالم صناعة المحتوى الذكي بجودة سينمائية عالية."},
    "ar_salma_eg": {"id": "ar-EG-SalmaNeural", "label": "Salma — Expressive Arabic Female (Egypt)", "group": "Arabic", "rate": "+1%", "pitch": "+0Hz", "sample": "النهاردة هنشوف إزاي تعمل فيديو احترافي يجذب ملايين المشاهدات."},
    # --- Spanish (Mexico & Spain) ---
    "es_dalia_mx": {"id": "es-MX-DaliaNeural", "label": "Dalia — Expressive Spanish Female (MX)", "group": "Spanish", "rate": "+2%", "pitch": "+0Hz", "sample": "Descubre cómo crear videos virales con calidad de estudio en cuestión de minutos."},
    "es_jorge_mx": {"id": "es-MX-JorgeNeural", "label": "Jorge — Dynamic Spanish Male (MX)", "group": "Spanish", "rate": "+1%", "pitch": "+0Hz", "sample": "El secreto de los videos que retienen a la audiencia está en los primeros tres segundos."},
    "es_elvira_es": {"id": "es-ES-ElviraNeural", "label": "Elvira — Editorial Spanish Female (ES)", "group": "Spanish", "rate": "+0%", "pitch": "+0Hz", "sample": "Transforma cualquier idea en una producción audiovisual lista para publicar."},
    "es_alvaro_es": {"id": "es-ES-AlvaroNeural", "label": "Alvaro — Documentary Spanish Male (ES)", "group": "Spanish", "rate": "+0%", "pitch": "-1Hz", "sample": "La nueva generación de creadores combina velocidad, guion y diseño visual impecable."},
    # --- French (France) ---
    "fr_denise": {"id": "fr-FR-DeniseNeural", "label": "Denise — Natural French Female (FR)", "group": "French", "rate": "+1%", "pitch": "+0Hz", "sample": "Créez des vidéos captivantes avec une voix naturelle et des sous-titres animés."},
    "fr_henri": {"id": "fr-FR-HenriNeural", "label": "Henri — Cinema French Male (FR)", "group": "French", "rate": "+0%", "pitch": "-1Hz", "sample": "Voici comment transformer une simple idée en vidéo professionnelle en quelques instants."},
    # --- German (Germany) ---
    "de_katja": {"id": "de-DE-KatjaNeural", "label": "Katja — Clear German Female (DE)", "group": "German", "rate": "+1%", "pitch": "+0Hz", "sample": "Entdecke, wie du in wenigen Minuten professionelle Videos für jede Plattform erstellst."},
    "de_conrad": {"id": "de-DE-ConradNeural", "label": "Conrad — Documentary German Male (DE)", "group": "German", "rate": "+0%", "pitch": "-1Hz", "sample": "Starke Geschichten brauchen Tempo, klare Stimmen und präzise visuelle Führung."},
    # --- Portuguese (Brazil) ---
    "pt_francisca_br": {"id": "pt-BR-FranciscaNeural", "label": "Francisca — Vibrant Portuguese Female (BR)", "group": "Portuguese", "rate": "+2%", "pitch": "+0Hz", "sample": "Transforme suas ideias em vídeos virais prontos para YouTube, Reels e TikTok."},
    "pt_antonio_br": {"id": "pt-BR-AntonioNeural", "label": "Antonio — Smooth Portuguese Male (BR)", "group": "Portuguese", "rate": "+1%", "pitch": "-1Hz", "sample": "Com roteiro inteligente e legendas sincronizadas, seu conteúdo se destaca no primeiro segundo."},
    # --- Turkish ---
    "tr_emel": {"id": "tr-TR-EmelNeural", "label": "Emel — Natural Turkish Female (TR)", "group": "Turkish", "rate": "+1%", "pitch": "+0Hz", "sample": "Dakikalar içinde profesyonel seslendirme ve animasyonlu altyazılı videolar oluşturun."},
    "tr_ahmet": {"id": "tr-TR-AhmetNeural", "label": "Ahmet — Strong Turkish Male (TR)", "group": "Turkish", "rate": "+0%", "pitch": "-1Hz", "sample": "Milyonlarca izlenen videoların sırrı doğru hikaye ve akıcı kurgudur."},
    # --- Indonesian ---
    "id_gadis": {"id": "id-ID-GadisNeural", "label": "Gadis — Natural Indonesian Female (ID)", "group": "Indonesian", "rate": "+2%", "pitch": "+0Hz", "sample": "Buat video viral berkualitas studio dengan suara alami dan teks animasi dalam hitungan menit."},
    "id_ardi": {"id": "id-ID-ArdiNeural", "label": "Ardi — Narrator Indonesian Male (ID)", "group": "Indonesian", "rate": "+0%", "pitch": "-1Hz", "sample": "Setiap ide hebat bisa langsung berubah menjadi konten siap tayang untuk seluruh dunia."},
    # --- Italian ---
    "it_elsa": {"id": "it-IT-ElsaNeural", "label": "Elsa — Expressive Italian Female (IT)", "group": "Italian", "rate": "+1%", "pitch": "+0Hz", "sample": "Trasforma ogni idea in un video professionale pronto per conquistare il pubblico."},
    "it_diego": {"id": "it-IT-DiegoNeural", "label": "Diego — Cinema Italian Male (IT)", "group": "Italian", "rate": "+0%", "pitch": "-1Hz", "sample": "Ritmo, voce naturale e sottotitoli dinamici fanno la differenza fin dal primo secondo."},
    # --- Japanese, Korean, Chinese, Russian ---
    "ja_nanami": {"id": "ja-JP-NanamiNeural", "label": "Nanami — Natural Japanese Female (JP)", "group": "Japanese", "rate": "+1%", "pitch": "+0Hz", "sample": "アイデアひとつから、プロ品質のショート動画を数分で制作できます。"},
    "ko_sunhi": {"id": "ko-KR-SunHiNeural", "label": "Sun-Hi — Natural Korean Female (KR)", "group": "Korean", "rate": "+1%", "pitch": "+0Hz", "sample": "단 하나의 아이디어로 몇 분 만에 스튜디오급 영상을 완성해 보세요."},
    "zh_xiaoxiao": {"id": "zh-CN-XiaoxiaoNeural", "label": "Xiaoxiao — Expressive Chinese Female (CN)", "group": "Chinese", "rate": "+1%", "pitch": "+0Hz", "sample": "只需一个创意，几分钟内即可生成电影级高清短视频。"},
    "ru_svetlana": {"id": "ru-RU-SvetlanaNeural", "label": "Svetlana — Clear Russian Female (RU)", "group": "Russian", "rate": "+0%", "pitch": "+0Hz", "sample": "Создавайте профессиональные видео с естественной озвучкой и динамичными субтитрами."},
    # Legacy aliases
    "urdu_male": {"id": "ur-PK-AsadNeural", "label": "Asad — Urdu Male", "group": "Urdu", "rate": "+2%", "pitch": "-2Hz", "sample": "Salam!"},
    "urdu_female": {"id": "ur-PK-UzmaNeural", "label": "Noor — Urdu Female", "group": "Urdu", "rate": "+2%", "pitch": "+2Hz", "sample": "Salam!"},
    "hindi_male": {"id": "hi-IN-MadhurNeural", "label": "Aarav — Hindi Male", "group": "Hindi", "rate": "+0%", "pitch": "-2Hz", "sample": "Namaste!"},
    "hindi_female": {"id": "hi-IN-SwaraNeural", "label": "Ananya — Hindi Female", "group": "Hindi", "rate": "+2%", "pitch": "+0Hz", "sample": "Namaste!"},
    "en_male": {"id": "en-US-AndrewMultilingualNeural", "label": "Andrew — English Male", "group": "English", "rate": "+1%", "pitch": "+0Hz", "sample": "Hello!"},
    "en_female": {"id": "en-US-AvaMultilingualNeural", "label": "Ava — English Female", "group": "English", "rate": "+2%", "pitch": "+0Hz", "sample": "Hello!"},
}


def get_ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def probe_duration_seconds(media_path: Path) -> float:
    ffmpeg = get_ffmpeg_exe()
    try:
        proc = subprocess.run([ffmpeg, "-i", str(media_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        import re
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
        if m:
            h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return max(1.5, h * 3600 + mn * 60 + s)
    except Exception:
        pass
    return 5.0


async def generate_voice_clip_with_timings(
    text: str,
    voice_key: str,
    out_path: Path,
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Generates realistic neural voiceover AND captures EXACT millisecond WordBoundary timings
    so captions & active-word karaoke sync precisely with speech!
    """
    import edge_tts

    preset = VOICE_PRESETS.get(voice_key, VOICE_PRESETS["urdu_female_noor"])
    voice_id = preset["id"]
    rate = preset.get("rate", "+0%")
    pitch = preset.get("pitch", "+0Hz")
    clean_text = (text or "").strip() or "Welcome."

    async def _stream_to_file(use_pitch: bool) -> List[Dict[str, Any]]:
        kwargs: Dict[str, Any] = {"rate": rate, "boundary": "WordBoundary"}
        if use_pitch and pitch != "+0Hz":
            kwargs["pitch"] = pitch
        comm = edge_tts.Communicate(clean_text, voice_id, **kwargs)
        audio_chunks = bytearray()
        words: List[Dict[str, Any]] = []
        async for ch in comm.stream():
            ctype = ch.get("type")
            if ctype == "audio":
                audio_chunks.extend(ch["data"])
            elif ctype == "WordBoundary":
                start_s = ch["offset"] / 1e7
                dur_s = max(0.08, ch["duration"] / 1e7)
                words.append({"start": round(start_s, 3), "end": round(start_s + dur_s, 3), "text": ch.get("text", "")})
        if len(audio_chunks) < 500:
            raise RuntimeError("Empty audio stream")
        out_path.write_bytes(bytes(audio_chunks))
        return words

    try:
        word_timings = await _stream_to_file(use_pitch=True)
    except Exception:
        word_timings = await _stream_to_file(use_pitch=False)

    dur = await asyncio.to_thread(probe_duration_seconds, out_path)
    return dur, word_timings


async def generate_voice_clip(text: str, voice_key: str, out_path: Path) -> float:
    dur, _ = await generate_voice_clip_with_timings(text, voice_key, out_path)
    return dur


async def _fetch_pexels_video(query: str, api_key: str, orientation: str, out_path: Path, used_ids: set) -> Optional[str]:
    if not api_key:
        return None
    headers = {"Authorization": api_key}
    params = {"query": query, "orientation": orientation, "per_page": 8, "size": "medium"}
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get("https://api.pexels.com/videos/search", headers=headers, params=params)
            if r.status_code != 200:
                return None
            videos = r.json().get("videos") or []
            chosen = next((v for v in videos if v.get("id") not in used_ids), videos[0] if videos else None)
            if not chosen:
                return None
            used_ids.add(chosen.get("id"))
            mp4s = [f for f in (chosen.get("video_files") or []) if f.get("file_type") == "video/mp4" and f.get("link")]
            if not mp4s:
                return None
            mp4s.sort(key=lambda f: abs((f.get("width") or 1080) - (1080 if orientation == "portrait" else 1280)))
            dl = await client.get(mp4s[0]["link"])
            if dl.status_code == 200 and len(dl.content) > 40_000:
                out_path.write_bytes(dl.content)
                return "hd_footage"
    except Exception:
        return None
    return None


async def _fetch_pixabay_video(query: str, api_key: str, out_path: Path, used_ids: set) -> Optional[str]:
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get("https://pixabay.com/api/videos/", params={"key": api_key, "q": query[:95], "per_page": 6})
            if r.status_code != 200:
                return None
            hits = r.json().get("hits") or []
            chosen = next((h for h in hits if h.get("id") not in used_ids), hits[0] if hits else None)
            if not chosen:
                return None
            used_ids.add(chosen.get("id"))
            vids = chosen.get("videos") or {}
            url = (vids.get("medium") or vids.get("large") or vids.get("small") or {}).get("url")
            if not url:
                return None
            dl = await client.get(url)
            if dl.status_code == 200 and len(dl.content) > 40_000:
                out_path.write_bytes(dl.content)
                return "hd_footage"
    except Exception:
        return None
    return None


async def _fetch_ai_visual(prompt: str, width: int, height: int, seed: int, out_path: Path) -> Optional[str]:
    """
    Rate-limit aware Pollinations Flux generator (spaces calls by ~5.5s so multi-scene videos
    succeed reliably instead of triggering 429 on scenes 2-7!).
    """
    global _LAST_POLLINATIONS_CALL
    now = time.monotonic()
    wait_s = 5.6 - (now - _LAST_POLLINATIONS_CALL)
    if wait_s > 0:
        await asyncio.sleep(wait_s)

    encoded = urllib.parse.quote(prompt[:380], safe="")
    urls = [
        f"https://gen.pollinations.ai/image/{encoded}?model=flux&width={width}&height={height}&seed={seed}&nologo=true",
        f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed}&nologo=true",
    ]
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        for attempt in range(2):
            _LAST_POLLINATIONS_CALL = time.monotonic()
            for url in urls:
                try:
                    r = await client.get(url)
                    ctype = r.headers.get("content-type", "")
                    if r.status_code == 200 and len(r.content) > 15_000 and ("image" in ctype or r.content[:2] in (b"\xff\xd8", b"\x89P")):
                        out_path.write_bytes(r.content)
                        with Image.open(out_path) as im:
                            if min(im.width, im.height) >= 400:
                                # Trim bottom 6% cleanly so no generator corner badge ever appears
                                im = im.crop((0, 0, im.width, int(im.height * 0.94)))
                                im.convert("RGB").save(out_path, "JPEG", quality=93)
                                return "ai_cinema"
                    if r.status_code == 429:
                        break
                except Exception:
                    continue
            if attempt == 0:
                await asyncio.sleep(5.5)
    return None


def _search_clean_hd_image_urls(query: str) -> List[str]:
    """Zero-API-key high-res clean photography search (strictly filtering watermarked stock & UI screenshot domains)."""
    preferred: List[str] = []
    others: List[str] = []
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            hits = list(ddgs.images(f"{query} cinematic photography unsplash pexels -watermark -dribbble", max_results=18))
            for h in hits:
                u = str(h.get("image") or "").strip()
                title = str(h.get("title") or "").lower()
                w = int(h.get("width") or 0)
                ht = int(h.get("height") or 0)
                low = u.lower()
                if not u.startswith("http"):
                    continue
                if any(bad in low for bad in WATERMARKED_DOMAINS):
                    continue
                if any(bad in title for bad in ("adobe stock", "shutterstock", "getty", "istock", "alamy", "dreamstime", "dribbble", "dashboard ui", "template")):
                    continue
                if w and ht and min(w, ht) < 520:
                    continue
                if any(good in low for good in PREFERRED_CLEAN_DOMAINS):
                    preferred.append(u)
                else:
                    others.append(u)
    except Exception:
        pass
    return preferred + others


async def _fetch_clean_hd_photo(query: str, out_path: Path, used_urls: set) -> Optional[str]:
    candidates = await asyncio.to_thread(_search_clean_hd_image_urls, query)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0"}
    async with httpx.AsyncClient(timeout=18.0, follow_redirects=True, headers=headers) as client:
        for u in candidates:
            if u in used_urls:
                continue
            try:
                r = await client.get(u)
                if r.status_code == 200 and len(r.content) > 20_000:
                    tmp = out_path.with_suffix(".tmp")
                    tmp.write_bytes(r.content)
                    with Image.open(tmp) as im:
                        if min(im.width, im.height) >= 480:
                            im.convert("RGB").save(out_path, "JPEG", quality=93)
                            tmp.unlink(missing_ok=True)
                            used_urls.add(u)
                            return "hd_photo"
                    tmp.unlink(missing_ok=True)
            except Exception:
                continue
    return None


def _load_font(size: int, style: str = "bold") -> ImageFont.FreeTypeFont:
    font_map = {
        "brush": [
            "C:/Windows/Fonts/BRUSHSCI.TTF",
            "C:/Windows/Fonts/SCRIPTBL.TTF",
            "C:/Windows/Fonts/segoescb.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
        ],
        "hand": [
            "C:/Windows/Fonts/segoeprb.ttf",
            "C:/Windows/Fonts/comicbd.ttf",
            "C:/Windows/Fonts/Inkfree.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
        ],
        "impact": [
            "C:/Windows/Fonts/impact.ttf",
            "C:/Windows/Fonts/arialbi.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ],
        "bold": [
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/verdanab.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ],
        "regular": [
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ],
    }
    for path in font_map.get(style, font_map["bold"]):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def generate_warm_parchment_canvas(
    width: int,
    height: int,
    scene_num: int,
    out_path: Path,
    character_img: Optional[Path] = None,
) -> str:
    """
    Signature Viral Typography Edit canvas (inspired by @nr.vibes0.1):
    Warm creamy parchment-gold radial glow (#FFF6D6 -> #C1AB7B), top-right lavender floral accent,
    subtle sparkle details, and clean rounded lavender-framed hero character/visual!
    """
    sw, sh = max(120, width // 4), max(120, height // 4)
    small = Image.new("RGB", (sw, sh))
    px = small.load()
    scx, scy = sw * 0.5, sh * 0.48
    smax = math.hypot(sw * 0.68, sh * 0.68)
    for y in range(sh):
        for x in range(sw):
            d = min(1.0, math.hypot(x - scx, y - scy) / smax)
            t = d ** 1.35
            px[x, y] = (int(255 * (1 - t) + 188 * t), int(246 * (1 - t) + 167 * t), int(214 * (1 - t) + 122 * t))
    img = small.resize((width, height), Image.Resampling.BICUBIC).convert("RGBA")

    # Top-right lavender cosmos flower corner accent (2x supersampled for razor-crisp anti-aliased curves!)
    fl_box = int(min(width, height) * 0.34)
    fl_hi = Image.new("RGBA", (fl_box * 2, fl_box * 2), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fl_hi)
    fcx, fcy = int(fl_box * 1.56), int(fl_box * 0.44)
    pr = int(fl_box * 0.48)
    for ang in range(0, 360, 45):
        rad = math.radians(ang)
        px_c = fcx + int(math.cos(rad) * pr * 0.78)
        py_c = fcy + int(math.sin(rad) * pr * 0.78)
        # Soft outer petal
        fd.ellipse([px_c - int(pr * 0.56), py_c - int(pr * 0.56), px_c + int(pr * 0.56), py_c + int(pr * 0.56)], fill=(124, 102, 198, 195))
        # Inner lavender highlight
        hx = fcx + int(math.cos(rad) * pr * 0.56)
        hy = fcy + int(math.sin(rad) * pr * 0.56)
        fd.ellipse([hx - int(pr * 0.28), hy - int(pr * 0.28), hx + int(pr * 0.28), hy + int(pr * 0.28)], fill=(162, 144, 224, 150))
    fd.ellipse([fcx - int(pr * 0.36), fcy - int(pr * 0.36), fcx + int(pr * 0.36), fcy + int(pr * 0.36)], fill=(238, 178, 42, 240))
    fd.ellipse([fcx - int(pr * 0.22), fcy - int(pr * 0.22), fcx + int(pr * 0.22), fcy + int(pr * 0.22)], fill=(252, 218, 106, 245))
    fl_lo = fl_hi.resize((fl_box, fl_box), Image.Resampling.LANCZOS)
    img.alpha_composite(fl_lo, (width - fl_box, 0))

    # Subtle bottom-left delicate accent ring
    decor = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    dd = ImageDraw.Draw(decor)
    dd.arc([int(-width * 0.06), int(height * 0.86), int(width * 0.16), int(height * 1.06)], 270, 360, fill=(126, 107, 196, 85), width=4)
    img = Image.alpha_composite(img, decor)

    # Frame character/scene visual cleanly in upper hero zone (9:16) or alternating side (16:9)
    if character_img and character_img.exists():
        try:
            with Image.open(character_img) as ch:
                ch = ch.convert("RGB")
                is_vert = height > width
                if is_vert:
                    cw, ch_h = int(width * 0.62), int(width * 0.62)
                    pos_x = (width - cw) // 2
                    pos_y = int(height * 0.12)
                else:
                    cw, ch_h = int(height * 0.62), int(height * 0.62)
                    pos_x = int(width * 0.06) if scene_num % 2 == 1 else int(width - cw - width * 0.06)
                    pos_y = (height - ch_h) // 2

                # Center-crop square
                side = min(ch.width, ch.height)
                ch = ch.crop(((ch.width - side) // 2, (ch.height - side) // 2, (ch.width + side) // 2, (ch.height + side) // 2))
                ch = ch.resize((cw, ch_h), Image.Resampling.LANCZOS).convert("RGBA")

                # Drop shadow behind framed card
                sh_box = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                ImageDraw.Draw(sh_box).rounded_rectangle([pos_x + 4, pos_y + 12, pos_x + cw + 12, pos_y + ch_h + 18], radius=38, fill=(80, 62, 32, 85))
                sh_box = sh_box.filter(ImageFilter.GaussianBlur(radius=18))
                img = Image.alpha_composite(img, sh_box)

                mask = Image.new("L", (cw, ch_h), 0)
                ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw, ch_h], radius=32, fill=255)
                frame = Image.new("RGBA", (cw + 12, ch_h + 12), (0, 0, 0, 0))
                ImageDraw.Draw(frame).rounded_rectangle([0, 0, cw + 12, ch_h + 12], radius=36, fill=(126, 107, 196, 230))
                frame.paste(ch, (6, 6), mask)
                img.alpha_composite(frame, (pos_x - 6, pos_y - 6))
        except Exception:
            pass

    img.convert("RGB").save(out_path, "JPEG", quality=93)
    return "viral_typography_canvas"


def _generate_cinematic_fallback_card(title: str, scene_num: int, width: int, height: int, out_path: Path) -> str:
    palettes = [
        ((12, 16, 30), (34, 24, 68), (99, 102, 241)),
        ((9, 18, 28), (15, 58, 86), (14, 165, 233)),
        ((20, 14, 28), (74, 26, 62), (236, 72, 153)),
        ((11, 20, 22), (20, 62, 56), (16, 185, 129)),
    ]
    c1, c2, accent = palettes[(scene_num - 1) % len(palettes)]

    img = Image.new("RGB", (width, height), c1)
    draw = ImageDraw.Draw(img, "RGBA")
    for y in range(0, height, 4):
        t = y / max(1, height)
        draw.rectangle(
            [0, y, width, y + 4],
            fill=(int(c1[0] * (1 - t) + c2[0] * t), int(c1[1] * (1 - t) + c2[1] * t), int(c1[2] * (1 - t) + c2[2] * t), 255),
        )

    orb = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(orb)
    od.ellipse([int(width * 0.08), int(height * 0.14), int(width * 0.78), int(height * 0.14 + width * 0.7)], fill=(accent[0], accent[1], accent[2], 70))
    od.ellipse([int(width * 0.42), int(height * 0.52), int(width * 1.08), int(height * 0.52 + width * 0.65)], fill=(245, 179, 66, 52))
    orb = orb.filter(ImageFilter.GaussianBlur(radius=95))
    img = Image.alpha_composite(img.convert("RGBA"), orb).convert("RGB")

    d2 = ImageDraw.Draw(img, "RGBA")
    step = int(min(width, height) * 0.09)
    for gx in range(step, width, step):
        d2.line([(gx, 0), (gx, height)], fill=(255, 255, 255, 12), width=1)
    for gy in range(step, height, step):
        d2.line([(0, gy), (width, gy)], fill=(255, 255, 255, 12), width=1)
    img.save(out_path, "JPEG", quality=93)
    return "motion_graphics"


def create_high_ctr_thumbnail(
    hero_media_path: Path,
    headline: str,
    subline: str,
    video_format: str,
    out_path: Path,
    visual_style: str = "Realistic Cinema",
) -> Path:
    tw, th = (1080, 1920) if video_format == "9:16" else (1280, 720)
    bg: Optional[Image.Image] = None

    if hero_media_path.exists():
        if hero_media_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            try:
                bg = Image.open(hero_media_path).convert("RGB")
            except Exception:
                bg = None
        else:
            tmp_frame = out_path.parent / "_thumb_frame.jpg"
            try:
                subprocess.run([get_ffmpeg_exe(), "-y", "-ss", "1.0", "-i", str(hero_media_path), "-vframes", "1", "-q:v", "2", str(tmp_frame)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                if tmp_frame.exists():
                    bg = Image.open(tmp_frame).convert("RGB")
                    tmp_frame.unlink(missing_ok=True)
            except Exception:
                bg = None

    if bg is None:
        tmp_card = out_path.parent / "_thumb_fb.jpg"
        _generate_cinematic_fallback_card(headline or "NEXUS", 1, tw, th, tmp_card)
        bg = Image.open(tmp_card).convert("RGB")
        tmp_card.unlink(missing_ok=True)

    src_r, dst_r = bg.width / bg.height, tw / th
    if src_r > dst_r:
        nw = int(bg.height * dst_r)
        bg = bg.crop(((bg.width - nw) // 2, 0, (bg.width + nw) // 2, bg.height))
    else:
        nh = int(bg.width / dst_r)
        bg = bg.crop((0, (bg.height - nh) // 2, bg.width, (bg.height + nh) // 2))
    bg = bg.resize((tw, th), Image.Resampling.LANCZOS).convert("RGBA")

    is_warm_typo = visual_style == "Viral Typography"
    if not is_warm_typo:
        overlay = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for y in range(0, th, 3):
            frac = y / th
            alpha = int(20 + (190 * (max(0.0, (frac - 0.38) / 0.62) ** 1.4)))
            od.rectangle([0, y, tw, y + 3], fill=(8, 10, 18, min(225, alpha)))
        bg = Image.alpha_composite(bg, overlay)

    draw = ImageDraw.Draw(bg)
    margin = int(tw * 0.07)
    head_text = (headline or "WATCH NOW").upper().strip()
    head_size = int(min(tw, th) * (0.105 if video_format == "9:16" else 0.125))
    head_font = _load_font(head_size, style="impact")

    words = head_text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=head_font) <= tw - margin * 2:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    lines = lines[:3]

    line_h = int(head_size * 1.15)
    total_h = len(lines) * line_h
    base_y = int(th * (0.66 if video_format == "9:16" else 0.56)) - total_h // 2

    for i, ln in enumerate(lines):
        y = base_y + i * line_h
        if is_warm_typo:
            lw = draw.textlength(ln, font=head_font)
            x = max(margin, (tw - lw) / 2)
            fill = (232, 77, 46, 255) if i % 2 == 0 else (35, 31, 138, 255)
            draw.text((x + 5, y + 7), ln, font=head_font, fill=(60, 44, 18, 95))
            draw.text((x, y), ln, font=head_font, fill=fill, stroke_width=4, stroke_fill=(14, 14, 18, 255))
        else:
            x = margin + 10
            fill = (255, 255, 255, 255) if i % 2 == 0 else (242, 84, 45, 255)
            draw.text((x + 5, y + 6), ln, font=head_font, fill=(0, 0, 0, 215))
            draw.text((x, y), ln, font=head_font, fill=fill, stroke_width=4, stroke_fill=(8, 10, 16, 255))

    if subline:
        sub_font = _load_font(int(head_size * 0.44), style=("hand" if is_warm_typo else "bold"))
        sub_y = base_y + total_h + 22
        sub_txt = subline[:55]
        if is_warm_typo:
            sw_txt = draw.textlength(sub_txt, font=sub_font)
            sx = max(margin, (tw - sw_txt) / 2)
            draw.text((sx + 2, sub_y + 3), sub_txt, font=sub_font, fill=(255, 250, 232, 180))
            draw.text((sx, sub_y), sub_txt, font=sub_font, fill=(18, 18, 22, 255))
        else:
            draw.text((margin + 12, sub_y + 3), sub_txt, font=sub_font, fill=(0, 0, 0, 195))
            draw.text((margin + 12, sub_y), sub_txt, font=sub_font, fill=(241, 245, 249, 245))

    bg.convert("RGB").save(out_path, "PNG")
    return out_path


async def run_producer(
    script_data: Dict[str, Any],
    project_dir: Path,
    video_format: str,
    voice_key: str,
    visual_mode: str,
    config: Dict[str, Any],
    log_fn: Callable[[str], None],
    visual_style: str = "Viral Typography",
) -> Dict[str, Any]:
    assets_dir = project_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    voice_info = VOICE_PRESETS.get(voice_key, VOICE_PRESETS["urdu_female_noor"])
    orientation = "portrait" if video_format == "9:16" else "landscape"
    is_vert = video_format == "9:16"
    out_w, out_h = (1080, 1920) if is_vert else (1920, 1080)
    img_w, img_h = (768, 1344) if is_vert else (1280, 720)

    pexels_key = config.get("pexels_api_key", "")
    pixabay_key = config.get("pixabay_api_key", "")
    used_pexels: set = set()
    used_pixabay: set = set()
    used_photo_urls: set = set()

    scenes = script_data.get("scenes") or []
    log_fn(f"Producer recording {voice_info['label']} (word-synced) & crafting {visual_style} visuals for {len(scenes)} scenes...")

    produced_scenes: List[Dict[str, Any]] = []
    hero_media: Optional[Path] = None

    for idx, sc in enumerate(scenes, start=1):
        audio_file = assets_dir / f"scene_{idx:02d}_voice.mp3"
        log_fn(f"Scene {idx}/{len(scenes)}: Recording neural voiceover with word sync...")
        duration, word_timings = await generate_voice_clip_with_timings(sc.get("narration", ""), voice_key, audio_file)

        visual_file: Optional[Path] = None
        visual_source = ""
        visual_type = "image"

        query = sc.get("visual_query", "modern technology photography")
        ai_prompt = sc.get("ai_image_prompt", query)

        if visual_style == "Viral Typography":
            char_tmp = assets_dir / f"scene_{idx:02d}_char.jpg"
            char_ok = None
            # Generate stylized character or clean pastel illustration visual for alternating/key scenes
            if idx == 1 or idx % 2 == 1:
                log_fn(f"Scene {idx}/{len(scenes)}: Creating stylized character visual...")
                char_ok = await _fetch_ai_visual(ai_prompt, 768, 768, seed=2100 + idx * 41, out_path=char_tmp)
                if not char_ok:
                    pastel_q = f"cute 3d character aesthetic illustration minimal art {idx}"
                    char_ok = await _fetch_clean_hd_photo(pastel_q, char_tmp, used_photo_urls)
            canvas_out = assets_dir / f"scene_{idx:02d}_visual.jpg"
            visual_source = await asyncio.to_thread(
                generate_warm_parchment_canvas,
                out_w,
                out_h,
                idx,
                canvas_out,
                char_tmp if char_ok else None,
            )
            visual_file = canvas_out
            visual_type = "image"
        else:
            want_stock = visual_mode in ("hybrid", "stock")
            want_ai = visual_mode in ("hybrid", "ai_images")

            # 1. Real HD Stock Video if Pexels/Pixabay configured
            if want_stock and (pexels_key or pixabay_key):
                vid_candidate = assets_dir / f"scene_{idx:02d}_visual.mp4"
                log_fn(f"Scene {idx}/{len(scenes)}: Fetching HD video clip ('{query}')...")
                src = await _fetch_pexels_video(query, pexels_key, orientation, vid_candidate, used_pexels)
                if not src and pixabay_key:
                    src = await _fetch_pixabay_video(query, pixabay_key, vid_candidate, used_pixabay)
                if src:
                    visual_file = vid_candidate
                    visual_source = src
                    visual_type = "video"

            # 2. If Realistic Cinema/Hybrid and no stock video key, try Clean HD Real Photography FIRST (fast, photorealistic, never rate-limited!)
            if visual_file is None and visual_style in ("Realistic Cinema", "Documentary Vox") and visual_mode != "ai_images":
                img_candidate = assets_dir / f"scene_{idx:02d}_visual.jpg"
                log_fn(f"Scene {idx}/{len(scenes)}: Fetching clean HD photography ('{query}')...")
                src = await _fetch_clean_hd_photo(query, img_candidate, used_photo_urls)
                if src:
                    visual_file = img_candidate
                    visual_source = src
                    visual_type = "image"

            # 3. Rate-limit-aware AI Cinema Visual (Flux)
            if visual_file is None and want_ai:
                img_candidate = assets_dir / f"scene_{idx:02d}_visual.jpg"
                log_fn(f"Scene {idx}/{len(scenes)}: Generating bespoke AI cinema scene...")
                src = await _fetch_ai_visual(ai_prompt, img_w, img_h, seed=1000 + idx * 73, out_path=img_candidate)
                if src:
                    visual_file = img_candidate
                    visual_source = src
                    visual_type = "image"

            # 4. Zero-key Clean HD Photography backup so we NEVER fall back to plain empty cards!
            if visual_file is None:
                img_candidate = assets_dir / f"scene_{idx:02d}_visual.jpg"
                log_fn(f"Scene {idx}/{len(scenes)}: Pulling clean HD visual backup...")
                src = await _fetch_clean_hd_photo(query, img_candidate, used_photo_urls)
                if src:
                    visual_file = img_candidate
                    visual_source = src
                    visual_type = "image"

            # 5. Last-resort Motion Graphics backdrop (only if offline)
            if visual_file is None:
                img_candidate = assets_dir / f"scene_{idx:02d}_visual.jpg"
                visual_source = await asyncio.to_thread(
                    _generate_cinematic_fallback_card,
                    sc.get("role", f"Scene {idx}"),
                    idx,
                    out_w,
                    out_h,
                    img_candidate,
                )
                visual_file = img_candidate
                visual_type = "image"

        if hero_media is None:
            hero_media = visual_file

        produced_scenes.append(
            {
                "scene_number": idx,
                "role": sc.get("role", f"Scene {idx}"),
                "narration": sc.get("narration", ""),
                "subtitle_text": sc.get("subtitle_text", ""),
                "hero_emphasis": sc.get("hero_emphasis", ""),
                "duration_sec": round(duration, 2),
                "word_timings": word_timings,
                "audio_file": audio_file.name,
                "visual_file": visual_file.name,
                "visual_type": visual_type,
                "visual_source": visual_source,
            }
        )

    thumb_path = project_dir / "thumbnail.png"
    log_fn("Producer designing High-CTR Cover Thumbnail...")
    await asyncio.to_thread(
        create_high_ctr_thumbnail,
        hero_media or (assets_dir / "scene_01_visual.jpg"),
        script_data.get("thumbnail_headline") or script_data.get("video_title", "WATCH NOW")[:24],
        script_data.get("thumbnail_subline", ""),
        video_format,
        thumb_path,
        visual_style,
    )

    total_dur = round(sum(s["duration_sec"] for s in produced_scenes), 2)
    log_fn(f"Producer finished {len(produced_scenes)} scenes ({total_dur}s total) + Cover Thumbnail.")
    return {
        "voice_id": voice_info["id"],
        "voice_label": voice_info["label"],
        "total_duration_sec": total_dur,
        "thumbnail_file": thumb_path.name,
        "scenes": produced_scenes,
    }

import asyncio
import math
import os
import random
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple
from PIL import Image, ImageDraw, ImageFilter
from employees.emp4_producer import _load_font, get_ffmpeg_exe


def _clean_subtitle_words(subtitle_text: str) -> List[str]:
    """Sanitizes LLM bilingual slashes (' / '), em-dashes, and stray punctuation tokens."""
    raw = (subtitle_text or "").strip()
    if " / " in raw:
        raw = raw.split(" / ", 1)[0].strip()
    raw = raw.replace("—", " ").replace("–", " ").replace(" | ", " ")
    cleaned: List[str] = []
    for tok in raw.split():
        t = tok.strip()
        if not t or t in ("/", "|", "-", "—", "–", "•"):
            continue
        cleaned.append(t)
    return cleaned


def _build_word_synced_beats(
    subtitle_text: str,
    word_timings: List[Dict[str, Any]],
    total_dur: float,
    words_per_group: int = 3,
) -> List[Dict[str, Any]]:
    """
    Maps exact millisecond WordBoundary timestamps from neural TTS onto `subtitle_text`
    so every caption group AND every active spoken word pops in true sync with the voice —
    with ZERO blank caption gaps from t=0.00 to t=total_dur!
    """
    sub_words = _clean_subtitle_words(subtitle_text)
    if not sub_words:
        return []

    n_sub = len(sub_words)
    # Derive start/end timestamp per subtitle word using real TTS word_timings proportionally
    word_spans: List[Tuple[float, float, str]] = []
    if word_timings and len(word_timings) >= 2:
        n_tts = len(word_timings)
        for i, sw in enumerate(sub_words):
            t_idx0 = min(n_tts - 1, int(i * n_tts / n_sub))
            t_idx1 = min(n_tts - 1, max(t_idx0, int((i + 1) * n_tts / n_sub) - 1))
            s0 = float(word_timings[t_idx0]["start"])
            s1 = float(word_timings[t_idx1]["end"])
            word_spans.append((max(0.0, s0), max(s0 + 0.14, s1), sw))
        # Snap first word to 0.0 and last word to total_dur, and close every gap cleanly!
        word_spans[0] = (0.0, word_spans[0][1], word_spans[0][2])
        for i in range(len(word_spans) - 1):
            s0, s1, w = word_spans[i]
            next_s0 = word_spans[i + 1][0]
            if next_s0 > s0 + 0.06:
                word_spans[i] = (s0, next_s0, w)
            else:
                # Monotonic fallback if two words share the same TTS bucket
                mid = s0 + max(0.10, (s1 - s0) * 0.5)
                word_spans[i] = (s0, mid, w)
                word_spans[i + 1] = (mid, max(mid + 0.12, word_spans[i + 1][1]), word_spans[i + 1][2])
        last_s0, last_s1, last_w = word_spans[-1]
        word_spans[-1] = (last_s0, max(last_s1, total_dur + 0.05), last_w)
    else:
        step = total_dur / n_sub
        for i, sw in enumerate(sub_words):
            end_t = (total_dur + 0.05) if i == n_sub - 1 else (i + 1) * step
            word_spans.append((i * step, end_t, sw))

    groups: List[Dict[str, Any]] = []
    for g_start in range(0, n_sub, words_per_group):
        grp = word_spans[g_start : g_start + words_per_group]
        if not grp:
            continue
        groups.append(
            {
                "start": grp[0][0],
                "end": grp[-1][1],
                "words": [x[2] for x in grp],
                "spans": grp,
            }
        )
    # Guarantee seamless group boundaries (zero blank frames between caption groups!)
    for gi in range(len(groups) - 1):
        groups[gi]["end"] = groups[gi + 1]["start"]
        if groups[gi]["spans"]:
            s0, _, w = groups[gi]["spans"][-1]
            groups[gi]["spans"][-1] = (s0, groups[gi]["end"], w)
    if groups:
        groups[0]["start"] = 0.0
        groups[-1]["end"] = max(groups[-1]["end"], total_dur + 0.05)
    return groups


def _fit_font_width(draw: ImageDraw.ImageDraw, text: str, base_size: int, style: str, max_w: int):
    size = base_size
    while size >= 24:
        fn = _load_font(size, style=style)
        if draw.textlength(text, font=fn) <= max_w:
            return fn
        size = int(size * 0.88)
    return _load_font(24, style=style)


def _render_viral_typography_overlay(
    words: List[str],
    hero_emphasis: str,
    width: int,
    height: int,
    is_vertical: bool,
    scene_num: int,
    chunk_idx: int,
    out_path: Path,
    anim_scale: float = 1.0,
    y_offset: int = 0,
    glow_halo: bool = False,
) -> Path:
    """
    Signature '@nr.vibes0.1' Viral Kinetic Typography (NO BOX!) with optional pop-scale,
    slide-up kinetic offset, and soft glow pulse!
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow_layer)
    draw = ImageDraw.Draw(img)

    if not words:
        img.save(out_path, "PNG")
        return out_path

    if len(words) <= 2:
        line_specs = [("hero", " ".join(words).upper())]
    elif len(words) <= 4:
        mid = len(words) // 2
        line_specs = [("script", " ".join(words[:mid])), ("hero", " ".join(words[mid:]).upper())]
    else:
        a = max(1, len(words) // 3)
        b = max(a + 1, (2 * len(words)) // 3)
        line_specs = [
            ("script", " ".join(words[:a])),
            ("hero", " ".join(words[a:b]).upper()),
            ("hand", " ".join(words[b:])),
        ]

    base_scale = int((width if is_vertical else int(height * 0.90)) * anim_scale)
    max_w = int(width * (0.86 if is_vertical else 0.46)) if (not is_vertical and scene_num % 2 == 1) else int(width * 0.84)

    if is_vertical:
        center_x = width * 0.5
        center_y = (height * 0.69 if (scene_num == 1 or scene_num % 2 == 1) else height * 0.50) + y_offset
    else:
        center_x = width * (0.68 if scene_num % 2 == 1 else 0.50)
        center_y = height * 0.52 + y_offset

    hero_colors = [(232, 77, 46, 255), (35, 31, 138, 255), (217, 70, 35, 255)]
    hero_fill = hero_colors[(scene_num + chunk_idx) % len(hero_colors)]

    rendered = []
    for kind, txt in line_specs:
        if kind == "hero":
            fn = _fit_font_width(draw, txt, int(base_scale * 0.094), "impact", max_w)
        elif kind == "script":
            fn = _fit_font_width(draw, txt, int(base_scale * 0.096), "brush", max_w)
        else:
            fn = _fit_font_width(draw, txt, int(base_scale * 0.070), "hand", max_w)
        rendered.append((kind, txt, fn, int(fn.size * 1.24)))

    total_h = sum(r[3] for r in rendered)
    cur_y = center_y - total_h / 2

    for kind, txt, fn, lh in rendered:
        tw = draw.textlength(txt, font=fn)
        x = max(40, min(width - tw - 40, center_x - tw / 2))
        y = cur_y
        if glow_halo and kind == "hero":
            sd.text((x, y), txt, font=fn, fill=(hero_fill[0], hero_fill[1], hero_fill[2], 140))
        sd.text((x + 6, y + 8), txt, font=fn, fill=(0, 0, 0, 95))
        if kind == "hero":
            draw.text((x, y), txt, font=fn, fill=hero_fill, stroke_width=4, stroke_fill=(12, 12, 16, 255))
        else:
            draw.text((x, y), txt, font=fn, fill=(14, 14, 18, 255))
        cur_y += lh

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=(12 if glow_halo else 6)))
    Image.alpha_composite(shadow_layer, img).save(out_path, "PNG")
    return out_path


def _render_active_word_karaoke_overlay(
    words: List[str],
    active_word_idx: int,
    width: int,
    height: int,
    is_vertical: bool,
    group_idx: int,
    progress_frac: float,
    out_path: Path,
    pop_boost: float = 1.07,
    y_offset: int = 0,
    glow_halo: bool = False,
) -> Path:
    """
    TRUE CAPCUT / HORMOZI ACTIVE-WORD KARAOKE POP (NO UGLY DARK BOX!) with kinetic pop-bounce,
    slide-up motion, and optional neon glow pulse on the spoken word!
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    draw = ImageDraw.Draw(img)

    # Sleek top retention progress bar
    bar_h = 8 if is_vertical else 6
    draw.rectangle([0, 0, width, bar_h], fill=(255, 255, 255, 38))
    draw.rectangle([0, 0, int(width * max(0.02, min(1.0, progress_frac))), bar_h], fill=(253, 224, 71, 235))

    up_words = [w.upper() for w in words if w.strip()]
    if not up_words:
        img.save(out_path, "PNG")
        return out_path

    full_line = " ".join(up_words)
    base_size = int(width * (0.074 if is_vertical else 0.046))
    font = _fit_font_width(draw, full_line, base_size, "impact", int(width * 0.85))
    hi_font = _load_font(int(font.size * pop_boost), style="impact")

    hi_palette = [(253, 224, 71, 255), (56, 189, 248, 255), (251, 146, 60, 255)]
    hi_color = hi_palette[group_idx % len(hi_palette)]

    space_w = draw.textlength(" ", font=font)
    widths = [draw.textlength(w, font=(hi_font if i == active_word_idx else font)) for i, w in enumerate(up_words)]
    total_w = sum(widths) + space_w * max(0, len(up_words) - 1)

    x = (width - total_w) / 2
    center_y = int(height * (0.74 if is_vertical else 0.82)) + y_offset

    for i, w in enumerate(up_words):
        is_hi = i == active_word_idx
        fn = hi_font if is_hi else font
        fill = hi_color if is_hi else (255, 255, 255, 255)
        y = center_y - fn.size // 2 - (6 if is_hi else 0)
        if is_hi and glow_halo:
            sd.text((x, y), w, font=fn, fill=(hi_color[0], hi_color[1], hi_color[2], 210))
        sd.text((x + 5, y + 7), w, font=fn, fill=(0, 0, 0, 190))
        draw.text((x, y), w, font=fn, fill=fill, stroke_width=5, stroke_fill=(6, 8, 14, 255))
        x += widths[i] + space_w

    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=(14 if glow_halo else 6)))
    Image.alpha_composite(shadow, img).save(out_path, "PNG")
    return out_path


def _generate_soundtrack_with_whooshes(
    duration_sec: float,
    cut_times: List[float],
    out_path: Path,
) -> Path:
    """
    Pure-Python copyright-free warm cinematic ambient pad + soft subtle whoosh swells on scene cuts!
    """
    sr = 22050
    total_samples = int((duration_sec + 1.5) * sr)
    freqs = [73.42, 110.0, 174.61, 220.0, 329.63]
    amps = [0.22, 0.18, 0.14, 0.10, 0.06]
    rng = random.Random(42)

    frames = bytearray()
    lp = 0.0
    for n in range(total_samples):
        t = n / sr
        lfo = 0.78 + 0.22 * math.sin(2 * math.pi * 0.18 * t)
        fade_in = min(1.0, t / 1.6)
        fade_out = min(1.0, max(0.0, (duration_sec + 1.1 - t) / 2.0))
        pad = sum(a * math.sin(2 * math.pi * f * t) for f, a in zip(freqs, amps)) * lfo * fade_in * fade_out * 0.19

        # Soft filtered noise whoosh around each scene transition cut
        whoosh = 0.0
        for ct in cut_times:
            dt = abs(t - ct)
            if dt < 0.22:
                env_w = math.cos((dt / 0.22) * (math.pi / 2)) ** 2
                white = rng.uniform(-1.0, 1.0)
                lp = lp * 0.82 + white * 0.18
                whoosh += lp * env_w * 0.28
                break

        val = max(-1.0, min(1.0, pad + whoosh))
        frames.extend(struct.pack("<h", int(val * 32767)))

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))
    return out_path


def _format_srt_time(seconds: float) -> str:
    ms = int(round((seconds - int(seconds)) * 1000))
    total = int(seconds)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d},{ms:03d}"


def _write_srt_and_social_pack(project_dir: Path, topic: str, script_data: Dict[str, Any], produced_scenes: List[Dict[str, Any]]) -> None:
    srt_lines: List[str] = []
    cursor = 0.0
    counter = 1
    for sc in produced_scenes:
        dur = float(sc.get("duration_sec", 4.0))
        groups = _build_word_synced_beats(sc.get("subtitle_text", ""), sc.get("word_timings") or [], dur, words_per_group=4)
        for g in groups:
            srt_lines.extend(
                [
                    str(counter),
                    f"{_format_srt_time(cursor + g['start'])} --> {_format_srt_time(cursor + g['end'])}",
                    " ".join(g["words"]),
                    "",
                ]
            )
            counter += 1
        cursor += dur
    (project_dir / "subtitles.srt").write_text("\n".join(srt_lines), encoding="utf-8")

    pack = script_data.get("social_pack") or {}
    yt, ig, fb = pack.get("youtube") or {}, pack.get("instagram") or {}, pack.get("facebook") or {}
    md = f"""# Upload Pack — {script_data.get('video_title', topic)}

## YouTube
**Title:** {yt.get('title', '')}
**A/B Titles:** {' | '.join(yt.get('alt_titles', []))}

**Description:**
{yt.get('description', '')}

**Tags:** {', '.join(yt.get('tags', []))}
**Pinned Comment:** {yt.get('pinned_comment', '')}

---

## Instagram Reels
{ig.get('caption', '')}

{' '.join(ig.get('hashtags', []))}

---

## Facebook
{fb.get('post_copy', '')}

{' '.join(fb.get('hashtags', []))}
"""
    (project_dir / "social_media_pack.md").write_text(md, encoding="utf-8")


def _render_scene_clip_sync(
    ffmpeg: str,
    visual_path: Path,
    visual_type: str,
    audio_path: Path,
    duration: float,
    subtitle_text: str,
    hero_emphasis: str,
    word_timings: List[Dict[str, Any]],
    enable_captions: bool,
    visual_style: str,
    width: int,
    height: int,
    is_vertical: bool,
    out_clip: Path,
    work_dir: Path,
    scene_num: int,
    scene_start_global: float,
    total_video_dur: float,
    caption_animation: str = "pop",
) -> float:
    fps = 30
    dur = max(1.6, duration + 0.14)
    base_clip = work_dir / f"base_{scene_num:02d}.mp4"
    is_typography_mode = visual_style == "Viral Typography"

    if visual_type == "video":
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"eq=contrast=1.05:saturation=1.10:brightness=-0.02,"
            f"vignette=PI/5,fps={fps},format=yuv420p"
        )
        cmd_base = [
            ffmpeg, "-y", "-stream_loop", "-1", "-i", str(visual_path),
            "-t", f"{dur:.3f}", "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", str(base_clip),
        ]
    else:
        total_frames = max(45, int(math.ceil(dur * fps)))
        pre_img = work_dir / f"pre_{scene_num:02d}.jpg"
        with Image.open(visual_path) as im:
            im = im.convert("RGB")
            src_r, dst_r = im.width / im.height, width / height
            if src_r > dst_r:
                nw = int(im.height * dst_r)
                im = im.crop(((im.width - nw) // 2, 0, (im.width + nw) // 2, im.height))
            else:
                nh = int(im.width / dst_r)
                im = im.crop((0, (im.height - nh) // 2, im.width, (im.height + nh) // 2))
            im.resize((width, height), Image.Resampling.LANCZOS).save(pre_img, "JPEG", quality=93)

        if is_typography_mode:
            vf = (
                f"zoompan=z='min(zoom+0.00045,1.045)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={width}x{height}:fps={fps},format=yuv420p"
            )
        else:
            zoom_expr = "min(zoom+0.0012,1.15)" if scene_num % 2 == 1 else "if(lte(zoom,1.0),1.14,max(1.0,zoom-0.0011))"
            vf = (
                f"zoompan=z='{zoom_expr}':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={total_frames}:s={width}x{height}:fps={fps},"
                f"eq=contrast=1.05:saturation=1.08,vignette=PI/5,format=yuv420p"
            )

        cmd_base = [
            ffmpeg, "-y", "-i", str(pre_img),
            "-t", f"{dur:.3f}", "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", str(base_clip),
        ]

    res = subprocess.run(cmd_base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=200)
    if res.returncode != 0:
        raise RuntimeError(f"Scene {scene_num} visual render error: {res.stderr[-260:]}")

    # Build word-synced kinetic animated overlays (pop / slide / glow / classic)
    overlay_events: List[Tuple[Path, float, float]] = []
    anim_mode = (caption_animation or "pop").lower()
    use_glow = anim_mode == "glow"

    if enable_captions and subtitle_text.strip():
        if is_typography_mode:
            groups = _build_word_synced_beats(subtitle_text, word_timings, dur, words_per_group=5)
            for gi, grp in enumerate(groups):
                g0, g1 = grp["start"], grp["end"]
                if anim_mode in ("pop", "slide") and (g1 - g0) > 0.24:
                    intro_end = round(g0 + 0.11, 3)
                    cap_intro = work_dir / f"cap_{scene_num:02d}_{gi:02d}_in.png"
                    _render_viral_typography_overlay(
                        grp["words"], hero_emphasis, width, height, is_vertical, scene_num, gi, cap_intro,
                        anim_scale=(1.08 if anim_mode == "pop" else 0.98),
                        y_offset=(22 if anim_mode == "slide" else -6),
                        glow_halo=use_glow,
                    )
                    overlay_events.append((cap_intro, g0, intro_end))
                    cap_png = work_dir / f"cap_{scene_num:02d}_{gi:02d}.png"
                    _render_viral_typography_overlay(
                        grp["words"], hero_emphasis, width, height, is_vertical, scene_num, gi, cap_png,
                        anim_scale=1.0, y_offset=0, glow_halo=use_glow,
                    )
                    overlay_events.append((cap_png, intro_end, g1))
                else:
                    cap_png = work_dir / f"cap_{scene_num:02d}_{gi:02d}.png"
                    _render_viral_typography_overlay(
                        grp["words"], hero_emphasis, width, height, is_vertical, scene_num, gi, cap_png,
                        glow_halo=use_glow,
                    )
                    overlay_events.append((cap_png, g0, g1))
        else:
            # Active-word karaoke pop with snappy scale-bounce / slide / neon glow!
            groups = _build_word_synced_beats(subtitle_text, word_timings, dur, words_per_group=3)
            ev_count = 0
            for gi, grp in enumerate(groups):
                spans = grp["spans"]
                if len(groups) <= 7 and ev_count + len(spans) <= 26:
                    for wi, (w0, w1, _) in enumerate(spans):
                        prog = (scene_start_global + w0) / max(1.0, total_video_dur)
                        if anim_mode in ("pop", "slide") and wi == 0 and (w1 - w0) > 0.18 and ev_count < 24:
                            intro_end = round(w0 + 0.08, 3)
                            cap_in = work_dir / f"cap_{scene_num:02d}_{gi:02d}_{wi}_in.png"
                            _render_active_word_karaoke_overlay(
                                grp["words"], wi, width, height, is_vertical, gi, prog, cap_in,
                                pop_boost=(1.15 if anim_mode == "pop" else 1.08),
                                y_offset=(18 if anim_mode == "slide" else -5),
                                glow_halo=use_glow,
                            )
                            overlay_events.append((cap_in, w0, intro_end))
                            ev_count += 1
                            w0 = intro_end
                        cap_png = work_dir / f"cap_{scene_num:02d}_{gi:02d}_{wi}.png"
                        _render_active_word_karaoke_overlay(
                            grp["words"], wi, width, height, is_vertical, gi, prog, cap_png,
                            pop_boost=(1.11 if anim_mode == "pop" else 1.07),
                            y_offset=0, glow_halo=use_glow,
                        )
                        overlay_events.append((cap_png, w0, w1))
                        ev_count += 1
                else:
                    cap_png = work_dir / f"cap_{scene_num:02d}_{gi:02d}.png"
                    prog = (scene_start_global + grp["start"]) / max(1.0, total_video_dur)
                    _render_active_word_karaoke_overlay(
                        grp["words"], len(grp["words"]) - 1, width, height, is_vertical, gi, prog, cap_png,
                        glow_halo=use_glow,
                    )
                    overlay_events.append((cap_png, grp["start"], grp["end"]))
                    ev_count += 1

    if overlay_events:
        inputs = [ffmpeg, "-y", "-i", str(base_clip), "-i", str(audio_path)]
        filter_parts = []
        last_stream = "[0:v]"
        for oi, (png_path, t0, t1) in enumerate(overlay_events):
            inputs.extend(["-i", str(png_path)])
            in_idx = oi + 2
            out_stream = f"[v{oi}]"
            filter_parts.append(f"{last_stream}[{in_idx}:v]overlay=0:0:enable='between(t,{t0:.2f},{t1:.2f})'{out_stream}")
            last_stream = out_stream

        cmd_mux = inputs + [
            "-filter_complex", ";".join(filter_parts),
            "-map", last_stream, "-map", "1:a",
            "-threads", "2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-shortest", str(out_clip),
        ]
    else:
        cmd_mux = [
            ffmpeg, "-y", "-i", str(base_clip), "-i", str(audio_path),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-shortest", str(out_clip),
        ]

    res2 = subprocess.run(cmd_mux, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=220)
    if res2.returncode != 0:
        raise RuntimeError(f"Scene {scene_num} caption/audio render error: {res2.stderr[-260:]}")
    return dur


def _stitch_with_xfade(
    ffmpeg: str,
    clips: List[Tuple[Path, float]],
    out_mp4: Path,
    trans_dur: float = 0.30,
) -> Tuple[bool, List[float]]:
    """
    Stitches scenes with silky smooth FFmpeg `xfade` video transitions + `acrossfade` audio transitions!
    Returns (success, cut_timestamps).
    """
    if len(clips) <= 1 or len(clips) > 12:
        return False, []

    transitions = ["fade", "smoothleft", "slideup", "smoothright", "dissolve"]
    inputs = [ffmpeg, "-y"]
    for p, _ in clips:
        inputs.extend(["-i", str(p)])

    v_filters = []
    a_filters = []
    # Normalize timebase across clips for reliable xfade
    for i in range(len(clips)):
        v_filters.append(f"[{i}:v]settb=AVTB,fps=30,format=yuv420p[vs{i}]")

    cur_v = "[vs0]"
    cur_a = "[0:a]"
    offset = clips[0][1] - trans_dur
    cut_times: List[float] = []

    for i in range(1, len(clips)):
        tr = transitions[(i - 1) % len(transitions)]
        safe_off = max(0.2, offset)
        cut_times.append(safe_off)
        out_v = f"[vx{i}]"
        out_a = f"[ax{i}]"
        v_filters.append(f"{cur_v}[vs{i}]xfade=transition={tr}:duration={trans_dur:.2f}:offset={safe_off:.3f}{out_v}")
        a_filters.append(f"{cur_a}[{i}:a]acrossfade=d={trans_dur:.2f}:c1=tri:c2=tri{out_a}")
        cur_v = out_v
        cur_a = out_a
        offset = safe_off + clips[i][1] - trans_dur

    fc = ";".join(v_filters + a_filters)
    cmd = inputs + [
        "-filter_complex", fc,
        "-map", cur_v, "-map", cur_a,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", str(out_mp4),
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
    return res.returncode == 0, cut_times


def _assemble_final_video_sync(
    project_dir: Path,
    topic: str,
    script_data: Dict[str, Any],
    producer_data: Dict[str, Any],
    video_format: str,
    enable_captions: bool,
    enable_music: bool,
    log_fn: Callable[[str], None],
    visual_style: str = "Viral Typography",
    caption_animation: str = "pop",
) -> Dict[str, Any]:
    ffmpeg = get_ffmpeg_exe()
    assets_dir = project_dir / "assets"
    work_dir = project_dir / "_render_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    is_vertical = video_format == "9:16"
    low_mem = os.environ.get("LOW_MEM_MODE", "").strip() == "1"
    if low_mem:
        width, height = (720, 1280) if is_vertical else (1280, 720)
    else:
        width, height = (1080, 1920) if is_vertical else (1920, 1080)
    produced_scenes = producer_data.get("scenes") or []
    total_est = sum(float(s.get("duration_sec", 4.0)) for s in produced_scenes) or 30.0

    clips_with_dur: List[Tuple[Path, float]] = []
    running_t = 0.0

    for sc in produced_scenes:
        idx = sc["scene_number"]
        log_fn(f"Editor rendering Scene {idx}/{len(produced_scenes)} (word-synced captions + motion)...")
        clip_out = work_dir / f"scene_{idx:02d}_final.mp4"
        actual_dur = _render_scene_clip_sync(
            ffmpeg=ffmpeg,
            visual_path=assets_dir / sc["visual_file"],
            visual_type=sc.get("visual_type", "image"),
            audio_path=assets_dir / sc["audio_file"],
            duration=float(sc.get("duration_sec", 4.0)),
            subtitle_text=sc.get("subtitle_text", ""),
            hero_emphasis=sc.get("hero_emphasis", ""),
            word_timings=sc.get("word_timings") or [],
            enable_captions=enable_captions,
            visual_style=visual_style,
            width=width,
            height=height,
            is_vertical=is_vertical,
            out_clip=clip_out,
            work_dir=work_dir,
            scene_num=idx,
            scene_start_global=running_t,
            total_video_dur=total_est,
            caption_animation=caption_animation,
        )
        clips_with_dur.append((clip_out, actual_dur))
        running_t += actual_dur

    stitched_mp4 = work_dir / "stitched.mp4"
    log_fn("Editor applying smooth cinematic scene transitions...")
    xfade_ok, cut_times = _stitch_with_xfade(ffmpeg, clips_with_dur, stitched_mp4, trans_dur=0.28)

    if not xfade_ok:
        concat_list = work_dir / "concat.txt"
        concat_list.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p, _ in clips_with_dur), encoding="utf-8")
        cut_times = []
        acc = 0.0
        for _, d in clips_with_dur[:-1]:
            acc += d
            cut_times.append(acc)
        cmd_cat = [
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart", str(stitched_mp4),
        ]
        res_cat = subprocess.run(cmd_cat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
        if res_cat.returncode != 0:
            raise RuntimeError(f"Master assembly failed: {res_cat.stderr[-260:]}")

    final_mp4 = project_dir / "final_video.mp4"
    total_dur = float(producer_data.get("total_duration_sec", 30.0))

    if enable_music:
        log_fn("Editor mastering soundtrack + transition whoosh SFX...")
        bg_wav = work_dir / "ambient_bed.wav"
        _generate_soundtrack_with_whooshes(total_dur + 2.0, cut_times, bg_wav)
        cmd_mix = [
            ffmpeg, "-y", "-i", str(stitched_mp4), "-i", str(bg_wav),
            "-filter_complex", "[0:a]volume=1.10[voice];[1:a]volume=0.20[bgm];[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final_mp4),
        ]
        res_mix = subprocess.run(cmd_mix, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=240)
        if res_mix.returncode != 0:
            final_mp4.write_bytes(stitched_mp4.read_bytes())
    else:
        final_mp4.write_bytes(stitched_mp4.read_bytes())

    _write_srt_and_social_pack(project_dir, topic, script_data, produced_scenes)
    size_mb = round(final_mp4.stat().st_size / (1024 * 1024), 2)
    log_fn(f"Final master exported ({size_mb} MB, {width}x{height}, xfade={'ON' if xfade_ok else 'OFF'})!")

    return {
        "video_file": "final_video.mp4",
        "subtitles_file": "subtitles.srt",
        "social_pack_file": "social_media_pack.md",
        "thumbnail_file": "thumbnail.png",
        "resolution": f"{width}x{height}",
        "fps": 30,
        "size_mb": size_mb,
        "duration_sec": total_dur,
        "transitions": "xfade" if xfade_ok else "cut",
    }


async def run_editor(
    project_dir: Path,
    topic: str,
    script_data: Dict[str, Any],
    producer_data: Dict[str, Any],
    video_format: str,
    enable_captions: bool,
    enable_music: bool,
    log_fn: Callable[[str], None],
    visual_style: str = "Viral Typography",
    caption_animation: str = "pop",
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        _assemble_final_video_sync,
        project_dir,
        topic,
        script_data,
        producer_data,
        video_format,
        enable_captions,
        enable_music,
        log_fn,
        visual_style,
        caption_animation,
    )

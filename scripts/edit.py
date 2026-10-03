"""Assemble an episode from picked takes: 1280x720/30fps, burned-in captions (en or zh),
optional end card, per-clip levelling + final loudnorm.

    python edit.py <episode_dir> [--lang en|zh] [--autotime]

Reads <episode_dir>/shots.json (shot order + prompts) and <episode_dir>/edit.json:
    {"output": "my_film_ep01",                   # output name (default: the directory name)
     "picks": {"01": "b", ...},                  # default take "a"
     "skip": ["02"],                             # shots left out of the cut
     "trim": {"01": {"in": 0.4, "out": 9.6}},    # seconds inside the take (out = clip end if missing)
     "captions": {"01": [{"start": 0.0, "end": 6.3, "en": "...", "zh": "..."}]},
     "gain": {"02": 3},                          # dB on top of the levelled take (-12..12)
     "fonts": {"en": "fonts/NotoSans-Bold.ttf", "zh": "fonts/NotoSansSC-Bold.otf"},  # under assets/
     "endcard": {"title": "MY FILM", "sub": "Episode 1", "price": "Made with okaypic.com"}}

Caption times are relative to the untrimmed take, so trimming never shifts them.
Missing captions are auto-timed: silencedetect finds where speech sits in the take and the
quoted lines of the shot's prompt are spread over that span in order (snapped to the detected
segments when the counts match). --autotime only writes those guesses into edit.json, for the
editor UI to refine. It is an estimate: listen once before posting.

The assets folder (fonts/, optional logo.png) is the first "assets" directory found walking up
from <episode_dir>. The end card is skipped when edit.json has no "endcard".
"""
import argparse
import json
import os
import re
import subprocess
import textwrap

DEFAULT_FONTS = {"en": "fonts/NotoSans-Bold.ttf", "zh": "fonts/NotoSansSC-Bold.otf"}


def find_assets(ep_dir):
    d = os.path.abspath(ep_dir)
    for _ in range(5):
        cand = os.path.join(d, "assets")
        if os.path.isdir(cand):
            return cand
        d = os.path.dirname(d)
    raise SystemExit("no assets/ folder found above the episode directory (run fetch_fonts.py there)")


def probe_duration(mp4):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def speech_segments(mp4):
    out = subprocess.run(["ffmpeg", "-i", mp4, "-af", "silencedetect=n=-35dB:d=0.3", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    dur = probe_duration(mp4)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    if len(ends) < len(starts):
        ends.append(dur)
    segs, cur = [], 0.0
    for s, e in zip(starts, ends):
        if s - cur >= 0.25:
            segs.append((cur, s))
        cur = e
    if dur - cur >= 0.25:
        segs.append((cur, dur))
    return segs, dur


def time_lines(lines, segs, dur):
    if not lines:
        return []
    if len(segs) == len(lines):
        return [(round(a, 2), round(b, 2), t) for (a, b), t in zip(segs, lines)]
    lo = segs[0][0] if segs else 0.3
    hi = segs[-1][1] if segs else dur - 0.3
    lo, hi = max(0.0, lo - 0.1), min(dur, hi + 0.2)
    total = sum(len(t) for t in lines) or 1
    out, cur = [], lo
    for t in lines:
        w = (hi - lo) * len(t) / total
        out.append((round(cur, 2), round(cur + w, 2), t))
        cur += w
    return out


def quoted_lines(prompt):
    return [q.strip() for q in re.findall(r'"([^"]+)"', prompt)]


def auto_captions(mp4, prompt):
    segs, dur = speech_segments(mp4)
    return [{"start": a, "end": b, "en": t, "zh": ""} for a, b, t in time_lines(quoted_lines(prompt), segs, dur)]


def wrap(text, lang):
    if lang == "zh":
        text = text.strip()
        return "\n".join(text[i:i + 24] for i in range(0, len(text), 24))
    return "\n".join(textwrap.wrap(text, 46))


def drawtext(font, textfile, start, end, size):
    return (f"drawtext=fontfile={font}:textfile={textfile}:fontsize={size}:fontcolor=white:"
            f"borderw=4:bordercolor=black@0.85:line_spacing=4:x=(w-text_w)/2:y=h-70-text_h:"
            f"enable='between(t,{start:.2f},{end:.2f})'")


def esc(s):
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\\\\\'").replace("%", "\\%")


def render_endcard(ep_dir, assets, assets_rel, font_en, card):
    title, sub = card.get("title", ""), card.get("sub", "")
    price = card.get("price", "Made with okaypic.com")
    has_logo = os.path.exists(os.path.join(assets, "logo.png"))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x1a1108:s=1280x720:d=3.5:r=30"]
    if has_logo:
        cmd += ["-i", f"{assets_rel}/logo.png"]
    cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    graph = "[0:v]vignette=PI/3.5[bg];"
    graph += "[1:v]scale=360:-1:flags=lanczos[lg];[bg][lg]overlay=(W-w)/2:120[v1];" if has_logo else "[bg]null[v1];"
    graph += (f"[v1]drawtext=fontfile={font_en}:text='{esc(title)}':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=330,"
              f"drawtext=fontfile={font_en}:text='{esc(sub)}':fontsize=36:fontcolor=0xb9ab95:x=(w-text_w)/2:y=425,"
              f"drawtext=fontfile={font_en}:text='okaypic.com':fontsize=44:fontcolor=0xf5c542:x=(w-text_w)/2:y=500,"
              f"drawtext=fontfile={font_en}:text='{esc(price)}':fontsize=24:fontcolor=0xb9ab95:x=(w-text_w)/2:y=575,"
              "fade=t=in:st=0:d=0.4,format=yuv420p[v]")
    cmd += ["-filter_complex", graph, "-map", "[v]", "-map", f"{2 if has_logo else 1}:a", "-t", "3.5",
            "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "160k", "endcard.mp4"]
    subprocess.run(cmd, cwd=ep_dir, check=True)


def load(ep_dir):
    spec = json.load(open(os.path.join(ep_dir, "shots.json"), encoding="utf-8"))
    cfg_path = os.path.join(ep_dir, "edit.json")
    cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
    return spec, cfg


def save_cfg(ep_dir, cfg):
    with open(os.path.join(ep_dir, "edit.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)


def level_take(mp4, log=None):
    """Make a loudness-levelled copy of a take (audio to -16 LUFS, video stream copied, +faststart)
    in takes/leveled/. H3 takes come out anywhere between -26 and -10 LUFS; levelling them once
    means the editor preview and the final cut hear the same thing, and renders skip the per-clip
    loudnorm. Cached: skipped when the copy is newer than the take."""
    out = os.path.join(os.path.dirname(mp4), "leveled", os.path.basename(mp4))
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(mp4):
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if log:
        log(f"levelling {os.path.basename(mp4)}")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-c:v", "copy",
                        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                        "-movflags", "+faststart", out], capture_output=True, text=True)
    if r.returncode != 0:
        if os.path.exists(out):
            os.remove(out)
        raise RuntimeError(f"levelling failed for {mp4}: {r.stderr[-400:]}")
    return out


def level_all(ep_dir, log=None):
    takes = os.path.join(ep_dir, "takes")
    if not os.path.isdir(takes):
        return 0
    n = 0
    for f in sorted(os.listdir(takes)):
        if f.endswith(".mp4"):
            before = os.path.exists(os.path.join(takes, "leveled", f))
            level_take(os.path.join(takes, f), log)
            n += 0 if before else 1
    return n


def raw_take_path(ep_dir, cfg, sid):
    return os.path.join(ep_dir, "takes", f"{sid}_{cfg.get('picks', {}).get(sid, 'a')}.mp4")


def take_path(ep_dir, cfg, sid):
    """The levelled copy when it exists, else the raw take."""
    raw = raw_take_path(ep_dir, cfg, sid)
    lv = os.path.join(os.path.dirname(raw), "leveled", os.path.basename(raw))
    return lv if os.path.exists(lv) else raw


def fill_missing_captions(ep_dir, spec, cfg):
    """Auto-time every shot that has no captions yet. Returns True if anything was added."""
    caps = cfg.setdefault("captions", {})
    changed = False
    for shot in spec["shots"]:
        sid = shot["id"]
        mp4 = take_path(ep_dir, cfg, sid)
        if sid not in caps and os.path.exists(mp4):
            caps[sid] = auto_captions(mp4, shot["prompt"])
            changed = True
    return changed


def render(ep_dir, lang="en", log=print):
    ep_dir = os.path.abspath(ep_dir)
    level_all(ep_dir, log)
    spec, cfg = load(ep_dir)
    if fill_missing_captions(ep_dir, spec, cfg):
        save_cfg(ep_dir, cfg)
    assets = find_assets(ep_dir)
    assets_rel = os.path.relpath(assets, ep_dir).replace("\\", "/")
    fonts = {**DEFAULT_FONTS, **cfg.get("fonts", {})}
    font, font_en = f"{assets_rel}/{fonts[lang]}", f"{assets_rel}/{fonts['en']}"
    if not os.path.exists(os.path.join(assets, fonts[lang])):
        raise SystemExit(f"font not found: {os.path.join(assets, fonts[lang])} (run fetch_fonts.py or set edit.json fonts)")
    size = 44 if lang == "en" else 42

    skip, trims = set(cfg.get("skip", [])), cfg.get("trim", {})
    cap_dir = os.path.join(ep_dir, "captions")
    os.makedirs(cap_dir, exist_ok=True)
    inputs, vparts, aparts, timeline, t0 = [], [], [], [], 0.0
    for shot in spec["shots"]:
        sid = shot["id"]
        if sid in skip:
            continue
        mp4 = take_path(ep_dir, cfg, sid)
        if not os.path.exists(mp4):
            log(f"missing {os.path.basename(mp4)}, skipping")
            continue
        idx = len(inputs)
        inputs.append(os.path.relpath(mp4, ep_dir).replace("\\", "/"))
        dur = probe_duration(mp4)
        tr = trims.get(sid, {})
        tin = float(tr.get("in", 0) or 0)
        tout = min(float(tr.get("out") or dur), dur)
        vchain = f"trim=start={tin:.3f}:end={tout:.3f},setpts=PTS-STARTPTS,scale=1280:720,setsar=1,fps=30"
        for j, cap in enumerate(cfg.get("captions", {}).get(sid, [])):
            text = (cap.get(lang) or "").strip()
            a, b = float(cap["start"]) - tin, float(cap["end"]) - tin
            if not text or b <= 0 or a >= tout - tin:
                continue
            a, b = max(a, 0.0), min(b, tout - tin)
            tf = f"captions/{sid}_{j}_{lang}.txt"
            with open(os.path.join(ep_dir, tf), "w", encoding="utf-8") as f:
                f.write(wrap(text, lang))
            vchain += "," + drawtext(font, tf, a, b, size)
            timeline.append((round(t0 + a, 1), round(t0 + b, 1), sid, text))
        vparts.append(f"[{idx}:v]{vchain}[v{idx}]")
        gain = float(cfg.get("gain", {}).get(sid, 0) or 0)
        # Takes are already levelled to -16 LUFS (level_take); a raw take only slips through when
        # levelling failed, so normalise it inline in that case.
        lvl = "" if "leveled" in mp4.replace("\\", "/").split("/") else "loudnorm=I=-16:TP=-1.5:LRA=11,"
        aparts.append(f"[{idx}:a]atrim=start={tin:.3f}:end={tout:.3f},asetpts=PTS-STARTPTS,"
                      f"aformat=sample_rates=48000:channel_layouts=stereo,{lvl}volume={gain}dB[a{idx}]")
        t0 += tout - tin

    if "endcard" in cfg:
        render_endcard(ep_dir, assets, assets_rel, font_en, cfg["endcard"])
        idx = len(inputs)
        inputs.append("endcard.mp4")
        vparts.append(f"[{idx}:v]scale=1280:720,setsar=1,fps=30[v{idx}]")
        aparts.append(f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{idx}]")
        t0 += 3.5
    n = len(inputs)
    concat = "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a];[a]loudnorm=I=-14:TP=-1.5:LRA=11[an]"
    with open(os.path.join(ep_dir, f"filter_{lang}.txt"), "w", encoding="utf-8") as f:
        f.write(";\n".join(vparts + aparts + [concat]))
    with open(os.path.join(cap_dir, f"timeline_{lang}.txt"), "w", encoding="utf-8") as f:
        for a, b, sid, text in timeline:
            f.write(f"{a:7.1f} {b:7.1f}  {sid}  {text}\n")

    out = f"{cfg.get('output') or os.path.basename(ep_dir)}_{lang}.mp4"
    part = out + ".part.mp4"  # render here, rename when complete: nobody opens a half-written file
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    for rel in inputs:
        cmd += ["-i", rel]
    cmd += ["-filter_complex_script", f"filter_{lang}.txt", "-map", "[v]", "-map", "[an]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", part]
    log(f"rendering {out}: {n} clips, ~{t0:.0f}s")
    proc = subprocess.Popen(cmd, cwd=ep_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    last = -1
    for line in proc.stdout:
        if line.startswith("out_time_us=") and t0 > 0:
            try:
                pct = min(99, int(int(line.split("=")[1]) / 1e6 / t0 * 100))
            except ValueError:
                continue
            if pct >= last + 5:
                last = pct
                log(f"progress {pct}%")
    err = proc.stderr.read()
    if proc.wait() != 0:
        if os.path.exists(os.path.join(ep_dir, part)):
            os.remove(os.path.join(ep_dir, part))
        log(err[-2000:])
        raise SystemExit("ffmpeg failed")
    os.replace(os.path.join(ep_dir, part), os.path.join(ep_dir, out))
    log(f"done {out}")
    return os.path.join(ep_dir, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode_dir")
    ap.add_argument("--lang", default="en", choices=["en", "zh"])
    ap.add_argument("--autotime", action="store_true", help="only fill missing captions into edit.json")
    ap.add_argument("--level", action="store_true", help="only make the levelled copies of the takes")
    a = ap.parse_args()
    if a.level:
        print("levelled", level_all(a.episode_dir, print), "new takes")
        return
    if a.autotime:
        spec, cfg = load(a.episode_dir)
        if fill_missing_captions(a.episode_dir, spec, cfg):
            save_cfg(a.episode_dir, cfg)
        print("captions in edit.json:", sum(len(v) for v in cfg.get("captions", {}).values()))
        return
    render(a.episode_dir, a.lang)


if __name__ == "__main__":
    main()

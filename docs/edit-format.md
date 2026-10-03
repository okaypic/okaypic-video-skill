# `edit.json` — the cut

Written by the editor UI, readable by hand, rendered by `edit.py`.

```json
{
  "output": "goblin_city_ep01",
  "fonts": {"en": "fonts/NotoSans-Bold.ttf", "zh": "fonts/NotoSansSC-Bold.otf"},
  "picks": {"01": "b", "16": "b"},
  "skip": ["27"],
  "trim": {"26": {"in": 0, "out": 7.2}},
  "gain": {"02": 3},
  "captions": {
    "01": [
      {"start": 0.0, "end": 6.28, "en": "A prank collective. Probably a crypto marketing stunt.", "zh": "一个恶作剧团伙。多半是某个加密货币的营销噱头。"},
      {"start": 6.28, "end": 10.12, "en": "Goblins. Sure. How much do I buy?", "zh": "哥布林？行啊。我该买多少？"}
    ]
  },
  "endcard": {"title": "GOBLIN CITY", "sub": "Episode 1 - The Liquidation", "price": "Made with okaypic.com"}
}
```

| Field | Meaning |
|---|---|
| `output` | Base name; the files are `<output>_en.mp4` and `<output>_zh.mp4`. Default: the episode directory name. |
| `fonts` | Paths under the project's `assets/`. Defaults are the Noto fonts `fetch_fonts.py` downloads. Any TTF/OTF/TTC works. |
| `picks` | Take letter per shot. Missing → `a`. |
| `skip` | Shots left out of the cut (kept in `shots.json` so they can come back). |
| `trim` | Seconds inside the take. `out` missing or null = end of clip. Caption times stay relative to the untrimmed take. |
| `gain` | dB per shot on top of the levelled take (−12…+12; the editor's volume slider). |
| `captions` | Per shot, in order. `start`/`end` in seconds of the untrimmed take; `en` and `zh` text (empty = not shown in that language). |
| `endcard` | Omit the key to render without an end card. `title` big, `sub` under it, `okaypic.com` in brand gold, `price` small. Uses `assets/logo.png` if present. |

## How captions get their times

`edit.py --autotime` (and the UI, on first load) runs ffmpeg `silencedetect` on the picked take,
takes the quoted lines from the shot's prompt, and spreads them over the span where there is
sound — snapped to the detected segments when their count matches the number of lines. It is a
guess within about a second; the editor UI exists so a human can fix it while watching.

Chinese lines are left empty for you (or Claude) to fill; the UI shows both languages side by
side. Lines wrap automatically (46 Latin characters / 24 CJK characters per line).

## Rendering

- Takes are levelled once, up front: `takes/leveled/<take>.mp4` is the take with its audio at
  −16 LUFS (video stream copied, so it takes a second per clip). `gen_clips.py` makes it on
  download, `editor.py` on startup, `edit.py` before a render (`--level` does only that). H3 takes
  vary from −26 to −10 LUFS between clips; the editor preview and the cut both use the levelled
  copies, so what you hear while editing is what you get.
- Every clip: `trim`, scale to 1280×720, 30 fps, captions burned in with a black border, `gain`.
- Hard-cut concat, then the whole programme is normalised to −14 LUFS / −1.5 dBTP.
- H.264 CRF 20 slow, AAC 192 kbps, `+faststart`. A 5-minute episode is ~80 MB.
- `filter_<lang>.txt` (the ffmpeg filter graph) and `captions/timeline_<lang>.txt` (every caption
  with its absolute time) are left next to the output for debugging.

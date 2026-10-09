---
name: okaypic-video
description: Make short films, episodic series and ads with AI video through the okaypic.com API (MiniMax H3 video with generated voices, GPT/Gemini images for character sheets). Use when the user wants to write, generate, assemble or edit an AI-generated video, series episode, promo or ad with okaypic, or asks about okaypic's API. Covers planning the shot list, character reference sheets, batch rendering takes, picking takes from contact sheets, burned-in captions in English and Chinese, a local editing UI, and cost control.
---

# okaypic video skill

You are producing a video with the okaypic.com API: images for character/location reference
sheets, MiniMax H3 for 1–15 s clips with generated dialogue, sound and music, ffmpeg to cut it
together. The scripts in `scripts/` do the mechanical work; your job is the creative work and
quality control. Everything below has been used to ship real episodes; follow it unless the user
asks for something else.

## Setup (once)

- `OKAYPIC_API_KEY` in the environment or a `.env` file in the project (never print it, never
  commit it). Keys: https://okaypic.com/api-docs . Prices: https://okaypic.com/pricing .
- `ffmpeg` and `ffprobe` on PATH. Python 3.9+, stdlib only.
- Fonts for captions: `python scripts/fetch_fonts.py <project>/assets` (Noto Sans + Noto Sans SC,
  OFL). Optional `<project>/assets/logo.png` for the end card.
- Project layout the scripts expect:

```
project/
  .env                     OKAYPIC_API_KEY=...
  assets/fonts/            captions fonts (+ optional logo.png)
  ep01/
    cast.json              who/where to draw          -> refs/sheets/<name>.png
    shots.json             style + ordered shots      -> takes/<shot>_<take>.mp4 (+ .jpg contact sheet)
    edit.json              picks, trims, captions     -> <output>_en.mp4 / <output>_zh.mp4
```

## Workflow

Costs are small but real: one 10 s clip at 768p is US$0.10, a sheet US$0.02–0.03. Tell the user
the estimate before each paid step and **get their OK on the plan before generating anything**.

1. **Plan with the user.** Concept, tone, language, aspect ratio (16:9 unless they say
   otherwise), length. For a series, write an outline first (world, characters, per-episode hook
   and ending) and iterate until they sign off. Keep a `outline.md` in the project.
2. **Script as a shot list.** One shot = one H3 clip of 5–10 s. For each shot: location, action
   beat by beat, the exact spoken lines in double quotes, the voice (age, accent, mood), sound.
   Write it in `docs/shots-format.md` form (`shots.json`). Put the hook in shot 1: the first three
   seconds decide whether anyone keeps watching. ≤ 12 words per line of dialogue; H3 is most
   reliable with short lines. Avoid on-screen text in prompts; overlay text in post instead.
3. **Reference sheets.** Write `cast.json` (see `docs/cast-format.md`) and run
   `python scripts/gen_sheets.py ep01`. Show the user the sheets (they are the faces every clip
   will inherit) and regenerate until approved.
   **If you have your own image tool, use it for the sheets** (e.g. Codex, which has
   gpt-image-2.5 built in): run `python scripts/gen_sheets.py ep01 --prompts-only`, render each
   `refs/sheets/<name>.prompt.txt` with your tool as a 16:9 image (attach the entry's `ref` photo
   when it has one) and save it as `refs/sheets/<name>.png`. That costs the user nothing on
   okaypic. Fall back to the API (`gen_sheets.py ep01 --missing`) for anything your tool can't do.
   Agents without an image tool (Claude Code and most others) use `gen_sheets.py` directly.
   Rules that matter:
   - State ethnicity, age, build and height explicitly; models default to a generic face otherwise.
   - One retained visual anchor per character (a tie, a scar, a hat) survives across styles.
   - A character who changes form (human → creature) needs one sheet per form.
   - Write positive descriptions only ("clean white background"), never "no text / no watermark":
     naming a thing summons it.
4. **Render takes.** `python scripts/gen_clips.py ep01` renders every shot × every seed (2 seeds
   is the sweet spot). Run it detached and tail `takes/run.log`; with 18 in flight a clip takes
   10–20 min, so a 25-shot episode is 30–60 min. Review the 5-frame contact sheets
   (`takes/<shot>_<take>.jpg`), not the videos: pick on character consistency first, then energy.
   Re-run only the shots that failed or misfired (`gen_clips.py ep01 07 12`); the script is
   resumable and never charges twice for the same `client_request_id`.
5. **Cut.** `python scripts/edit.py ep01 --autotime` fills caption timings from the audio; then
   `python scripts/editor.py ep01` opens the local editing UI (pick takes, trim heads/tails,
   nudge captions while watching, write Chinese captions, export EN/ZH). Or edit `edit.json` by
   hand and run `python scripts/edit.py ep01 --lang en`. Output: 1280×720, CRF 20, loudness
   −14 LUFS, `+faststart`.
6. **Verify.** Make a frame sheet of the final file
   (`ffmpeg -i out.mp4 -vf "fps=1/8,scale=256:-1,tile=8x4" -frames:v 1 sheet.jpg`) and look at
   it. You cannot hear the audio: say so, and ask the user to listen once before posting,
   especially for caption timing.

## Prompting H3 (the part that decides quality)

- Start with the style sentence (`shots.json` "style" is prepended to every shot), then place,
  then action beat by beat, then dialogue in quotes with the voice described, then sound.
- Refer to reference sheets as "the man from <Picture 1>", in the order of the shot's `refs`.
  Say "the same ... lounge" in later shots for continuity.
- Keep `optimize_prompt: true` (okaypic rewrites plain English into H3's structured format using
  your references; no extra charge). Do not hand-write the structured format.
- Different seeds give different takes; the same seed does **not** reproduce a clip. Keep the
  takes you like.
- H3 writes real text on screens and signs sometimes, but not reliably; plan overlays.
- Crowds, exact blocking, or strict continuity with the previous shot: render the opening frame
  as an image first (reference sheets as `images`), then lock it with `first_frame` in the shot
  (ref_mode "okay"). See `docs/prompting-h3.md`.
- Loudness of generated takes varies by 15 dB. Every take gets a levelled copy
  (`takes/leveled/`, −16 LUFS) as soon as it is downloaded; the editor previews and `edit.py`
  renders from those copies, then normalises the programme to −14 LUFS. If a narration is still
  buried, set the clip's volume slider in the editor (or `"gain": {"02": 4}` in `edit.json`).

## Balance and top-ups

- Before a batch: `python scripts/gen_clips.py ep01 --quote` prints what is done, what is in
  flight (already paid) and what is left to render, with its cost and the current balance.
  Quote that line to the user. After a crash or a stopped run, quote again: a resume only
  charges for what is left.
- The scripts check the balance and stop with a top-up link when it won't cover the batch, or when
  the API answers 402 mid-batch (in-flight takes keep rendering and are downloaded). Tell the user
  plainly: what it costs, what is left, that they can top up from US$2 at
  https://okaypic.com/billing (card or WeChat Pay), and that re-running continues where it stopped.
  New accounts start with a small free credit that runs out after a few clips; say so before
  their first paid batch rather than after it fails.
- `GET /api/balance` returns `{"balanceCents": ...}` for the key.

## Guardrails

- Never put the API key in a prompt, a log, a commit, or a file you did not create for it.
- Before any paid batch, state the number of calls and the cost, and wait for approval unless the
  user already approved that batch.
- Keep `client_request_id` unique per take (`<ep>-<shot>_<take>-<attempt>`); retrying a timed-out
  request with the same id is free.
- Failed tasks are refunded; `content_violation` is never retryable — rewrite the prompt.
- Do not watch full videos to judge takes; use contact sheets, then only open the finalists.

## Files

- `scripts/okaypic_api.py` – API client (env/.env key, idempotency, inline base64 media, curl fallback)
- `scripts/gen_sheets.py` – character and location reference sheets from `cast.json`
- `scripts/gen_clips.py` – batch H3 rendering from `shots.json`, resumable, contact sheets
- `scripts/edit.py` – assemble, captions (en/zh), end card, loudness
- `scripts/editor.py` + `editor.html` – local editing UI on http://127.0.0.1:8765
- `scripts/fetch_fonts.py` – download the caption fonts
- `docs/` – formats, prompting guide, API cheat-sheet, worked example
- `examples/goblin-city-ep01/` – a real 28-shot episode: shots.json and edit.json with en/zh captions

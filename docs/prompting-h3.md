# Prompting MiniMax H3 through okaypic

H3 renders 1–15 s clips **with audio**: voices in the language you write the dialogue in, sound
effects, ambience. Reference images keep characters consistent across shots. This is what we
learned shipping episodes with it.

## Request shape

```json
{
  "model": "minimax-h3",
  "prompt": "Photorealistic cinematic drama. <place> <action> ... \"line\" ... <sound>",
  "duration": 10, "ratio": "16:9", "resolution": "768p",
  "ref_mode": "omni", "optimize_prompt": true, "seed": 1011,
  "client_request_id": "ep01-01_a-1",
  "media": [{"type": "image", "url": "data:image/jpeg;base64,..."}]
}
```

- `media` images become `<Picture 1>`, `<Picture 2>`… in order (≤ 9 images, ≤ 3 audio clips).
  Public https URLs or base64 data URIs (≤ 10 MB each, ≤ 12 per request); data URIs are stored on
  okaypic's CDN for you. `gen_clips.py` inlines sheets downscaled to 2048 px.
- `optimize_prompt: true`: okaypic's LLM rewrites your plain-English prompt into H3's structured
  format using the references and audio. Free. Prompts already in that format pass through.
- `seed`: different seeds → different takes. The same seed is **not** reproducible.
- `client_request_id` / `Idempotency-Key`: same id → same task, never charged twice. Use
  `<ep>-<shot>_<take>-<attempt>`.
- Output: 1344×768 for 768p 16:9, ~10.1 s for `duration: 10`.

## The prompt

1. **Style sentence** first (shared by the whole episode).
2. **Place**: "The same rooftop lounge at night" — "the same" carries continuity.
3. **Action beat by beat**, in the order it should happen. Camera moves are understood: "the
   camera tilts down from the screen to…", "overhead shot of…", "the camera pushes in…".
4. **Dialogue** in double quotes, each line introduced by who speaks and how: `The man from
   <Picture 1>, furious, voice cracking: "You said it would go up!"`. Short lines (≤ 12 words).
   Off-screen voices work: `From the phone, a calm gravelly voice: "..."`.
5. **Sound**: "Ice clinks in the glass.", "A long flat alarm tone, then silence."
6. Optional pacing tag: "Deadpan, snappy timing." / "Snappy comedic timing."

Things that behaved well: holographic screens, phone UIs, face-scan overlays, crowds of
creatures, rain, neon; a narrator voice-over on a scenery shot; an electronic voice
("A soft synthetic female voice: ..."); a character seeing themselves in a mirror.

Things to avoid: readable on-screen text (chalkboards, signs: plan an overlay), more than three
speakers in one shot, two different characters who look alike, "no X" phrasing.

## Reference strategy

- **Sheets, not stills.** A 16:9 sheet with close-ups and front/side/back full body (see
  `cast-format.md`) keeps a face across 50 clips; a single three-quarter portrait drifts.
- One sheet per form of a character (human / creature), both carrying the same anchor object.
- Pass only the sheets a shot needs. Extra references leak into the frame ("two Victors").
- If a take shows a duplicate character, prefer the other seed over re-rendering; it is usually
  seed-specific.

## Modes

| `ref_mode` | Inputs | Use for |
|---|---|---|
| `omni` (default) | `media` images + audio | Nearly everything. Fastest. |
| `okay` | `first_frame` / `last_frame` **plus** `media` | Crowds, exact blocking, strict continuity: render the opening frame as an image first (with the sheets as image references), then lock it here. Locked frames are not numbered as pictures. 480p/768p, 5–15 s (≥ 6 s best), slower; under heavy load may fail after 30 min in queue (refunded). |
| `first-last` | `first_frame` (+ `last_frame`), no `media` | Pure interpolation between frames. |
| `lip-sync` | exactly 1 image + 1 audio | Audio-driven talking head; the video is as long as the audio. |

`gen_clips.py` switches to `okay` automatically when a shot has `first_frame`.

## Picking takes

Make a contact sheet instead of watching:

```
ffmpeg -i take.mp4 -vf "fps=1/2,scale=320:-1,tile=5x1" -frames:v 1 take.jpg
```

Pick on character consistency with the sheet first, then on energy. Check where speech sits
with `ffmpeg -i take.mp4 -af silencedetect=n=-35dB:d=0.3 -f null -`. Takes vary ±15 dB in
loudness; `edit.py` handles that.

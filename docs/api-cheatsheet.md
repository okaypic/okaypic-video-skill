# okaypic API cheat-sheet

Full reference: https://okaypic.com/api-docs . Prices: https://okaypic.com/pricing .

All calls: `Authorization: Bearer $OKAYPIC_API_KEY`, `Content-Type: application/json`.
Base URL `https://okaypic.com`.

| What | Call |
|---|---|
| Image | `POST /api/image/generate` → poll `GET /api/image/tasks/<taskId>` |
| Video | `POST /api/video/generate` → poll `GET /api/video/tasks/<taskId>` |

Submit returns `{"taskId": "...", "status": "pending"}`. Poll every 5–15 s until `status` is
`completed` (`resultUrls[0]`) or `failed` (`errorCode`, `retryable`, `errorMessage`). Failed
tasks are refunded.

Send `client_request_id` in the body (and/or an `Idempotency-Key` header): a repeat with the same
id returns the original task and never charges twice, so a timed-out submit can be retried safely.

## Image models

| Model | Ratios | Resolution | Notes |
|---|---|---|---|
| `gpt-image-2.5` | 1:1 16:9 9:16 4:3 3:4 3:2 2:3 | `1k` `2k` `4k` | Default for sheets (2k). ≤ 6 reference `images`. US$0.03 |
| `gemini-3.1-flash-image-preview` | + 21:9 | — | Cheaper, fast, good with references. US$0.02 |
| `gemini-3-pro-image-preview` | + 21:9 | — | US$0.03 |
| `doubao-seedream-5.0` | + 21:9 | `1k` `2k` `4k` | US$0.20 |
| `gpt-image-2` | | — | Older gpt-image |

```json
{"model": "gpt-image-2.5", "ratio": "16:9", "resolution": "2k",
 "prompt": "A character reference sheet ...", "images": ["data:image/jpeg;base64,..."],
 "client_request_id": "ep01-sheet-victor-1"}
```

## MiniMax H3 (video)

Per-second pricing: 480p US$0.007/s, 768p US$0.01/s, 1080p higher. 1–15 s (1080p ≤ 10 s).
Ratios 16:9 / 9:16. Output has generated voices, SFX and ambience.

| Param | Values |
|---|---|
| `duration` | 1–15 |
| `resolution` | `480p` / `768p` (default) / `1080p` |
| `ref_mode` | `omni` (default) / `okay` / `first-last` / `lip-sync` — see prompting-h3.md |
| `media` | `[{"type": "image"|"audio", "url": https or data URI}]`, ≤ 9 images + 3 audio |
| `first_frame` / `last_frame` | https URL or data URI (`okay`, `first-last`) |
| `optimize_prompt` | `true` recommended; rewrites plain English into H3's structured prompt |
| `seed` | 0–2147483647, H3 only (other models reject it) |

## Errors

| `errorCode` | retryable | Do |
|---|---|---|
| `content_violation` | no | Rewrite the prompt / change the reference. |
| other | often yes | Resubmit with the same `client_request_id` (free). |

HTTP 429 or "concurrent": the account has 20 generations in progress; wait for some to finish.

## Notes from the field

- Some Windows Python builds time out in the TLS handshake with urllib; `okaypic_api.py` falls
  back to `curl` automatically.
- With 18 clips in flight a 10 s clip takes 10–20 minutes; alone it takes 4–7.
- Inline data URIs count toward request size; downscale sheets to ~2048 px (≈ 200 KB JPEG).

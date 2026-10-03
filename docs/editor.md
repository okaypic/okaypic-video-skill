# The editing UI

```
python scripts/editor.py ep01            # opens http://127.0.0.1:8765
python scripts/editor.py ep01 --port 9000 --no-browser
```

Python standard library only (http.server); the page is `scripts/editor.html`. It reads
`shots.json` and `edit.json`, fills missing caption timings from the audio on first load, and
saves every change back to `edit.json` about half a second after you stop typing (the "saved"
pill in the header tells you).

## Header

- **preview captions** — which language the overlay on the videos shows (en / zh).
- **caption nudge step** — seconds moved by every ◀ ▶ button (default 0.2).
- **Export EN / Export ZH / Export both** — saves, then renders `<output>_<lang>.mp4` in the
  background. The log appears under the header; when it says `done …` a link opens the file.

## Per shot

- **take** — which take file to use (`takes/<shot>_<take>.mp4`). The video reloads so you can
  compare takes by ear immediately.
- **skip** — leave this shot out of the cut.
- **trim in / out** — seconds inside the take. Type them, or scrub the video to the moment and
  press *set in from playhead* / *set out from playhead*. *clear* resets. Captions keep their
  times (they are relative to the untrimmed take); anything trimmed away is simply not shown.
- **captions**
  - *◀ all −step / all +step ▶* shift every caption of the shot (use when the whole clip's
    dialogue starts earlier or later than guessed).
  - *auto-time from audio* re-runs the silence detection for the current take and keeps the
    Chinese text you already wrote for identical English lines.
  - *+ add* inserts a caption at the playhead.
  - Per line: ▶ plays from the caption start; start–end fields; ◀ ▶ nudge both by one step;
    *start=ph* / *end=ph* set a boundary from the playhead; ✕ deletes. English and Chinese text
    side by side; an empty text means "no caption in that language".

The overlay under the video shows the active caption of the preview language while playing, so
you can scrub and watch the timing without exporting.

## Workflow that works

1. Play each shot once at 1× with the EN overlay. Most guesses are within a second; nudge the ones
   that lead or lag.
2. For shots with two speakers, use *start=ph* on the second line while the clip plays.
3. Trim dead air at clip heads (H3 often opens on a half-second of stillness) and the tail after
   the last line.
4. Fill the Chinese column (or let Claude write it into `edit.json` and polish here).
5. Export EN, watch it once with sound, then Export ZH.

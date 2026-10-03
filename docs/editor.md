# The editing UI

```
python scripts/editor.py ep01            # opens http://127.0.0.1:8765
python scripts/editor.py ep01 --port 9000 --no-browser
```

Python standard library only (http.server); the page is `scripts/editor.html`. It reads
`shots.json` and `edit.json`, fills missing caption timings from the audio on first load, and
saves every change back to `edit.json` half a second after you stop (the "saved" pill in the
header tells you). `edit.py` renders from the same file, so UI and command line are
interchangeable.

![editor](editor.jpg)

## Layout

- **Preview** (top left): the whole programme plays as one sequence — clips switch automatically
  at their trim points, the caption overlay shows the active line in the chosen language. The
  timecode is programme time; the grey text shows which shot/take and the time inside that take.
- **Inspector** (top right): details of whatever is selected in the timeline.
- **Timeline** (bottom): a ruler, one **clip track** (filmstrip of each take), an **EN caption
  track** and a **ZH caption track**. Skipped shots sit greyed out after the end of the programme
  so they can be brought back.

## Timeline gestures

| Do | Effect |
|---|---|
| Click the ruler, or drag along it | Move the playhead / scrub |
| Click a clip | Select it (inspector: take, skip, in/out, volume ±dB, prompt) |
| Drag a clip's **left edge** | Trim the head (`trim.in`); everything after shifts left |
| Drag a clip's **right edge** | Trim the tail (`trim.out`) |
| Drag a caption block | Move it (start and end together), kept inside its clip |
| Drag a caption's left/right edge | Change its start / end |
| Click a caption | Select it (inspector: times, EN and ZH text, delete) |
| Zoom slider / **fit** | Pixels per second / fit the whole programme |

Caption blocks are shown in both language tracks; a dashed block means that language has no text
yet. Times are stored relative to the untrimmed take, so trimming a clip never moves its captions.

## Volume

Every take is levelled to −16 LUFS when the editor starts (`takes/leveled/`), so clips already
sit at the same loudness in the preview. The **volume** slider in a clip's inspector adds
−12…+12 dB on top (stored as `gain` in `edit.json`, previewed live through Web Audio, applied
identically on export); a gold `+3 dB` badge on the clip block shows it is set.

## Keyboard

| Key | Action |
|---|---|
| `Space` | Play / pause |
| `←` `→` | Nudge the selected caption by one step (header "step"); with nothing selected, move the playhead |
| `I` / `O` | Set the current clip's in / out point at the playhead |
| `Delete` | Delete the selected caption |

## Buttons

- **+ caption at playhead** — new 2 s caption in the current clip.
- **auto-time this clip** — re-run the silence detection for the clip under the playhead; Chinese
  text already written for identical English lines is kept.
- **Export EN / Export ZH / Export both** — saves, renders `<output>_<lang>.mp4` in the
  background, and links the file when done.

## Workflow that works

1. Press **fit**, play from the start once with the EN overlay on. Most guesses are within a
   second; drag the blocks that lead or lag.
2. For a line that starts late, scrub to the first syllable and press *start = playhead* in the
   inspector (or drag the block's left edge).
3. Trim dead air at clip heads (H3 often opens on a half-second of stillness) and the tail after
   the last line by dragging clip edges.
4. Fill the Chinese column (or let Claude write it into `edit.json`, then polish here).
5. Export EN, watch it once with sound, then Export ZH.

Browser note: media only loads in a visible tab; a hidden/background automation window shows a
black preview although everything else works.

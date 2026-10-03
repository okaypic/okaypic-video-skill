# `shots.json` — the shot list

One file per episode. `gen_clips.py` renders it; `edit.py` cuts it in this order.

```json
{
  "style": "Photorealistic cinematic near-future urban drama, moody low-key lighting, shallow depth of field, subtle film grain.",
  "seeds": [1, 2],
  "duration": 10,
  "resolution": "768p",
  "ratio": "16:9",
  "shots": [
    {
      "id": "01",
      "refs": ["victor_human", "kessler"],
      "prompt": "Interior, a luxurious rooftop lounge at night ... The man from <Picture 1> ... the bald bearded man from <Picture 2> ... \"Goblins. Sure. How much do I buy?\" Deadpan, snappy timing."
    },
    {
      "id": "22",
      "refs": ["victor_goblin"],
      "first_frame": "frames/22.png",
      "duration": 8,
      "prompt": "The candlelit underground market. A crowd of goblins ..."
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `style` | Prepended to every prompt. Keep it one sentence; it is what makes the episode look like one film. |
| `seeds` | How many takes per shot and their seed suffix. Take letters are `a, b, c…`; seed = `1000 + 10 × shot id + n`. Two takes is the sweet spot. |
| `duration` / `resolution` / `ratio` | Defaults for every shot (`duration` can be overridden per shot). 1–15 s; 480p / 768p / 1080p (1080p: ≤ 10 s, omni only). |
| `shots[].id` | Numeric string, unique. Order in the array is the cut order; ids don't have to be sorted (insert "26" after "10" when you add a shot later). |
| `shots[].refs` | Sheet names from `refs/sheets/<name>.png`, becoming `<Picture 1>`, `<Picture 2>`… in that order. Up to 9. Empty for pure scenery. |
| `shots[].prompt` | Plain English, see [prompting-h3.md](prompting-h3.md). Dialogue in double quotes — `edit.py` extracts those as the captions. |
| `shots[].first_frame` | Optional image (local path or https URL) locked as the opening frame (ref_mode `okay`). Locked frames are **not** numbered as pictures. |

## Writing the prompt

Place → action beat by beat → each line of dialogue in `"..."` with who says it and how
→ sound. Example that rendered well:

> The same back alley at night under orange sodium lamps. The goblin from <Picture 1> shivers in
> the dumpster with the suit jacket wrapped around him. The manhole cover lifts fully and the old
> goblin from <Picture 2>, in a green doorman's coat with brass buttons, pushes his head and
> shoulders up into the light and grins. Old goblin, raspy, warm, amused: "You'll freeze in that
> jacket, Your Excellency." The goblin from <Picture 1>, thin and scared: "Who are you?" Old
> goblin: "The doorman. Down here's warmer. Bring the coin."

Rules of thumb:

- ≤ 12 words per spoken line; 2–3 lines per 10 s shot.
- Name the voice every time ("raspy, warm", "flat TV-news tone", "thin, cracking, panicked").
- "No dialogue. Only his breathing." is a valid line — silence is a choice, not an omission.
- Describe screens and signs by what they show, not by their text; overlay real text in post.
- Say "the same lounge" / "the same alley" for continuity between shots.

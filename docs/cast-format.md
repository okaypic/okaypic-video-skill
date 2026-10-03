# `cast.json` — who and where to draw

`gen_sheets.py` turns this into reference sheets in `refs/sheets/<name>.png`. The names are what
`shots.json` lists in `refs`.

```json
{
  "style": "a grounded cinematic live-action style, low-key warm practical lighting, shallow depth of field, subtle film grain",
  "cast": {
    "victor_human": {
      "look": "a white man of 32, tall and slim, a thick mop of dark brown curly hair, pale skin, strong dark brows, sharp cheekbones, clean-shaven, a serious slightly sullen expression, wearing a slim-cut bespoke navy suit, crisp white shirt, dark red silk tie, black oxford shoes and a gold luxury wristwatch",
      "height_cm": 186,
      "build": "slim",
      "ref": "refs/victor_photo.jpg"
    },
    "victor_goblin": {
      "look": "a goblin, hunched and wiry, grey-green wrinkled skin, huge pointed ears, long nose, big pale eyes, thin needle-like teeth, a messy tuft of dark brown curls between the ears, wearing a dark red silk tie knotted over a white dress shirt that hangs to his knees, a navy suit jacket draped over his shoulders like a cape trailing on the floor, bare feet, a gold wristwatch hanging loose on his thin wrist",
      "height_cm": 120,
      "build": "slim"
    }
  },
  "places": {
    "lounge": {"look": "a luxurious rooftop lounge at night: floor-to-ceiling glass, pink and blue neon city outside, a champagne tower, low leather sofas, floating holographic screens"}
  }
}
```

| Field | Meaning |
|---|---|
| `style` | Appended to every sheet prompt so sheets and clips share one look. Use the same wording as `shots.json` "style". |
| `cast.<name>.look` | One sentence of **visible** facts: ethnicity, age, build, hair, face, outfit, accessories. No personality, no backstory — models can't draw those. |
| `height_cm`, `build` | Written into the prompt ("about 186 cm tall with a slim build; draw true body proportions"). `build`: slim / average / athletic / sturdy / heavy. Without it, everybody comes out average. |
| `ref` | Optional image (local path or https URL) the sheet must match: a photo, an earlier sheet, a sketch. |
| `places.<name>.look` | Materials, light sources, signature furniture. The sheet is a 2×2 FRONT / TOP-DOWN / BACK / SIDE grid of the **empty** place. |

## What a character sheet looks like

16:9, pure white background. Left column: front close-up and 90° profile. Right: front, side,
back full-body at the same scale. One image carries everything a video model needs, and it is
what you show the user for approval before spending on clips.

## Lessons

- **Write the ethnicity.** A name does not tell the model anything; "Nadia Volkov" without
  "Eastern European" came out East Asian on the first try.
- **Two characters must not look alike.** If the founder and the investor are both "a man in his
  50s with grey hair", give one a bald head, a beard, glasses and a different build.
- **One anchor per character** that survives any scene: a red tie, a hair tie, a tattoo. It is
  how the audience recognises a character after a transformation, and how you check consistency
  on a contact sheet.
- **Positive phrasing only.** "clean white background", not "no text": naming a thing summons it.
- A creature that was a person keeps something: for a human → goblin arc, draw both sheets and
  repeat the anchor (the same tie, the same curls between the ears).

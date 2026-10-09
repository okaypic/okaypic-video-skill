"""Character / location reference sheets through the okaypic image API.

    python gen_sheets.py <episode_dir> [name ...]        # default: every entry in cast.json
    python gen_sheets.py <episode_dir> --model gemini-3.1-flash-image-preview
    python gen_sheets.py <episode_dir> --prompts-only   # write refs/sheets/<name>.prompt.txt, render nothing
    python gen_sheets.py <episode_dir> --missing        # only entries without a sheet yet

--prompts-only is for agents that can make images themselves (Codex has gpt-image-2.5 built in):
render each prompt with the agent's own tool, save it as refs/sheets/<name>.png, and the rest of
the pipeline uses it like any other sheet. This script's API rendering is the fallback.

<episode_dir>/cast.json describes who to draw:
    {
      "style": "a grounded cinematic live-action style, low-key warm practical lighting",
      "cast": {
        "victor_human": {"look": "a white man of 32, tall and slim, dark brown curly hair, ...",
                         "height_cm": 186, "build": "slim", "ref": "refs/victor_photo.jpg"},
        "gil":          {"look": "an old goblin, 115 cm, hunched, grey-green wrinkled skin, ...",
                         "height_cm": 115, "build": "slim"}
      },
      "places": {
        "lounge": {"look": "a rooftop lounge at night, floor-to-ceiling glass, neon city outside, ..."}
      }
    }

Sheets are written to <episode_dir>/refs/sheets/<name>.png. A character sheet is one 16:9 image:
front and profile close-ups on the left, front / side / back full-body views on the right, on a
white background, so one image carries everything a video model needs to keep the character
consistent. A place sheet is a 2x2 grid: FRONT / TOP-DOWN / BACK / SIDE of an empty location.
Pass "ref" (a local image or https URL) to pin a face or outfit you already have.

Default model gpt-image-2.5 at 2k (US$0.03). gemini-3.1-flash-image-preview is cheaper and fine.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okaypic_api import data_uri, download, poll, submit_image  # noqa: E402

BUILD = {"slim": "slim", "average": "average", "athletic": "athletic", "sturdy": "stocky, sturdy",
         "heavy": "heavy-set, large"}


def character_prompt(look, height_cm=None, build=None, style="", with_ref=False):
    size = ""
    if height_cm:
        size = (f" The person is about {height_cm} cm tall"
                + (f" with a {BUILD.get(build, build)} build" if build else "")
                + "; draw true body proportions, scaled uniformly to fit each panel, so a tall slender person stays tall and slender.")
    ref = (" The reference image shows this exact person: keep the same face, skin, hair, outfit and accessories in every view."
           if with_ref else "")
    return re.sub(r"\s+", " ", (
        "A character reference sheet, 16:9 landscape, seamless pure white background, soft even studio lighting. "
        "Left column, two stacked panels: top, a front-facing head-and-shoulders close-up at eye level, calm neutral "
        "expression, lips closed, looking into the camera; bottom, a strict 90-degree side-profile close-up of the same face. "
        "Right side, three full-body views standing side by side: front, strict 90-degree side, and back. Each full-body "
        "view shows the whole person from the top of the head to the soles of the shoes with a little white margin above "
        "and below; all three at the same scale, same height, same camera distance and same light, only the facing "
        "direction changes, arms relaxed at the sides. "
        f"The person: {look}.{size} "
        "Identical outfit, hairstyle, accessories and marks in every view. One single person shown from several angles, "
        f"the only subject in the image.{ref} {style}. Clean frame containing only the depicted subject."
    )).strip()


def place_prompt(look, style=""):
    return re.sub(r"\s+", " ", (
        "A location reference sheet, 16:9 landscape, divided into four equal panels in a 2x2 grid with thin white gutters. "
        "Each panel has a small clean English label in its top-left corner. "
        'Top-left panel labeled "FRONT": an eye-level wide view standing at the south side looking north. '
        'Top-right panel labeled "TOP-DOWN": a straight-down overhead view from the ceiling, north at the top, showing the whole floor layout. '
        'Bottom-left panel labeled "BACK": an eye-level wide view standing at the north side looking south. '
        'Bottom-right panel labeled "SIDE": an eye-level wide view standing at the west side looking east. '
        "All four panels show the same empty, deserted place with the same furniture in the same positions, the same materials and the same lighting. "
        f"The place: {look}. {style}."
    )).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode_dir")
    ap.add_argument("names", nargs="*")
    ap.add_argument("--model", default="gpt-image-2.5")
    ap.add_argument("--resolution", default="2k", help="gpt-image-2.5 / seedream only: 1k, 2k, 4k")
    ap.add_argument("--take", type=int, default=1, help="bump to regenerate with a fresh idempotency key")
    ap.add_argument("--prompts-only", action="store_true", help="write the prompts, do not call the API")
    ap.add_argument("--missing", action="store_true", help="skip entries that already have a sheet")
    a = ap.parse_args()

    ep = a.episode_dir
    cast = json.load(open(os.path.join(ep, "cast.json"), encoding="utf-8"))
    style = cast.get("style", "a grounded cinematic live-action style")
    out_dir = os.path.join(ep, "refs", "sheets")
    os.makedirs(out_dir, exist_ok=True)

    jobs = {}
    entries = [("character", n, c) for n, c in cast.get("cast", {}).items()] + \
              [("place", n, p) for n, p in cast.get("places", {}).items()]
    for kind, name, c in entries:
        if a.names and name not in a.names:
            continue
        if a.missing and os.path.exists(os.path.join(out_dir, f"{name}.png")):
            continue
        ref = c.get("ref")
        if kind == "character":
            prompt = character_prompt(c["look"], c.get("height_cm"), c.get("build"), style, with_ref=bool(ref))
        else:
            prompt = place_prompt(c["look"], style)
        body = {"model": a.model, "prompt": prompt, "ratio": "16:9"}
        if a.model in ("gpt-image-2.5", "doubao-seedream-5.0"):
            body["resolution"] = a.resolution
        if ref:
            body["images"] = [ref if ref.startswith("https://") else data_uri(os.path.join(ep, ref))]
        with open(os.path.join(out_dir, f"{name}.prompt.txt"), "w", encoding="utf-8") as f:
            f.write(prompt)
        if a.prompts_only:
            note = f" (reference image: {ref})" if ref else ""
            print(f"prompt {name}: {os.path.join(out_dir, name + '.prompt.txt')}{note}", flush=True)
            continue
        tid = submit_image(body, f"{os.path.basename(os.path.abspath(ep))}-sheet-{name}-{a.take}")
        jobs[name] = tid
        print("submitted", name, flush=True)

    for name, tid in jobs.items():
        r = poll("image", tid)
        if r.get("status") == "completed":
            path = download(r["resultUrls"][0], os.path.join(out_dir, f"{name}.png"))
            with open(os.path.join(out_dir, "urls.txt"), "a", encoding="utf-8") as f:
                f.write(f"{name} {r['resultUrls'][0]}\n")
            print("done", name, path, flush=True)
        else:
            print("FAILED", name, r.get("errorCode"), r.get("errorMessage"), flush=True)


if __name__ == "__main__":
    main()

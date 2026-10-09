"""Render an episode's shots with MiniMax H3 through the okaypic API.

    python gen_clips.py <episode_dir>              # every shot x every seed
    python gen_clips.py <episode_dir> 01 03 17     # only these shot ids
    python gen_clips.py <episode_dir> --quote      # price what is left to render, submit nothing

<episode_dir>/shots.json:
    {
      "style": "Photorealistic cinematic near-future urban drama, moody low-key lighting.",
      "seeds": [1, 2],                       # takes per shot: a, b, ... (seed = 1000 + 10*shot + n)
      "duration": 10, "resolution": "768p", "ratio": "16:9",
      "shots": [
        {"id": "01", "refs": ["victor_human", "kessler"], "prompt": "... the man from <Picture 1> ..."},
        {"id": "22", "refs": ["victor_goblin"], "first_frame": "frames/22.png", "prompt": "..."}
      ]
    }

`refs` name sheets in <episode_dir>/refs/sheets/<name>.png; they are inlined (downscaled to
2048 px) and become <Picture 1>, <Picture 2>... in that order. A shot with `first_frame`
(a local image or https URL) is rendered in ref_mode "okay": that frame is locked as the opening
frame while the sheets are still used as references (locked frames are not numbered).

Resumable: state lives in <episode_dir>/takes/state.json. Re-running skips finished takes and
keeps polling submitted ones (both already paid), and quotes and submits only what is left.
Failed renders are refunded by the API; a retryable failure is resubmitted once under a new
client_request_id. A submit whose answer was lost (crash, timeout) is resent with the same
client_request_id, which the API answers with the original task instead of charging again.
Before submitting, the balance is checked against the remaining cost; on HTTP 402 the script
stops submitting, prints the top-up link and keeps polling what is already in flight. At most MAX_INFLIGHT generations run at once (the account cap is
20). Each finished take gets a 5-frame contact sheet (<take>.jpg) next to the mp4 so you can
pick takes without watching every clip.
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from okaypic_api import TOP_UP_URL, balance_cents, data_uri, download, h3_cost_cents, request, usd  # noqa: E402
from edit import level_take  # noqa: E402

MAX_INFLIGHT = 18
POLL_SECONDS = 20
INFLIGHT = ("pending", "processing", "queued", "submitted")


def contact_sheet(mp4):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-vf", "fps=1/2,scale=320:-1,tile=5x1",
                    "-frames:v", "1", mp4[:-4] + ".jpg"])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    quote_only = "--quote" in sys.argv
    ep = args[0]
    only = set(args[1:])
    spec = json.load(open(os.path.join(ep, "shots.json"), encoding="utf-8"))
    takes_dir = os.path.join(ep, "takes")
    os.makedirs(takes_dir, exist_ok=True)
    state_path = os.path.join(takes_dir, "state.json")
    state = json.load(open(state_path, encoding="utf-8")) if os.path.exists(state_path) else {}
    tag = os.path.basename(os.path.abspath(ep))

    def save():
        json.dump(state, open(state_path, "w", encoding="utf-8"), indent=1)

    work = []
    for shot in spec["shots"]:
        if only and shot["id"] not in only:
            continue
        for i, n in enumerate(spec.get("seeds", [1])):
            work.append((f"{shot['id']}_{'abcdef'[i]}", shot, 1000 + int(shot["id"]) * 10 + n))

    def shot_cost(shot):
        return h3_cost_cents(spec.get("resolution", "768p"), shot.get("duration", spec.get("duration", 10)))

    def to_submit():
        out = []
        for k, shot, _ in work:
            st = state.get(k, {})
            if st.get("status") == "completed" or st.get("status") in INFLIGHT:
                continue
            if st.get("status") == "failed" and (st.get("attempt", 1) >= 2 or st.get("retryable") is False):
                continue
            out.append((k, shot))
        return out

    # quote only what is left: finished and in-flight takes are already paid
    left = to_submit()
    cost = sum(shot_cost(s) for _, s in left)
    done = sum(1 for k, _, _ in work if state.get(k, {}).get("status") == "completed")
    flying = sum(1 for k, _, _ in work if state.get(k, {}).get("status") in INFLIGHT)
    bal = balance_cents()
    print(f"{len(work)} takes: {done} done, {flying} in flight (already paid), {len(left)} to render = {usd(cost)}"
          + (f"; balance {usd(bal)}" if bal is not None else ""), flush=True)
    if quote_only:
        return
    out_of_funds = False
    if left and bal is not None and bal < cost:
        print(f"Not enough balance for the remaining takes ({usd(cost)} needed, {usd(bal)} left). "
              f"Top up from US$2 at {TOP_UP_URL} and re-run; finished takes are kept.", flush=True)
        if not flying:
            return
        out_of_funds = True  # just finish what is in flight

    ref_cache = {}

    def ref(name):
        if name not in ref_cache:
            ref_cache[name] = data_uri(os.path.join(ep, "refs", "sheets", f"{name}.png"))
        return ref_cache[name]

    while True:
        for k in [k for k, s in state.items() if s.get("status") in INFLIGHT]:
            code, r = request("GET", f"/api/video/tasks/{state[k]['taskId']}")
            if code != 200:
                print(f"poll {k}: http {code} {r}", flush=True)
                continue
            if r.get("status") == "completed":
                mp4 = os.path.join(takes_dir, f"{k}.mp4")
                download(r["resultUrls"][0], mp4)
                contact_sheet(mp4)
                try:
                    level_take(mp4)  # -16 LUFS copy in takes/leveled/ for the editor and the cut
                except Exception as e:
                    print(f"level {k}: {e}", flush=True)
                state[k].update(status="completed", url=r["resultUrls"][0])
                print(f"done {k}", flush=True)
            elif r.get("status") == "failed":
                state[k].update(status="failed", error=r.get("errorCode"), retryable=r.get("retryable"))
                print(f"FAILED {k}: {r.get('errorCode')} {r.get('errorMessage', '')} retryable={r.get('retryable')}", flush=True)
            else:
                state[k]["status"] = r.get("status") or "pending"
            save()

        inflight = [k for k, s in state.items() if s.get("status") in INFLIGHT]
        for k, shot, seed in ([] if out_of_funds else work):
            st = state.get(k, {})
            if st.get("status") == "completed" or k in inflight:
                continue
            if st.get("status") == "failed" and (st.get("attempt", 1) >= 2 or st.get("retryable") is False):
                continue
            if len(inflight) >= MAX_INFLIGHT:
                break
            attempt = st.get("attempt", 0) + 1
            body = {
                "model": "minimax-h3", "prompt": spec.get("style", "") + " " + shot["prompt"],
                "duration": shot.get("duration", spec.get("duration", 10)),
                "ratio": spec.get("ratio", "16:9"), "resolution": spec.get("resolution", "768p"),
                "ref_mode": "omni", "optimize_prompt": True, "seed": seed,
                "client_request_id": f"{tag}-{k}-{attempt}",
            }
            media = [{"type": "image", "url": ref(n)} for n in shot.get("refs", [])]
            if media:
                body["media"] = media
            ff = shot.get("first_frame")
            if ff:
                body["ref_mode"] = "okay"
                body["first_frame"] = ff if ff.startswith("https://") else data_uri(os.path.join(ep, ff), max_px=0)
            code, r = request("POST", "/api/video/generate", body, body["client_request_id"])
            if code in (200, 201, 202) and r.get("taskId"):
                state[k] = {"status": "submitted", "taskId": r["taskId"], "seed": seed, "attempt": attempt}
                inflight.append(k)
                print(f"submitted {k} seed={seed}", flush=True)
            elif code == 402:
                out_of_funds = True
                print(f"Balance ran out ({usd(r.get('balanceCents', 0))} left, this take costs "
                      f"{usd(r.get('costCents', 0))}). Top up from US$2 at {TOP_UP_URL} and re-run; "
                      "nothing already rendered or in flight is charged again.", flush=True)
                break
            else:
                state[k] = {"status": "failed", "attempt": attempt, "retryable": True, "error": r}
                print(f"SUBMIT ERROR {k}: http {code} {r}", flush=True)
                if code == 429:
                    break
            save()

        inflight = [k for k, s in state.items() if s.get("status") in INFLIGHT]
        remaining = [k for k, _, _ in work if state.get(k, {}).get("status") != "completed"]
        if not inflight:
            print(f"ALL DONE. completed={len(work) - len(remaining)}/{len(work)} failed={remaining}", flush=True)
            break
        print(f"... {len(inflight)} in flight, {len(remaining)} remaining", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

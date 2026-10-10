"""Tiny okaypic.com API client shared by the other scripts. Python stdlib only.

Reads OKAYPIC_API_KEY (and optional OKAYPIC_API_BASE, default https://okaypic.com) from the
environment or from a .env file found in the current directory or any parent.

    from okaypic_api import submit_image, submit_video, poll, download

Every call sends `client_request_id` as the Idempotency-Key, so a retried request never creates
(or charges for) a second task.
"""
import base64
import json
import math
import mimetypes
import os
import subprocess
import time
import urllib.error
import urllib.request

DEFAULT_BASE = "https://okaypic.com"
TOP_UP_URL = "https://okaypic.com/billing"

# MiniMax H3 list prices, US cents per second of output (https://okaypic.com/pricing)
H3_CENTS_PER_SECOND = {"480p": 5 / 7, "768p": 1.0, "1080p": 15 / 7}


def h3_cost_cents(resolution, seconds):
    return math.ceil(H3_CENTS_PER_SECOND.get(resolution, 1.0) * seconds)


def usd(cents):
    return f"US${cents / 100:.2f}"


class TopUpNeeded(SystemExit):
    """The account balance does not cover the request (HTTP 402)."""

    def __init__(self, cost_cents=None, balance_cents=None):
        msg = "Your okaypic balance is too low for this"
        if cost_cents is not None and balance_cents is not None:
            msg += f" ({usd(cost_cents)} needed, {usd(balance_cents)} left)"
        super().__init__(msg + f". Top up from US$2 at {TOP_UP_URL} (card or WeChat Pay), then re-run: "
                         "finished work is kept and never charged again.")


def balance_cents():
    """Current balance in US cents, or None if the API could not be reached."""
    code, r = request("GET", "/api/balance")
    return r.get("balanceCents") if code == 200 else None


def load_env():
    """Return (base, key). Looks in os.environ first, then .env files up the tree."""
    env = dict(os.environ)
    d = os.getcwd()
    for _ in range(6):
        p = os.path.join(d, ".env")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break
        d = os.path.dirname(d)
    key = env.get("OKAYPIC_API_KEY")
    if not key:
        raise SystemExit("OKAYPIC_API_KEY is not set (export it or put it in a .env file). "
                         "Get a key at https://okaypic.com/api-docs")
    return env.get("OKAYPIC_API_BASE", DEFAULT_BASE).rstrip("/"), key


def _curl(method, url, headers, body):
    cmd = ["curl", "-s", "-X", method, url, "-w", "\n%{http_code}", "--max-time", "180"]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    tmp = None
    if body is not None:
        tmp = f".okaypic_req_{os.getpid()}.json"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
        cmd += ["--data-binary", "@" + tmp]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=200).stdout
        text, _, code = out.rpartition("\n")
        return int(code or 0), (json.loads(text) if text.strip() else {})
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


def request(method, path, body=None, idempotency_key=None):
    """HTTP call to the API. Tries urllib, falls back to curl (some Windows setups time out
    in urllib's TLS handshake while curl works). Returns (status_code, json)."""
    base, key = load_env()
    url = base + path
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    data = json.dumps(body) if body is not None else None
    try:
        req = urllib.request.Request(url, data=data.encode() if data else None, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")
    except Exception:
        return _curl(method, url, headers, data)


def data_uri(path, max_px=2048):
    """Inline a local image as a base64 data URI (the API stores it on its CDN).
    Large images are downscaled with ffmpeg so reference uploads stay small."""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    src = path
    if max_px:
        small = path + f".{max_px}.jpg"
        if not os.path.exists(small):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path,
                            "-vf", f"scale='min({max_px},iw)':-2", "-q:v", "3", small], check=True)
        src, mime = small, "image/jpeg"
    with open(src, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def submit_image(body, client_request_id):
    body = {**body, "client_request_id": client_request_id}
    code, r = request("POST", "/api/image/generate", body, client_request_id)
    if code == 402:
        raise TopUpNeeded(r.get("costCents"), r.get("balanceCents"))
    if code not in (200, 201, 202) or not r.get("taskId"):
        raise RuntimeError(f"image submit failed: http {code} {r}")
    return r["taskId"]


def submit_video(body, client_request_id):
    body = {**body, "client_request_id": client_request_id}
    code, r = request("POST", "/api/video/generate", body, client_request_id)
    if code == 402:
        raise TopUpNeeded(r.get("costCents"), r.get("balanceCents"))
    if code not in (200, 201, 202) or not r.get("taskId"):
        raise RuntimeError(f"video submit failed: http {code} {r}")
    return r["taskId"]


def poll(kind, task_id, every=15, timeout=3600):
    """Block until the task completes. kind = "image" | "video". Returns the task JSON."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        code, r = request("GET", f"/api/{kind}/tasks/{task_id}")
        if code == 200 and r.get("status") in ("completed", "failed"):
            return r
        time.sleep(every)
    raise TimeoutError(f"{kind} task {task_id} still running after {timeout}s")


def download(url, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    try:
        urllib.request.urlretrieve(url, path)
    except Exception:
        subprocess.run(["curl", "-s", "-L", "-o", path, "--max-time", "600", url], check=True)
    return path


def project_tag(ep):
    """The prefix of every client_request_id for this episode folder, kept in <ep>/.okaypic-id.

    Idempotency keys are per account and permanent, so two projects whose episode folders are both
    called "ep01" must not produce the same ids: the second would get the first one's old results
    back. New folders get "<name>-<random>"; folders that already have takes or sheets keep the
    plain folder name they were rendered under, so resuming them still matches."""
    path = os.path.join(ep, ".okaypic-id")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    name = os.path.basename(os.path.abspath(ep))
    sheets = os.path.join(ep, "refs", "sheets")
    started = os.path.exists(os.path.join(ep, "takes", "state.json")) or (
        os.path.isdir(sheets) and any(f.endswith(".png") for f in os.listdir(sheets)))
    tag = name if started else f"{name}-{os.urandom(3).hex()}"
    with open(path, "w", encoding="utf-8") as f:
        f.write(tag + chr(10))
    return tag

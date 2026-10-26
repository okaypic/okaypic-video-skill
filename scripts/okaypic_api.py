"""Tiny okaypic.com API client shared by the other scripts. Python stdlib only.

Reads OKAYPIC_API_KEY (and optional OKAYPIC_API_BASE, default https://okaypic.com) from the
environment, a .env file in the current directory or any parent, or ~/.okaypic/key (where
`save_key` puts the key an x402 USDC payment returned — no account needed, see X402_DOCS below).

Budget guardrail: every paid submit is priced first with the free POST /api/quote. When this
project's spending (ledger: .okaypic-spend.json in the working directory, reset after 12 h) plus
the next call would pass OKAYPIC_MAX_SPEND_USD (default 5.00; "off" disables it), the script stops
with BudgetExceeded so the agent asks the user before spending more.

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
X402_DOCS = "https://okaypic.com/api.md#pay-per-request-with-x402-no-api-key"
KEY_FILE = os.path.join(os.path.expanduser("~"), ".okaypic", "key")
LEDGER = ".okaypic-spend.json"
LEDGER_TTL_SECONDS = 12 * 3600
DEFAULT_MAX_SPEND_USD = "5.00"

# MiniMax H3 list prices, US cents per second of output (https://okaypic.com/pricing)
H3_CENTS_PER_SECOND = {"480p": 5 / 7, "768p": 1.0, "1080p": 15 / 7}


#: Surcharge for the `effort` tier (a better render). Well under the
#: render-time multiple — 2x renders ~1.9x slower and costs 1.6x. Mirrors
#: okaypic's GET /v1/api/effort; that endpoint is what actually bills, and the
#: rates are a trial setting that will move once real usage comes in.
#: ⚠️ 1080p has no tiers (no in-house path there) — sending one returns 400.
H3_EFFORT_SURCHARGE = {"1x": 1.0, "1.5x": 1.3, "2x": 1.6}


def h3_cost_cents(resolution, seconds, effort="1x"):
    rate = H3_CENTS_PER_SECOND.get(resolution, 1.0)
    return math.ceil(rate * H3_EFFORT_SURCHARGE.get(effort, 1.0) * seconds)


def usd(cents):
    return f"US${cents / 100:.2f}"


class TopUpNeeded(SystemExit):
    """The account balance does not cover the request (HTTP 402)."""

    def __init__(self, cost_cents=None, balance_cents=None):
        msg = "Your okaypic balance is too low for this"
        if cost_cents is not None and balance_cents is not None:
            msg += f" ({usd(cost_cents)} needed, {usd(balance_cents)} left)"
        super().__init__(msg + f". Top up from US$2 at {TOP_UP_URL} (card or WeChat Pay), or pay with USDC "
                         f"from an agent wallet (x402: POST /api/agent/topup?amount=5, see {X402_DOCS}), then "
                         "re-run: finished work is kept and never charged again.")


class BudgetExceeded(SystemExit):
    """The next paid call would pass OKAYPIC_MAX_SPEND_USD for this project."""

    def __init__(self, spent, cost, limit):
        super().__init__(
            f"Budget stop: this project has spent {usd(spent)} of its {usd(limit)} limit and the next call costs "
            f"{usd(cost)}. Ask the user before spending more; to continue, re-run with a higher "
            f"OKAYPIC_MAX_SPEND_USD (e.g. {(limit + max(cost, 100)) / 100:.2f}). Nothing was charged for this call.")


def balance_cents():
    """Current balance in US cents, or None if the API could not be reached."""
    code, r = request("GET", "/api/balance")
    return r.get("balanceCents") if code == 200 else None


_ENV = None


def env_vars():
    """os.environ plus the nearest .env file up the tree (environment wins)."""
    global _ENV
    if _ENV is not None:
        return _ENV
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
    _ENV = env
    return env


def load_env():
    """Return (base, key): OKAYPIC_API_KEY from the environment / .env, else ~/.okaypic/key."""
    env = env_vars()
    key = env.get("OKAYPIC_API_KEY")
    if not key and os.path.exists(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as f:
            key = f.read().strip()
    if not key:
        raise SystemExit(
            "No okaypic API key. Either create one at https://okaypic.com/developer (OKAYPIC_API_KEY in the "
            "environment or .env), or pay with USDC from an agent wallet, no account needed: with any x402 "
            "client, POST https://api.okaypic.com/api/agent/topup?amount=5 (Base, Solana, Polygon, Arbitrum, "
            "Avalanche or Monad), then save the apiKey it returns with: python scripts/okaypic_api.py save-key "
            f"okpk_... — details: {X402_DOCS}")
    return env.get("OKAYPIC_API_BASE", DEFAULT_BASE).rstrip("/"), key


def save_key(key):
    """Store a key (e.g. the one an x402 payment returned) in ~/.okaypic/key."""
    if not key.startswith("okpk_"):
        raise SystemExit("That does not look like an okaypic API key (okpk_...).")
    os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key + chr(10))
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass
    return KEY_FILE


# ---- budget ----

def budget_limit_cents():
    raw = str(env_vars().get("OKAYPIC_MAX_SPEND_USD", DEFAULT_MAX_SPEND_USD)).strip().lower()
    if raw in ("off", "none", "0", "unlimited"):
        return None
    try:
        return round(float(raw) * 100)
    except ValueError:
        return round(float(DEFAULT_MAX_SPEND_USD) * 100)


def _ledger():
    try:
        with open(LEDGER, encoding="utf-8") as f:
            led = json.load(f)
        if time.time() - led.get("started", 0) < LEDGER_TTL_SECONDS:
            return led
    except (OSError, ValueError):
        pass
    return {"started": time.time(), "requests": {}}


def spent_cents():
    return sum(_ledger()["requests"].values())


def budget_left_cents():
    """Cents left under OKAYPIC_MAX_SPEND_USD for this project (None = no limit)."""
    limit = budget_limit_cents()
    return None if limit is None else max(0, limit - spent_cents())


def quote_cents(kind, body):
    """Free price of a generate request (POST /api/quote), in cents; None if it could not be priced."""
    code, r = request("POST", "/api/quote", {k: v for k, v in body.items() if k != "client_request_id"})
    return r.get("costCents") if code == 200 else None


def _guard(kind, body, client_request_id):
    """Stop before a paid call that would pass the budget. Returns the quoted cents (or None)."""
    led = _ledger()
    if client_request_id in led["requests"]:
        return None  # a retry of a call already counted (and never charged twice)
    limit = budget_limit_cents()
    if limit is None:
        return None
    cost = quote_cents(kind, body)
    if cost is not None and sum(led["requests"].values()) + cost > limit:
        raise BudgetExceeded(sum(led["requests"].values()), cost, limit)
    return cost


def _record(client_request_id, cents):
    if cents is None:
        return
    led = _ledger()
    led["requests"][client_request_id] = cents
    with open(LEDGER, "w", encoding="utf-8") as f:
        json.dump(led, f)


record_spend = _record  # for scripts that call request() directly (gen_clips.py)


def claim_url():
    """For an account an x402 payment created: the link that moves it to the user's Google login."""
    code, r = request("GET", "/api/agent/account")
    return r.get("claimUrl") if code == 200 else None


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


_use_curl = False


def request(method, path, body=None, idempotency_key=None):
    """HTTP call to the API. Tries urllib, falls back to curl (some Windows setups time out
    in urllib's TLS handshake while curl works). Returns (status_code, json)."""
    base, key = load_env()
    url = base + path
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    global _use_curl
    data = json.dumps(body) if body is not None else None
    if _use_curl:
        return _curl(method, url, headers, data)
    try:
        req = urllib.request.Request(url, data=data.encode() if data else None, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")
    except Exception:
        _use_curl = True  # urllib's TLS stalls on some setups: use curl for the rest of the run
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
    cost = _guard("image", body, client_request_id)
    code, r = request("POST", "/api/image/generate", body, client_request_id)
    if code == 402:
        raise TopUpNeeded(r.get("costCents"), r.get("balanceCents"))
    if code not in (200, 201, 202) or not r.get("taskId"):
        raise RuntimeError(f"image submit failed: http {code} {r}")
    _record(client_request_id, cost)
    return r["taskId"]


def submit_video(body, client_request_id):
    body = {**body, "client_request_id": client_request_id}
    cost = _guard("video", body, client_request_id)
    code, r = request("POST", "/api/video/generate", body, client_request_id)
    if code == 402:
        raise TopUpNeeded(r.get("costCents"), r.get("balanceCents"))
    if code not in (200, 201, 202) or not r.get("taskId"):
        raise RuntimeError(f"video submit failed: http {code} {r}")
    _record(client_request_id, cost)
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


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "save-key":
        print("saved", save_key(sys.argv[2].strip()))
    elif len(sys.argv) == 2 and sys.argv[1] == "budget":
        left = budget_left_cents()
        print(f"spent {usd(spent_cents())} this session; " + ("no limit" if left is None else f"{usd(left)} left of {usd(budget_limit_cents())}"))
    else:
        print("usage: python okaypic_api.py save-key okpk_...   |   python okaypic_api.py budget")

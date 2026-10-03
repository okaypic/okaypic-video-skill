"""Local editing UI for an episode: pick takes, trim clips, nudge captions, export en/zh.

    python editor.py <ep> [--port 8765]

Opens http://127.0.0.1:8765 . Everything it changes is written to <ep>/edit.json, the same file
edit.py renders from, so the UI and the command line stay interchangeable. Python stdlib only.
"""
import argparse
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import edit as editlib  # noqa: E402

STATE = {"ep_dir": None, "durations": {}, "export": {"running": False, "log": [], "lang": None}}


def takes_for(ep_dir, sid):
    d = os.path.join(ep_dir, "takes")
    if not os.path.isdir(d):
        return []
    return sorted(f[len(sid) + 1:-4] for f in os.listdir(d) if f.startswith(sid + "_") and f.endswith(".mp4"))


def duration(path):
    if path not in STATE["durations"]:
        STATE["durations"][path] = editlib.probe_duration(path)
    return STATE["durations"][path]


def project():
    ep_dir = STATE["ep_dir"]
    spec, cfg = editlib.load(ep_dir)
    if editlib.fill_missing_captions(ep_dir, spec, cfg):
        editlib.save_cfg(ep_dir, cfg)
    shots = []
    for s in spec["shots"]:
        takes = takes_for(ep_dir, s["id"])
        shots.append({
            "id": s["id"], "prompt": s["prompt"], "refs": s.get("refs", []), "takes": takes,
            "durations": {t: duration(os.path.join(ep_dir, "takes", f"{s['id']}_{t}.mp4")) for t in takes},
        })
    return {"ep": os.path.basename(ep_dir), "shots": shots, "edit": cfg}


def run_export(lang):
    st = STATE["export"]
    st.update(running=True, log=[], lang=lang)
    try:
        editlib.render(STATE["ep_dir"], lang, log=lambda m: st["log"].append(str(m)))
    except BaseException as e:  # SystemExit from edit.py included
        st["log"].append(f"ERROR: {e}")
    finally:
        st["running"] = False


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # quieter console
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            html = open(os.path.join(ROOT, "editor.html"), "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif path == "/api/project":
            self.send_json(project())
        elif path == "/api/status":
            self.send_json(STATE["export"])
        elif path.startswith("/poster/"):
            # One frame per take so the page shows 28 stills without opening 28 video streams
            # (browsers allow ~6 connections per host; 28 <video preload> tags would stall).
            name = os.path.basename(path)
            if not re.fullmatch(r"[\w.-]+\.jpg", name):
                return self.send_error(404)
            jpg = os.path.join(STATE["ep_dir"], "takes", "posters", name)
            if not os.path.exists(jpg):
                os.makedirs(os.path.dirname(jpg), exist_ok=True)
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.5",
                                "-i", os.path.join(STATE["ep_dir"], "takes", name[:-4] + ".mp4"),
                                "-frames:v", "1", "-vf", "scale=480:-1", jpg])
            if not os.path.exists(jpg):
                return self.send_error(404)
            data = open(jpg, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path.startswith("/takes/") or path.startswith("/out/"):
            name = os.path.basename(path)
            if not re.fullmatch(r"[\w.-]+\.mp4", name):
                return self.send_error(404)
            sub = "takes" if path.startswith("/takes/") else ""
            self.send_file(os.path.join(STATE["ep_dir"], sub, name))
        else:
            self.send_error(404)

    def send_file(self, fp):
        """Serve an mp4 with Range support so <video> can seek."""
        if not os.path.exists(fp):
            return self.send_error(404)
        size = os.path.getsize(fp)
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(fp, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (ConnectionAbortedError, BrokenPipeError):
                    return
                left -= len(chunk)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n).decode() or "{}")
        ep_dir = STATE["ep_dir"]
        if path == "/api/save":
            editlib.save_cfg(ep_dir, body)
            self.send_json({"ok": True})
        elif path == "/api/autotime":
            spec, cfg = editlib.load(ep_dir)
            sid = body["shot"]
            shot = next(s for s in spec["shots"] if s["id"] == sid)
            take = body.get("take") or cfg.get("picks", {}).get(sid, "a")
            mp4 = os.path.join(ep_dir, "takes", f"{sid}_{take}.mp4")
            self.send_json({"captions": editlib.auto_captions(mp4, shot["prompt"])})
        elif path == "/api/export":
            if STATE["export"]["running"]:
                return self.send_json({"ok": False, "error": "export already running"}, 409)
            lang = body.get("lang", "en")
            threading.Thread(target=run_export, args=(lang,), daemon=True).start()
            self.send_json({"ok": True})
        else:
            self.send_error(404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ep")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    STATE["ep_dir"] = os.path.abspath(a.ep if os.path.isdir(a.ep) else os.path.join(ROOT, a.ep))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"editor for {STATE['ep_dir']} at {url}", flush=True)
    if not a.no_browser:
        webbrowser.open(url)
    srv.serve_forever()


if __name__ == "__main__":
    main()

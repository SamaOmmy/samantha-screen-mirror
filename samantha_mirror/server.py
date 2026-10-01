"""Flask app.

Public: the web app's own files (no secrets in them) and POST /api/login.
Everything else (/stream, /api/*) needs the token.
"""
import io
from pathlib import Path

import mss
from flask import Flask, Response, abort, jsonify, make_response, redirect, request, send_from_directory
from PIL import Image

from . import __version__
from .auth import COOKIE, Auth
from .capture import FrameSource
from .config import LIMITS, Config

BOUNDARY = "frame"
COOKIE_MAX_AGE = 30 * 24 * 3600
WEB_DIR = Path(__file__).resolve().parent / "web"
PUBLIC_ENDPOINTS = {"index", "static", "login"}


def _monitors():
    with mss.MSS() as sct:
        return [
            {"index": i, "width": m["width"], "height": m["height"],
             "label": "All monitors" if i == 0 else f"Monitor {i}"}
            for i, m in enumerate(sct.monitors)
        ]


def _parse_settings(data, monitor_count):
    """Validate a settings update. Returns (changes, error)."""
    if not isinstance(data, dict):
        return None, "expected a JSON object"
    changes = {}
    for key, value in data.items():
        if key == "cursor":
            if not isinstance(value, bool):
                return None, "cursor must be true or false"
            changes[key] = value
        elif key == "monitor":
            if type(value) is not int or not 0 <= value < monitor_count:
                return None, f"monitor must be an integer 0-{monitor_count - 1}"
            changes[key] = value
        elif key in LIMITS:
            lo, hi = LIMITS[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None, f"{key} must be a number"
            value = float(value) if key == "scale" else int(value)
            if not lo <= value <= hi:
                return None, f"{key} must be between {lo} and {hi}"
            changes[key] = value
        else:
            return None, f"unknown setting {key!r}"
    return changes, None


def create_app(cfg: Config, bind_ip: str = "") -> Flask:
    # Addresses the HTTPS proxy (`tailscale serve`) connects from.
    proxies = {bind_ip, "127.0.0.1"} if cfg.loopback else {bind_ip}
    app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
    auth = Auth(cfg.token)
    source = FrameSource(cfg.monitor, cfg.fps, cfg.jpeg_quality, cfg.scale, cfg.cursor, cfg.capture)

    def client_ip():
        # Behind `tailscale serve` every request comes from our own address, so the
        # real client is in X-Forwarded-For. Only trusted when it came from ourselves.
        if request.remote_addr in proxies:
            forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            if forwarded:
                return forwarded
        return request.remote_addr or "?"

    def set_cookie(resp, token):
        https = request.headers.get("X-Forwarded-Proto") == "https" and request.remote_addr in proxies
        resp.set_cookie(COOKIE, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="Strict",
                        secure=https, path="/")
        return resp

    @app.before_request
    def require_token():
        ip = client_ip()
        if auth.locked_out(ip):
            abort(429)
        # Opening the page with ?token=... sets the cookie and drops the token from the URL.
        if request.endpoint == "index" and request.args.get("token"):
            if auth.valid(request.args["token"]):
                return set_cookie(redirect("/"), request.args["token"])
            auth.record_failure(ip)
            return None  # fall through to the login screen
        if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
            return None
        ok, _ = auth.check(request)
        if not ok:
            auth.record_failure(ip)
            abort(401)

    @app.after_request
    def security_headers(resp):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'none'; img-src 'self' blob:; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'"
        )
        return resp

    @app.errorhandler(401)
    @app.errorhandler(404)
    @app.errorhandler(429)
    @app.errorhandler(503)
    def plain_error(err):
        return Response(err.name, status=err.code, mimetype="text/plain")

    # -- web app -------------------------------------------------------------
    @app.get("/")
    def index():
        if not (WEB_DIR / "index.html").exists():
            return Response("Web app not built. Run: cd web && npm install && npm run build",
                            status=500, mimetype="text/plain")
        return send_from_directory(WEB_DIR, "index.html")

    @app.post("/api/login")
    def login():
        data = request.get_json(silent=True) or {}
        token = data.get("token", "") if isinstance(data, dict) else ""
        if not isinstance(token, str) or not auth.valid(token.strip()):
            auth.record_failure(client_ip())
            return jsonify(error="Wrong token"), 401
        return set_cookie(make_response(jsonify(ok=True)), token.strip())

    @app.post("/api/logout")
    def logout():
        resp = make_response(jsonify(ok=True))
        resp.delete_cookie(COOKIE, path="/")
        return resp

    # -- API -----------------------------------------------------------------
    @app.get("/api/state")
    def state():
        # Polled by the page: its frame counters show whether the stream is stuck.
        return jsonify(source.state() | {"settings": source.settings(), "version": __version__})

    @app.get("/api/monitors")
    def monitors():
        return jsonify(monitors=_monitors(), limits=LIMITS, max_clients=cfg.max_clients)

    @app.post("/api/settings")
    def settings():
        changes, error = _parse_settings(request.get_json(silent=True), len(_monitors()))
        if error:
            return jsonify(error=error), 400
        source.configure(**changes)
        return jsonify(source.settings())

    @app.get("/api/screenshot")
    def screenshot():
        """Full-resolution PNG of the selected monitor, independent of the stream settings."""
        index = source.settings()["monitor"]
        with mss.MSS() as sct:
            if index >= len(sct.monitors):
                abort(404)
            shot = sct.grab(sct.monitors[index])
        buf = io.BytesIO()
        Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX").save(buf, "PNG")
        resp = Response(buf.getvalue(), mimetype="image/png")
        resp.headers["Content-Disposition"] = 'attachment; filename="screenshot.png"'
        return resp

    @app.get("/stream")
    def stream():
        if source.client_count() >= cfg.max_clients:
            abort(503)
        source.add_client()

        def generate():
            last = -1
            idle = 0
            try:
                while True:
                    item = source.wait_frame(last)
                    if item is None:
                        # Nothing new. A long silence while capture is failing ends the
                        # stream so the page retries; on a static screen, resend the frame
                        # now and then so a vanished viewer is noticed (the write fails).
                        idle += 1
                        if idle >= 6 and source.state()["error"]:
                            return
                        if idle % 2 == 0:
                            item = source.wait_frame(-1, timeout=0)
                        if item is None:
                            continue
                    else:
                        idle = 0
                    last, jpeg = item
                    yield (
                        b"--" + BOUNDARY.encode() + b"\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                        + jpeg + b"\r\n"
                    )
            finally:
                source.remove_client()

        resp = make_response(Response(generate(), mimetype=f"multipart/x-mixed-replace; boundary={BOUNDARY}"))
        resp.headers["X-Accel-Buffering"] = "no"
        return resp

    return app

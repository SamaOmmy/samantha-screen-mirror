"""Flask app. Every route (including static files) requires the token."""
from flask import Flask, Response, abort, jsonify, make_response, redirect, request, send_from_directory

from .auth import COOKIE, Auth
from .capture import FrameSource
from .config import Config

BOUNDARY = "frame"
COOKIE_MAX_AGE = 30 * 24 * 3600


def create_app(cfg: Config) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    auth = Auth(cfg.token)
    source = FrameSource(cfg.monitor, cfg.fps, cfg.jpeg_quality, cfg.scale)

    @app.before_request
    def require_token():
        ip = request.remote_addr or "?"
        if auth.locked_out(ip):
            abort(429)
        token, from_query = auth.extract(request)
        if not auth.valid(token):
            auth.record_failure(ip)
            abort(401)
        # First visit via ?token=...: set the cookie and drop the token from the URL.
        if from_query and request.method == "GET" and request.path == "/":
            resp = redirect("/")
            resp.set_cookie(
                COOKIE, token, max_age=COOKIE_MAX_AGE,
                httponly=True, samesite="Strict", path="/",
            )
            return resp

    @app.after_request
    def security_headers(resp):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'none'; img-src 'self'; script-src 'self'; "
            "style-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        return resp

    @app.errorhandler(401)
    @app.errorhandler(429)
    def plain_error(err):
        return Response(err.name, status=err.code, mimetype="text/plain")

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/status")
    def status():
        # The page polls this to detect a stalled stream and reconnect.
        return jsonify(seq=source.seq, viewers=source.client_count())

    @app.get("/stream")
    def stream():
        if source.client_count() >= cfg.max_clients:
            abort(503)
        source.add_client()

        def generate():
            last = -1
            try:
                while True:
                    item = source.wait_frame(last)
                    if item is None:
                        continue
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

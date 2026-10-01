# screen-mirror

View your Windows PC screen live in your phone's browser, over [Tailscale](https://tailscale.com), from any network. No cloud services: traffic goes PC <-> phone only, inside your tailnet.

**Phase 1: view-only.** Python + `mss` (capture) + Flask/waitress (MJPEG stream) + a small mobile page.

## Security model

- The server binds **only** to your Tailscale IP (from `tailscale ip -4`). If it can't find one in `100.64.0.0/10`, it exits. It never listens on `0.0.0.0`.
- Every route needs a secret token (`SM_TOKEN` in `.env`). It's checked in constant time; 10 bad attempts in 5 min locks that IP out (HTTP 429).
- Traffic is plain HTTP, but Tailscale's WireGuard tunnel encrypts it between your devices.

## Setup (Windows)

Requirements: Python 3.10+ and Tailscale running on the PC and signed in on the phone (same tailnet).

```powershell
cd screen-mirror
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

Paste the generated string into `.env` as `SM_TOKEN=...`.

## Run

```powershell
.\.venv\Scripts\python.exe run.py
```

It prints the URL to open on your phone. Stop it with Ctrl+C.

## Test from your phone

1. Make sure the Tailscale app on the phone is **connected** (you can turn Wi-Fi off and use mobile data to prove it works from any network).
2. Open the URL printed by `run.py`: `http://<tailscale-ip>:8787/?token=<your token>`.
3. The first visit stores the token in a cookie and redirects to a clean URL, so later you can just open `http://<tailscale-ip>:8787/`.
4. You should see your screen, with a green dot and "Live". Turn the phone's connection off and on to see it auto-reconnect.

If the page doesn't load, you may need a Windows Firewall rule. Run PowerShell **as Administrator**:

```powershell
New-NetFirewallRule -DisplayName "screen-mirror (Tailscale only)" -Direction Inbound `
  -Protocol TCP -LocalPort 8787 -RemoteAddress 100.64.0.0/10 -Action Allow
```

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `SM_TOKEN` | *(required)* | Access secret, min 16 chars |
| `SM_PORT` | 8787 | Port on the Tailscale IP |
| `SM_MONITOR` | 1 | mss monitor index (0 = all monitors combined) |
| `SM_FPS` | 15 | Frames per second (1-60) |
| `SM_JPEG_QUALITY` | 60 | 10-95; lower = smaller |
| `SM_SCALE` | 0.5 | 0.1-1.0 resolution scale; lower saves mobile data |
| `SM_MAX_CLIENTS` | 3 | Max simultaneous viewers |

Rough data use at the defaults on a 1280x720 screen: about 0.5 MB/s while connected. For mobile data try `SM_SCALE=0.4`, `SM_JPEG_QUALITY=45`, `SM_FPS=8`. Frames are sent even when the screen is unchanged.

## Notes

- **Fullscreen:** the button uses the Fullscreen API. iPhone Safari doesn't support it for normal pages, so there it falls back to hiding the toolbar (tap the screen to show it again). "Add to Home Screen" also gives a fuller view.
- Capture only runs while someone is watching.
- The page treats a frozen frame counter as a dropped stream and reconnects with backoff.

## Layout

```
run.py              entry point
mirror/config.py    .env settings + validation
mirror/netbind.py   Tailscale IP detection
mirror/capture.py   shared capture thread (mss -> scale -> JPEG)
mirror/auth.py      token check + lockout
mirror/server.py    Flask routes: /, /stream, /status
mirror/static/      mobile page (html/css/js)
```

Phase 2 (touch/keyboard control) can add an input module and a control endpoint behind the same auth.

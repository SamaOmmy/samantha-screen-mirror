# screen-mirror

View your Windows PC screen live in your phone's browser, over [Tailscale](https://tailscale.com), from any network. No cloud services: traffic goes PC <-> phone only, inside your tailnet.

**View-only** for now. Python + `mss` (capture) + Flask/waitress (MJPEG stream) + a React web app for the phone (installable, with a settings panel).

## Security model

- The server binds **only** to your Tailscale IP (from `tailscale ip -4`). If it can't find one in `100.64.0.0/10`, it exits. It never listens on `0.0.0.0`.
- The stream and every `/api` route need a secret token (`SM_TOKEN` in `.env`). It's checked in constant time; 10 bad attempts in 5 min locks that IP out (HTTP 429). Only the app's own files (no secrets) are public, so the login screen can load.
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

**Without typing commands:** run `.\autostart.ps1 install` once. The server then starts hidden at every Windows logon (`remove` undoes it, `status` checks it). Logs go to `screen-mirror.log`. After this, just open the app on your phone.

## Use it from your phone

1. Make sure the Tailscale app on the phone is **connected** (mobile data works too).
2. Open `http://<tailscale-ip>:8787/` and enter the token once (or open the `?token=` link printed by `run.py`, which signs you in directly).
3. In the app: tap to hide/show the bars, pinch to zoom, drag to pan, double-tap to reset. **Settings** has quality presets (Data saver / Balanced / Sharp), screen picker, fps/quality/resolution sliders and the pointer toggle. **Screenshot** saves a full-resolution PNG.
4. Add it to the home screen for an app-like icon (Share > Add to Home Screen on iPhone; browser menu on Android).

Chrome's "Install app" prompt and offline caching only work over HTTPS; plain `http://100.x.y.z` is not a secure context, so there the app still works but is a shortcut. For full install, enable HTTPS in the Tailscale admin console and put `tailscale serve` in front (not set up here).

If the page doesn't load, you may need a Windows Firewall rule. Run PowerShell **as Administrator**:

```powershell
New-NetFirewallRule -DisplayName "screen-mirror (Tailscale only)" -Direction Inbound `
  -Protocol TCP -LocalPort 8787 -RemoteAddress 100.64.0.0/10 -Action Allow
```

## Changing the web app

The built app is committed in `mirror/web/`, so you don't need Node to run the project. To edit it (needs Node 20+):

```powershell
cd web
npm install
npm run build    # writes ../mirror/web
SM_TARGET=http://<tailscale-ip>:8787 npm run dev   # live reload, proxies /api and /stream
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
| `SM_CURSOR` | 1 | Draw the mouse pointer on the stream |

Fps, quality, scale, screen and pointer can also be changed live from the app (shared by all viewers, reset on restart); `.env` holds the startup defaults.

Rough data use at the defaults on a 1280x720 screen: about 0.5 MB/s while connected. For mobile data try `SM_SCALE=0.4`, `SM_JPEG_QUALITY=45`, `SM_FPS=8`. Frames are only sent when something on screen changed, so a static screen costs almost nothing.

## Notes

- **Fullscreen:** uses the Fullscreen API; iPhone Safari doesn't support it for normal pages, so there it just hides the bars.
- Capture only runs while someone is watching.
- If the PC is locked or showing a UAC prompt, capture fails; the app shows "PC screen unavailable" and recovers on its own.
- The page treats a stalled server frame counter as a dropped stream and reconnects with backoff.

## Layout

```
run.py              entry point (logging, waits for Tailscale, friendly errors)
autostart.ps1       start at logon via Task Scheduler
mirror/config.py    .env settings + validation
mirror/netbind.py   Tailscale IP detection
mirror/capture.py   shared capture thread (mss -> change detection -> scale -> JPEG)
mirror/auth.py      token check + lockout
mirror/server.py    Flask routes: app files, /stream, /api/*
mirror/web/         built React app (generated from web/)
web/                React + TypeScript source (Vite)
```

Next up: touch/keyboard control can add an input module and a control endpoint behind the same auth.

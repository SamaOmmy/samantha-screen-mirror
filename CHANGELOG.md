# Changelog

## 0.3.0 (unreleased)

- Renamed to **Samantha Screen Mirror**; Python package is now `samantha_mirror`, command is `samantha-mirror`.
- New command line: `setup` (guided first run), `link` (QR code + phone steps), `doctor` (health check),
  `autostart install|remove|status`, `uninstall`.
- `install.ps1` one-step installer.
- Settings and token live in `%APPDATA%\SamanthaScreenMirror` (or the project folder when run from a checkout; `SM_HOME` overrides).
- Optional HTTPS through `tailscale serve`, so the phone can install the app as a real PWA.
- Much faster capture: DXGI Desktop Duplication (fallback: mss) and OpenCV encoding.
  About 29 fps at 1440x810 and about 14 ms median latency in testing.
- React web app: login, pinch-zoom, live settings, screenshots, install help, keeps the phone awake while viewing,
  clear message when the PC cannot be reached.
- Tests and CI.

## 0.1.0

- First view-only version: MJPEG stream over Tailscale with token auth.

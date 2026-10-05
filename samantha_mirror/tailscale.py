"""Talk to the local Tailscale CLI: find our address, check HTTPS, set up `tailscale serve`.

The server binds ONLY to the Tailscale address, so everything here is about finding it
safely and (optionally) putting Tailscale's HTTPS in front of it.
"""
import ipaddress
import json
import shutil
import subprocess
from pathlib import Path

from . import proc

# Tailscale assigns addresses from the CGNAT range 100.64.0.0/10.
TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
_WINDOWS_DEFAULT = Path(r"C:\Program Files\Tailscale\tailscale.exe")
HTTPS_PORTS = (443, 8443, 10000)  # the ports `tailscale serve` can use for HTTPS

DOWNLOAD_URL = "https://tailscale.com/download"
ADMIN_DNS_URL = "https://login.tailscale.com/admin/dns"
PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=com.tailscale.ipn"
APP_STORE_URL = "https://apps.apple.com/app/tailscale/id1470499037"


class BindError(Exception):
    pass


def find_cli():
    """Path to tailscale.exe, or None if it isn't installed."""
    found = shutil.which("tailscale")
    if found:
        return found
    return str(_WINDOWS_DEFAULT) if _WINDOWS_DEFAULT.exists() else None


def _cli() -> str:
    path = find_cli()
    if not path:
        raise BindError("Tailscale CLI not found. Is Tailscale installed?")
    return path


def run(*args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return proc.run([_cli(), *args], capture_output=True, text=True, timeout=timeout)


def status() -> dict:
    """Parsed `tailscale status --json`. Raises BindError if Tailscale isn't usable."""
    try:
        out = run("status", "--json")
        return json.loads(out.stdout)
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        raise BindError(f"Could not read Tailscale status: {exc}. Is Tailscale running?")


def backend_state(st: dict) -> str:
    """Running, NeedsLogin, Stopped, Starting, ..."""
    return st.get("BackendState", "Unknown")


def dns_name(st: dict) -> str:
    return (st.get("Self") or {}).get("DNSName", "").rstrip(".")


def https_enabled(st: dict) -> bool:
    return bool(st.get("CertDomains"))


def tailscale_ip() -> str:
    try:
        out = run("ip", "-4", timeout=10)
        if out.returncode != 0:
            raise subprocess.SubprocessError(out.stderr.strip() or f"exit code {out.returncode}")
    except (subprocess.SubprocessError, OSError) as exc:
        raise BindError(f"`tailscale ip -4` failed: {exc}. Is Tailscale running and logged in?")

    lines = out.stdout.split()
    if not lines:
        raise BindError("`tailscale ip -4` returned nothing. Is Tailscale connected?")
    try:
        addr = ipaddress.ip_address(lines[0])
    except ValueError:
        raise BindError(f"Unexpected output from tailscale: {lines[0]!r}")
    if addr not in TAILSCALE_NET:
        # Refuse rather than risk binding to a LAN/public address.
        raise BindError(f"{addr} is not in the Tailscale range {TAILSCALE_NET}; refusing to bind.")
    return str(addr)


# -- tailscale serve (HTTPS in front of our local port) -------------------------------------
def serve_map() -> dict:
    """{https_port: proxy_target} for everything currently served over HTTPS."""
    try:
        data = json.loads(run("serve", "status", "--json").stdout or "{}")
    except (BindError, subprocess.SubprocessError, OSError, ValueError):
        return {}
    result = {}
    for hostport, web in (data.get("Web") or {}).items():
        port = int(hostport.rsplit(":", 1)[-1])
        result[port] = (web.get("Handlers") or {}).get("/", {}).get("Proxy", "")
    return result


def https_url(st: dict, local_port: int):
    """The https:// address already proxying to our local port, or None."""
    target = f"http://127.0.0.1:{local_port}"
    for port, proxy in serve_map().items():
        if proxy.rstrip("/") == target:
            return f"https://{dns_name(st)}" + ("" if port == 443 else f":{port}") + "/"
    return None


def enable_https(st: dict, local_port: int) -> str:
    """Point `tailscale serve` at our local port on a free HTTPS port. Never replaces
    someone else's entry. Returns the https URL."""
    existing = https_url(st, local_port)
    if existing:
        return existing
    used = serve_map()
    port = next((p for p in HTTPS_PORTS if p not in used), None)
    if port is None:
        raise BindError("Tailscale Serve already uses ports 443, 8443 and 10000. Free one with "
                        "`tailscale serve --https=<port> off` and try again.")
    out = run("serve", "--bg", f"--https={port}", f"http://127.0.0.1:{local_port}")
    if out.returncode != 0:
        raise BindError(f"`tailscale serve` failed: {(out.stderr or out.stdout).strip()}")
    return f"https://{dns_name(st)}" + ("" if port == 443 else f":{port}") + "/"


def disable_https(st: dict, local_port: int) -> None:
    target = f"http://127.0.0.1:{local_port}"
    for port, proxy in serve_map().items():
        if proxy.rstrip("/") == target:
            run("serve", f"--https={port}", "off")

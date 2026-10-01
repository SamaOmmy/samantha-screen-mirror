"""Find the Tailscale IPv4 address. The server binds ONLY to this address."""
import ipaddress
import shutil
import subprocess
from pathlib import Path

# Tailscale assigns addresses from the CGNAT range 100.64.0.0/10.
TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
_WINDOWS_DEFAULT = Path(r"C:\Program Files\Tailscale\tailscale.exe")


class BindError(Exception):
    pass


def _cli() -> str:
    found = shutil.which("tailscale")
    if found:
        return found
    if _WINDOWS_DEFAULT.exists():
        return str(_WINDOWS_DEFAULT)
    raise BindError("Tailscale CLI not found. Is Tailscale installed?")


def tailscale_ip() -> str:
    try:
        out = subprocess.run(
            [_cli(), "ip", "-4"], capture_output=True, text=True, timeout=10, check=True
        ).stdout
    except (subprocess.SubprocessError, OSError) as exc:
        raise BindError(f"`tailscale ip -4` failed: {exc}. Is Tailscale running and logged in?")

    lines = out.split()
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

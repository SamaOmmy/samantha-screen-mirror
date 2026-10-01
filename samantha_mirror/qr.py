"""Print a QR code in the terminal (so the phone can open the app by scanning)."""
import qrcode


def render(text: str) -> str:
    """Two QR rows per text line using half-block characters."""
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(text)
    qr.make(fit=True)
    m = qr.get_matrix()
    if len(m) % 2:
        m.append([False] * len(m[0]))
    glyph = {(False, False): " ", (True, False): "▀", (False, True): "▄", (True, True): "█"}
    # Dark modules print as blank on a light background: invert so it scans on dark terminals.
    lines = []
    for y in range(0, len(m), 2):
        lines.append("".join(glyph[(not m[y][x], not m[y + 1][x])] for x in range(len(m[0]))))
    return "\n".join(lines)

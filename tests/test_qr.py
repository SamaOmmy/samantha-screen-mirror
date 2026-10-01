from samantha_mirror.qr import render


def test_render_produces_rectangular_block_art():
    lines = render("https://example.ts.net/?token=abc").splitlines()
    assert len(lines) > 10 and len({len(line) for line in lines}) == 1

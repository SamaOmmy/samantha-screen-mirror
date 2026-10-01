import pytest

from samantha_mirror import config


def test_defaults(home, monkeypatch):
    monkeypatch.setenv("SM_TOKEN", "x" * 20)
    cfg = config.load()
    assert (cfg.port, cfg.fps, cfg.jpeg_quality, cfg.scale) == (8787, 30, 70, 0.75)
    assert cfg.cursor is True and cfg.loopback is False and cfg.capture == "auto"


def test_short_token_rejected(home, monkeypatch):
    monkeypatch.setenv("SM_TOKEN", "short")
    with pytest.raises(config.ConfigError, match="SM_TOKEN"):
        config.load()


@pytest.mark.parametrize("name,value", [
    ("SM_FPS", "0"), ("SM_FPS", "abc"), ("SM_SCALE", "2"), ("SM_JPEG_QUALITY", "5"),
    ("SM_PORT", "80"), ("SM_CURSOR", "maybe"), ("SM_CAPTURE", "gpu"),
])
def test_bad_values_rejected(home, monkeypatch, name, value):
    monkeypatch.setenv("SM_TOKEN", "x" * 20)
    monkeypatch.setenv(name, value)
    with pytest.raises(config.ConfigError, match=name):
        config.load()


def test_ensure_env_creates_token_once(home):
    assert config.ensure_env() is True
    text = (home / ".env").read_text(encoding="utf-8")
    token = [line for line in text.splitlines() if line.startswith("SM_TOKEN=")][0].split("=", 1)[1]
    assert len(token) >= config.MIN_TOKEN_LEN
    assert config.ensure_env() is False  # does not rotate an existing token
    assert token in (home / ".env").read_text(encoding="utf-8")


def test_set_env_value_updates_or_appends(home):
    (home / ".env").write_text("# comment\nSM_FPS=15\n", encoding="utf-8")
    config.set_env_value("SM_FPS", "30")
    config.set_env_value("SM_LOOPBACK", "1")
    lines = (home / ".env").read_text(encoding="utf-8").splitlines()
    assert lines == ["# comment", "SM_FPS=30", "SM_LOOPBACK=1"]

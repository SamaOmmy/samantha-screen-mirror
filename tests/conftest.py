import os

import pytest

from samantha_mirror import config

TOKEN = "t" * 32


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Isolated settings folder with no SM_* variables leaking in from the real machine."""
    for key in [k for k in os.environ if k.startswith("SM_")]:
        monkeypatch.delenv(key)
    monkeypatch.setenv("SM_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def cfg(home, monkeypatch):
    monkeypatch.setenv("SM_TOKEN", TOKEN)
    return config.load()


@pytest.fixture
def client(cfg):
    from samantha_mirror.server import create_app
    app = create_app(cfg, "100.64.0.1")
    app.testing = True
    return app.test_client()

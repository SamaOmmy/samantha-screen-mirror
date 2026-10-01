"""Compatibility shim: `python run.py` is the same as `python -m samantha_mirror run`."""
import sys

from samantha_mirror.cli import main

sys.exit(main(["run"]))

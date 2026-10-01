"""Windowless entry point of the packaged app: runs the server (used for start-at-logon)."""
import sys

from samantha_mirror.runner import run_server

sys.exit(run_server())

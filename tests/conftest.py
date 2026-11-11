"""Test defaults: keep code-page verdicts on the deterministic byte probe.

The bundled rizin deep probe is exercised explicitly in test_rizin_probe.py.
"""
import os

os.environ.setdefault("GALTRANSL_RIZIN", "off")

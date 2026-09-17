"""Compatibility entrypoint for the separated administrator application."""

from pathlib import Path
import runpy


runpy.run_path(str(Path(__file__).parent / "admin" / "app.py"), run_name="__main__")

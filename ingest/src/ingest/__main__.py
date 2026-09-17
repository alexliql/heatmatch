"""Entry point for `python -m ingest`.

Preferred over the installed console script: uv's editable-install shim has
repeatedly dropped out of the local venv, and `python -m` with PYTHONPATH=src
works whether or not the package is installed.
"""

from ingest.cli import app

if __name__ == "__main__":
    app()

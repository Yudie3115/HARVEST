"""Regression tests for the catalogue worker entry point."""
import os
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_catalogue_worker_module_entry_point_imports_application():
    """The container/local launch form must be able to import the src package."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.catalogue_worker", "--help"],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "PYTHONPATH": ""},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Process at most one job and exit" in result.stdout


def test_runtime_commands_use_import_safe_module_entry_point():
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text()
    makefile = (REPOSITORY_ROOT / "Makefile").read_text()

    assert "command: python -m scripts.catalogue_worker" in compose
    assert makefile.count("poetry run python -m scripts.catalogue_worker") == 2

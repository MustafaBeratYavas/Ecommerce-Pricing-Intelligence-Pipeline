"""Regression tests for direct source-tree entrypoint execution."""

import subprocess
import sys

from src.definitions import ROOT_DIR


def _run_help(script_path: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, script_path, "--help"],
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )


def test_create_profile_direct_script_uses_repo_imports():
    result = _run_help("src/tasks/create_profile.py")

    assert result.returncode == 0
    assert "Chrome Profile Creator" in result.stdout
    assert ".venv\\Lib\\site-packages\\config\\settings.yaml" not in result.stderr


def test_seed_targets_direct_script_uses_repo_imports():
    result = _run_help("src/tasks/seed_targets.py")

    assert result.returncode == 0
    assert "Database Seeding Utility" in result.stdout
    assert ".venv\\Lib\\site-packages\\config\\settings.yaml" not in result.stderr

"""Unit tests for operational command helpers."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from src.tasks import create_profile, seed_targets


def test_create_chrome_profile_creates_profile_directory(tmp_path, capsys):
    user_data_dir = tmp_path / "browser-data"

    create_profile.create_chrome_profile(str(user_data_dir), "Profile 1")

    assert (user_data_dir / "Profile 1").is_dir()
    assert "Successfully created profile directory" in capsys.readouterr().out


def test_create_chrome_profile_reports_existing_directory(tmp_path, capsys):
    profile_dir = tmp_path / "browser-data" / "Profile 1"
    profile_dir.mkdir(parents=True)

    create_profile.create_chrome_profile(str(tmp_path / "browser-data"), "Profile 1")

    assert "Profile directory already exists." in capsys.readouterr().out


def test_create_chrome_profile_exits_when_directory_creation_fails(monkeypatch):
    monkeypatch.setattr(create_profile.os.path, "exists", lambda _path: False)

    def raise_os_error(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(create_profile.os, "makedirs", raise_os_error)

    with pytest.raises(SystemExit) as exc_info:
        create_profile.create_chrome_profile("browser-data", "Profile 1")

    assert exc_info.value.code == 1


def test_create_profile_main_uses_config_defaults(monkeypatch):
    config = MagicMock()
    config.get.side_effect = [".browser_profile", "Profile 2"]
    create = MagicMock()

    monkeypatch.setattr(create_profile, "Config", lambda: config)
    monkeypatch.setattr(create_profile, "create_chrome_profile", create)
    monkeypatch.setattr(sys, "argv", ["create_profile.py"])

    create_profile.main()

    create.assert_called_once_with(".browser_profile", "Profile 2")


def test_seed_from_file_deduplicates_codes_and_syncs_database(tmp_path, monkeypatch):
    seed_file = tmp_path / "codes.txt"
    seed_file.write_text("RZ01-001 / note\nRZ01-001\nRZ04-002\n\n", encoding="utf-8")
    db = MagicMock()
    db_context = MagicMock()
    db_context.__enter__.return_value = db
    db_context.__exit__.return_value = None

    monkeypatch.setattr(seed_targets, "DatabaseService", lambda: db_context)

    seed_targets.seed_from_file(str(seed_file))

    assert [call.args[0] for call in db.sync_target_product.call_args_list] == [
        "RZ01-001",
        "RZ04-002",
    ]


def test_seed_from_file_continues_when_single_code_fails(tmp_path, monkeypatch, capsys):
    seed_file = tmp_path / "codes.txt"
    seed_file.write_text("RZ01-001\nRZ04-002\n", encoding="utf-8")
    db = MagicMock()
    db.sync_target_product.side_effect = [RuntimeError("database busy"), None]
    db_context = MagicMock()
    db_context.__enter__.return_value = db
    db_context.__exit__.return_value = None

    monkeypatch.setattr(seed_targets, "DatabaseService", lambda: db_context)

    seed_targets.seed_from_file(str(seed_file))

    output = capsys.readouterr().out
    assert "Failed to synchronize 'RZ01-001'" in output
    assert "Successfully synchronized 1 product(s)" in output


def test_seed_from_file_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        seed_targets.seed_from_file(str(tmp_path / "missing.txt"))

    assert exc_info.value.code == 1


def test_seed_from_file_empty_file_warns_without_database(
    tmp_path, monkeypatch, capsys
):
    seed_file = tmp_path / "codes.txt"
    seed_file.write_text("\n", encoding="utf-8")
    database_service = MagicMock()

    monkeypatch.setattr(seed_targets, "DatabaseService", database_service)

    seed_targets.seed_from_file(str(seed_file))

    assert "No valid product codes" in capsys.readouterr().out
    database_service.assert_not_called()


def test_seed_from_file_fatal_read_error_exits(monkeypatch):
    monkeypatch.setattr(seed_targets.os.path, "exists", lambda _path: True)

    def raise_os_error(*_args, **_kwargs):
        raise OSError("read failed")

    monkeypatch.setattr("builtins.open", raise_os_error)

    with pytest.raises(SystemExit) as exc_info:
        seed_targets.seed_from_file("codes.txt")

    assert exc_info.value.code == 1


def test_seed_targets_main_passes_file_argument(monkeypatch):
    seed = MagicMock()

    monkeypatch.setattr(seed_targets, "seed_from_file", seed)
    monkeypatch.setattr(sys, "argv", ["seed_targets.py", "--file", "codes.txt"])

    seed_targets.main()

    seed.assert_called_once_with("codes.txt")

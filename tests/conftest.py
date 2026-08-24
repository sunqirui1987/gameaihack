from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import unity_apk_files, write_zip


@pytest.fixture(autouse=True)
def _configs_env(monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("GAMEAIHACK_CONFIGS", str(repo / "configs"))


@pytest.fixture
def unity_apk(tmp_path: Path) -> Path:
    return write_zip(tmp_path / "unity.apk", unity_apk_files(with_data=True))


@pytest.fixture
def shell_apk(tmp_path: Path) -> Path:
    return write_zip(tmp_path / "shell.apk", unity_apk_files(with_data=False))

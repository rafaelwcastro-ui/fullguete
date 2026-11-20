"""Cada teste usa um banco SQLite novo e o modo simulado, sem chave de API."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def ambiente_isolado(tmp_path, monkeypatch):
    monkeypatch.setenv("FULLGUETE_DB_PATH", str(tmp_path / "teste.db"))
    monkeypatch.setenv("FULLGUETE_MODO", "simulado")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("CNPJ_WS_TOKEN", "")
    yield tmp_path


@pytest.fixture
def base_carregada():
    from banco import semente

    return semente.garantir_base(simulado=True)

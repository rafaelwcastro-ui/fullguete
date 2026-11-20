"""Datas: tudo é gravado em UTC e exibido no horário de Brasília."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")


def agora() -> datetime:
    return datetime.now(UTC)


def iso(momento: datetime | None = None) -> str:
    return (momento or agora()).astimezone(UTC).isoformat(timespec="seconds")


def ler(valor: str | None) -> datetime | None:
    if not valor:
        return None
    momento = datetime.fromisoformat(valor)
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def local(valor: str | datetime | None) -> datetime | None:
    momento = ler(valor) if isinstance(valor, str) or valor is None else valor
    return momento.astimezone(FUSO) if momento else None


def fmt(valor: str | datetime | None, com_hora: bool = True) -> str:
    momento = local(valor)
    if not momento:
        return ""
    return momento.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


def hoje_local() -> date:
    return agora().astimezone(FUSO).date()


def horas_entre(inicio: str | None, fim: str | None) -> float | None:
    a, b = ler(inicio), ler(fim)
    if not a or not b:
        return None
    return (b - a).total_seconds() / 3600


def daqui(horas: float = 0, dias: float = 0) -> str:
    return iso(agora() + timedelta(hours=horas, days=dias))


def inicio_periodo(periodo: str) -> str | None:
    """'hoje', '7 dias', '30 dias' ou 'tudo'."""
    if periodo == "hoje":
        meia_noite = datetime.combine(hoje_local(), datetime.min.time(), tzinfo=FUSO)
        return iso(meia_noite)
    if periodo == "7 dias":
        return daqui(dias=-7)
    if periodo == "30 dias":
        return daqui(dias=-30)
    return None

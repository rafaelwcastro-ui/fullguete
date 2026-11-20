"""Validação e formatação de CNPJ (dígitos verificadores)."""

from __future__ import annotations

import re

_PESOS_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_PESOS_2 = [6, *_PESOS_1]


def so_digitos(valor: object) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _digito(base: str, pesos: list[int]) -> str:
    resto = sum(int(d) * p for d, p in zip(base, pesos, strict=True)) % 11
    return "0" if resto < 2 else str(11 - resto)


def completar(base12: str) -> str:
    """Recebe os 12 primeiros dígitos e devolve o CNPJ com os dois verificadores."""
    base12 = so_digitos(base12)
    if len(base12) != 12:
        raise ValueError("A base do CNPJ precisa de 12 dígitos.")
    d1 = _digito(base12, _PESOS_1)
    return base12 + d1 + _digito(base12 + d1, _PESOS_2)


def valido(valor: object) -> bool:
    cnpj = so_digitos(valor)
    if len(cnpj) != 14 or len(set(cnpj)) == 1:
        return False
    return completar(cnpj[:12]) == cnpj


def formatar(valor: object) -> str:
    cnpj = so_digitos(valor)
    if len(cnpj) != 14:
        return str(valor or "")
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"

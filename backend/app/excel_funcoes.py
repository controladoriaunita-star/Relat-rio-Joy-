"""Equivalentes exatos das funções e comparações do Excel usadas na planilha.

Regras do Excel reproduzidas aqui:
- comparação de texto com "=" ignora maiúsculas/minúsculas, mas respeita espaços;
- célula de data vazia vale 0 (30/12/1899) e EOMONTH(0, 0) = 31/01/1900;
- texto nunca é igual a número.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

DATA_ZERO = date(1899, 12, 30)
MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def como_data(valor) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        texto = valor.strip()[:10]
        for formato in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto, formato).date()
            except ValueError:
                continue
        return None
    if isinstance(valor, (int, float)):            # número serial do Excel
        return date.fromordinal(DATA_ZERO.toordinal() + int(valor))
    return None


def eomonth(valor, meses: int = 0) -> date:
    """EOMONTH(data; meses). Data vazia é tratada como 0, igual ao Excel."""
    base = como_data(valor) or DATA_ZERO
    indice = base.year * 12 + (base.month - 1) + meses
    ano, mes = divmod(indice, 12)
    mes += 1
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def meses_entre(inicio: date, quantidade: int) -> list[date]:
    """Lista de fins de mês a partir de `inicio` (inclusive)."""
    return [eomonth(inicio, i) for i in range(quantidade)]


def como_numero(valor) -> float:
    if valor is None or valor == "" or isinstance(valor, bool):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).replace(",", "."))
    except ValueError:
        return 0.0


def chave_texto(valor) -> str | None:
    """Chave para comparação de texto no estilo Excel; None quando não é texto comparável."""
    if valor is None:
        return None
    return str(valor).casefold()


def texto_igual(a, b) -> bool:
    return a is not None and b is not None and str(a).casefold() == str(b).casefold()


def texto_concat(valor) -> str:
    """Conversão de valor para texto usada pelo operador & do Excel."""
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


def arredondar(valor: float, casas: int) -> float:
    """ROUND do Excel (meio para longe do zero), diferente do round() do Python."""
    quantum = Decimal(1).scaleb(-casas)
    return float(Decimal(repr(valor)).quantize(quantum, rounding=ROUND_HALF_UP))


def texto_mes(data: date, separador: str = "/") -> str:
    """TEXT(data;"mmm/aaaa") em pt-BR, ex.: set/2026."""
    return f"{MESES_ABREV[data.month - 1]}{separador}{data.year}"


def texto_data(data: date) -> str:
    """TEXT(data;"dd/mm/aaaa")."""
    return data.strftime("%d/%m/%Y")

"""Registros normalizados que alimentam o motor de cálculo.

Cada tipo corresponde a uma tabela da planilha (nome entre parênteses) e só traz
as colunas que as fórmulas do Resumo e do Painel usam.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable, Iterable

from ..excel_funcoes import chave_texto


@dataclass(frozen=True)
class Desembolso:            # Custos_SPE e BD_NN_s
    classificacao: str | None
    status: str | None
    data_pagamento: date | None
    fim_mes: date
    valor: float


@dataclass(frozen=True)
class Movimento:             # Controle_Saídas e Controle_Entradas
    classificacao: str | None
    data: date | None
    fim_mes: date
    valor: float
    historico: str | None = None


@dataclass(frozen=True)
class Transferencia:         # bd_transferênciaBancária
    empresa: int | None
    empresa_credito: int | None
    fim_mes: date
    valor: float


@dataclass(frozen=True)
class Recebimento:           # Recebidas
    cliente: int | None
    fim_mes: date
    valor: float


@dataclass(frozen=True)
class SaldoConta:            # Consulta2 (aba Saldo)
    empresa: int | None
    conta: str | None
    data: date
    saldo: float


@dataclass(frozen=True)
class LinhaProjecao:         # Projeção_2
    descricao: str | None
    data: date | None
    tipo: str | None
    valor: float


@dataclass
class Base:
    custos_spe: list[Desembolso] = field(default_factory=list)
    custos_nn: list[Desembolso] = field(default_factory=list)
    saidas: list[Movimento] = field(default_factory=list)
    entradas: list[Movimento] = field(default_factory=list)
    transferencias: list[Transferencia] = field(default_factory=list)
    recebidas: list[Recebimento] = field(default_factory=list)
    saldos: list[SaldoConta] = field(default_factory=list)
    projecao: list[LinhaProjecao] = field(default_factory=list)
    ultima_atualizacao: datetime | None = None

    def __post_init__(self) -> None:
        self._indices: dict[tuple, dict] = {}

    # Índice por chave de texto (classificação ou descrição), montado uma única vez.
    def por_texto(self, tabela: str, atributo: str) -> dict[str | None, list]:
        chave = (tabela, atributo)
        if chave not in self._indices:
            indice: dict[str | None, list] = defaultdict(list)
            for registro in getattr(self, tabela):
                indice[chave_texto(getattr(registro, atributo))].append(registro)
            self._indices[chave] = indice
        return self._indices[chave]

    def filtrar(self, tabela: str, atributo: str, texto) -> list:
        """Registros cujo `atributo` é igual a `texto` (comparação do Excel)."""
        if texto is None:
            return []
        return self.por_texto(tabela, atributo).get(chave_texto(texto), [])


def somar(registros: Iterable, condicao: Callable[[object], bool] | None = None) -> float:
    return sum(r.valor for r in registros if condicao is None or condicao(r))

"""Monta a Base do motor a partir das tabelas brutas de cada fonte."""
from __future__ import annotations

from datetime import datetime

from ..motor.base import Base, LinhaProjecao, SaldoConta
from .definicoes import FONTES
from .normalizacao import ResultadoFonte, montar_depara, normalizar, tabela_para_dicts


def montar_base(tabelas: dict[str, list[list]], depara: dict[str, list[tuple]],
                projecao: list[LinhaProjecao], saldos: list[SaldoConta],
                ultima_atualizacao: datetime | None) -> tuple[Base, dict[str, ResultadoFonte]]:
    resultados = {
        f.codigo: normalizar(f.codigo, tabela_para_dicts(tabelas.get(f.codigo, [])),
                             montar_depara(depara.get(f.codigo, [])))
        for f in FONTES
    }
    base = Base(**{codigo: r.registros for codigo, r in resultados.items()},
                saldos=saldos, projecao=projecao, ultima_atualizacao=ultima_atualizacao)
    return base, resultados

"""Monta a Base do motor a partir das tabelas brutas de cada fonte de uma obra."""
from __future__ import annotations

from datetime import datetime

from ..motor.base import Base, LinhaProjecao
from ..obras import Obra
from .definicoes import FONTES
from .normalizacao import ResultadoFonte, montar_depara, normalizar, tabela_para_dicts


def montar_base(tabelas: dict[str, list[list]], depara: dict[str, list[tuple]],
                projecao: list[LinhaProjecao], ultima_atualizacao: datetime | None,
                obra: Obra | None = None) -> tuple[Base, dict[str, ResultadoFonte]]:
    resultados = {
        f.codigo: normalizar(f.codigo, tabela_para_dicts(tabelas.get(f.codigo, [])),
                             montar_depara(depara.get(f.codigo, [])), obra.empresa_spe if obra else None)
        for f in FONTES
    }
    identificacao = ({"empresa_spe": obra.empresa_spe, "cliente_investidor": obra.cliente_investidor,
                      "historico_aporte_investidor": obra.historico_aporte_investidor} if obra else {})
    base = Base(**{codigo: r.registros for codigo, r in resultados.items()},
                projecao=projecao, ultima_atualizacao=ultima_atualizacao, **identificacao)
    return base, resultados

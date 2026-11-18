"""Aba Aportes: aportes feitos na SPE até a data-base.

  * Investidor: todos os lançamentos da aba Recebidas.
  * Joy+: Transferências Bancárias de outra empresa para a SPE (Empresa_tb ≠ 73 e
    EmpresaCred_tb = 73). Empresa_tb 10 = Joy+, 1 = Unità; qualquer outro código vira
    apontamento para conferência (o valor entra no total da Joy+ como "não identificada").
"""
from __future__ import annotations

from datetime import date

from ..config import EMPRESA_SPE
from .base import Base

EMPRESAS_JOY = {10: "Joy+", 1: "Unità"}


def _data(registro) -> date:
    return registro.data or registro.fim_mes


def aportes_ate(base: Base, hoje: date) -> dict:
    investidor = [{"data": _data(r), "origem": "investidor", "empresa": None, "codigo": r.cliente,
                   "valor": r.valor} for r in base.recebidas if _data(r) <= hoje]
    joy = [{"data": _data(t), "origem": "joy", "empresa": EMPRESAS_JOY.get(t.empresa), "codigo": t.empresa,
            "valor": t.valor}
           for t in base.transferencias
           if t.empresa != EMPRESA_SPE and t.empresa_credito == EMPRESA_SPE and _data(t) <= hoje]
    apontamentos = [a for a in joy if a["empresa"] is None]

    por_empresa = {nome: sum(a["valor"] for a in joy if a["empresa"] == nome) for nome in EMPRESAS_JOY.values()}
    total_investidor = sum(a["valor"] for a in investidor)
    total_joy = sum(a["valor"] for a in joy)
    return {
        "ate": hoje,
        "totais": {"investidor": total_investidor, "joy": total_joy, "geral": total_investidor + total_joy,
                   "joy_por_empresa": por_empresa,
                   "nao_identificada": sum(a["valor"] for a in apontamentos)},
        "lancamentos": sorted(investidor + joy, key=lambda a: (a["data"], a["origem"]), reverse=True),
        "apontamentos": apontamentos,
    }

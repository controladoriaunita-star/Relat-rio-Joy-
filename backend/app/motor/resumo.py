"""Aba Resumo: custos e despesas por rubrica e cálculo do aporte do mês.

Reproduz as fórmulas da aba Resumo da planilha. A célula de origem de cada valor
está indicada no comentário (ex.: H7 = "Pago Total até").
"""
from __future__ import annotations

from datetime import date

from ..catalogo import LINHAS_RESUMO, Premissas
from ..config import EMPRESA_SPE
from ..excel_funcoes import (DATA_ZERO, eomonth, texto_data, texto_igual, texto_mes)
from .base import Base, somar

TIPO_PROJETADO_TOTAL = "Projetado Total"    # Resumo N3


def _ou_zero(data: date | None) -> date:
    return data or DATA_ZERO


def saldo_fim_de_mes(base: Base, fim_mes: date) -> float:
    """Soma do saldo do último dia lançado no mês, por empresa e conta (Consulta2[Coluna1]=1)."""
    ultimo: dict[tuple, date] = {}
    for s in base.saldos:
        chave = (s.empresa, (s.conta or "").casefold(), eomonth(s.data))
        if chave not in ultimo or s.data > ultimo[chave]:
            ultimo[chave] = s.data
    return sum(s.saldo for s in base.saldos
               if eomonth(s.data) == fim_mes
               and s.data == ultimo[(s.empresa, (s.conta or "").casefold(), fim_mes)])


def _projetado(base: Base, rotulo: str, data: date, tipo: str = TIPO_PROJETADO_TOTAL) -> float:
    return somar(base.filtrar("projecao", "descricao", rotulo),
                 lambda p: p.data == data and texto_igual(p.tipo, tipo))


def _pago_ate(base: Base, rotulo: str, mes: date) -> float:          # coluna H
    pago = lambda d: d.fim_mes < mes and texto_igual(d.status, "Pago")
    return (somar(base.filtrar("custos_spe", "classificacao", rotulo), pago)
            + somar(base.filtrar("custos_nn", "classificacao", rotulo), pago)
            + somar(base.filtrar("saidas", "classificacao", rotulo),
                    lambda m: _ou_zero(m.data) < mes))


def _retorno_holding_ate(base: Base, rotulo: str, mes_analise: date) -> float:  # H41
    return (somar(base.transferencias, lambda t: t.empresa == EMPRESA_SPE
                  and t.empresa_credito != EMPRESA_SPE and t.fim_mes <= mes_analise)
            + somar(base.filtrar("saidas", "classificacao", rotulo),
                    lambda m: m.fim_mes <= mes_analise))


def _pago_no_mes(base: Base, rotulo: str, mes: date) -> float:      # coluna J
    pago = lambda d: d.fim_mes == mes and texto_igual(d.status, "Pago")
    return (somar(base.filtrar("custos_spe", "classificacao", rotulo), pago)
            + somar(base.filtrar("custos_nn", "classificacao", rotulo), pago)
            + somar(base.filtrar("saidas", "classificacao", rotulo),
                    lambda m: _ou_zero(m.data) == mes))


def _a_pagar(base: Base, rotulo: str, ate: date) -> float:          # coluna L
    return somar(base.filtrar("custos_spe", "classificacao", rotulo),
                 lambda d: _ou_zero(d.data_pagamento) <= ate and texto_igual(d.status, "A Pagar"))


def _projetado_proximo(base: Base, rotulo: str, mes: date, ate: date) -> float:  # coluna S
    return (_projetado(base, rotulo, eomonth(mes, 1))
            + somar(base.filtrar("custos_spe", "classificacao", rotulo),
                    lambda d: texto_igual(d.status, "A pagar") and d.fim_mes == eomonth(ate, 1)))


def _dividir(a: float, b) -> float | None:
    return a / b if b else None


def _aporte(saldo: float, receita: float, caixa_minimo: float, custo: float):
    """Resumo Z9: aporte necessário; "-" quando o caixa cobre os custos."""
    x = saldo + receita - caixa_minimo - custo
    y = (0 if x > custo else x) * -1
    return "-" if y < 0 else y


def _parcela(valor, percentual: float):
    return valor * percentual if isinstance(valor, (int, float)) else "-"


def calcular_resumo(base: Base, hoje: date, viabilidade: dict[str, float],
                    premissas: Premissas) -> dict:
    mes = eomonth(hoje, 0)                  # B4
    ate = mes                               # L4
    mes_analise = eomonth(hoje, -1)         # AD3 (= Painel D22)

    linhas = []
    for spec in LINHAS_RESUMO:
        linha = {"linha_excel": spec.linha_excel, "rubrica": spec.rotulo, "grupo": spec.grupo}
        if spec.grupo in ("despesa", "custo"):
            linha["viabilidade"] = viabilidade.get(spec.rotulo, 0)
        if spec.tem_pago:
            if spec.linha_excel == 41:
                linha["pago_ate"] = _retorno_holding_ate(base, spec.rotulo, mes_analise)
            else:
                linha["pago_ate"] = _pago_ate(base, spec.rotulo_pago_ate or spec.rotulo, mes)
            linha["pago_mes"] = _pago_no_mes(base, spec.rotulo, mes)
        linha["a_pagar"] = _a_pagar(base, spec.rotulo, ate)
        linha["projetado_mes"] = _projetado(base, spec.rotulo, mes)
        linha["projetado_proximo"] = _projetado_proximo(base, spec.rotulo, mes, ate)
        linha["total_mes"] = linha.get("pago_mes", 0) + linha["a_pagar"]
        if spec.tem_pago:
            linha["pct_consumido"] = _dividir(linha["pago_mes"] + linha["pago_ate"],
                                              linha.get("viabilidade"))
        linhas.append(linha)

    por_linha = {l["linha_excel"]: l for l in linhas}
    soma = lambda campo, de, ate_l: sum(por_linha[r].get(campo) or 0
                                        for r in range(de, ate_l + 1) if r in por_linha)
    por_linha[24]["viabilidade"] = soma("viabilidade", 7, 22)
    por_linha[43]["viabilidade"] = soma("viabilidade", 26, 39)

    total = {campo: soma(campo, 7, 43) for campo in
             ("pago_ate", "pago_mes", "a_pagar", "projetado_mes", "projetado_proximo", "total_mes")}
    total["viabilidade"] = soma("viabilidade", 7, 22) + soma("viabilidade", 26, 41)
    total["pct_consumido"] = _dividir(total["pago_ate"], total["viabilidade"])

    # Bloco "Relatório de Aporte" (colunas Y:Z)
    saldo_anterior = saldo_fim_de_mes(base, eomonth(mes_analise))                 # Z5
    receita_mes = somar(base.entradas, lambda m: m.fim_mes == mes)                # Z6
    custo_mes = sum((por_linha[r].get("pago_mes") or 0) + por_linha[r]["a_pagar"]
                    + por_linha[r]["projetado_mes"] for r in range(7, 42))          # Z7
    aporte_total = _aporte(saldo_anterior, receita_mes, premissas.caixa_minimo, custo_mes)

    saldo_dois_meses = saldo_fim_de_mes(base, eomonth(mes_analise, -1))           # Z13
    valor_recebido = (somar(base.transferencias, lambda t: t.empresa != EMPRESA_SPE
                            and t.empresa_credito == EMPRESA_SPE
                            and t.fim_mes == eomonth(mes_analise))
                      + somar(base.recebidas))                                     # Z14
    pago_e_a_pagar = total["pago_mes"] + total["a_pagar"] + total["projetado_mes"]  # Z15
    saldo_atual = valor_recebido + saldo_dois_meses - pago_e_a_pagar               # Z16
    valor_a_aportar = premissas.aporte_referencia - valor_recebido                 # Z17
    saldo_final = valor_a_aportar + saldo_atual                                    # Z18
    custo_automatico = premissas.custo_projetado_proximo is None
    custo_proximo = (total["projetado_proximo"] if custo_automatico
                     else premissas.custo_projetado_proximo)                       # Z22
    aporte_proximo = premissas.caixa_minimo_proximo - saldo_final + custo_proximo  # Z24

    proximo = eomonth(ate, 1)
    pi, pj = premissas.participacao_investidor, premissas.participacao_joy
    return {
        "datas": {"mes_atual": mes, "mes_analise": mes_analise, "a_pagar_ate": ate,
                  "proximo_mes": proximo},
        "titulos": {
            "pago_ate": f"Pago Total até {texto_data(eomonth(mes, -1))}",
            "pago_mes": f"Pago no Mês {mes.strftime('%m/%Y')}",
            "a_pagar": f"Contas a Pagar até  {texto_data(ate)}",
            "projetado_proximo": f"Projetado  {texto_mes(proximo)}",
            "saldo_anterior": f"Saldo (Mês Anterior) - {texto_mes(eomonth(mes, -1))}",
            "custo_mes": f"Custo Realizado + Projetado (Mês) - {texto_mes(mes_analise, '-')}",
            "valor_recebido": f"Valor Recebido - {texto_mes(mes_analise, '-')}",
            "pago_e_a_pagar": f"Valor Pago e A pagar - {texto_mes(mes_analise, '-')}",
            "saldo_proximo": f"Saldo (Mês Anterior) - {texto_mes(mes)}",
            "custo_proximo": f"Custo Projetado (Mês) - {texto_mes(eomonth(mes_analise, 1), '-')}",
        },
        "linhas": linhas,
        "total": total,
        "aporte_mes": {
            "saldo_anterior": saldo_anterior, "receita_projetada": receita_mes,
            "custo_mes": custo_mes, "caixa_minimo": premissas.caixa_minimo,
            "aporte_total": aporte_total, "investidor": _parcela(aporte_total, pi),
            "joy": _parcela(aporte_total, pj)},
        "conta": {
            "saldo_mes_anterior": saldo_dois_meses, "valor_recebido": valor_recebido,
            "pago_e_a_pagar": pago_e_a_pagar, "saldo_atual": saldo_atual,
            "valor_a_aportar": valor_a_aportar, "saldo_final": saldo_final},
        "aporte_proximo": {
            "saldo_anterior": saldo_final, "receita_projetada": premissas.receita_projetada_proximo,
            "custo_projetado": custo_proximo, "custo_automatico": custo_automatico,
            "caixa_minimo": premissas.caixa_minimo_proximo, "aporte_total": aporte_proximo,
            "investidor": aporte_proximo * pi, "joy": aporte_proximo * pj},
        "aportes_programados": [
            {**a, "investidor": a["valor"] * pi, "joy": a["valor"] * pj}
            for a in premissas.aportes_programados],
        "total_aportes_programados": sum(a["valor"] for a in premissas.aportes_programados),
        "ultima_atualizacao": base.ultima_atualizacao,
    }

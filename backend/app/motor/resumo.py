"""Aba Resumo: custos e despesas por rubrica e cálculo do aporte do mês.

Reproduz as fórmulas da aba Resumo da planilha; a célula de origem está no comentário
(ex.: H7 = "Pago Total até"). Correções aprovadas em relação à planilha (out/2026):

  * Controle Saídas entram pelo mês da data (a planilha só contava como "pago no mês"
    a saída do último dia do mês; as demais caíam em "pago até o mês anterior").
  * Receita do mês exclui entradas classificadas como aporte (aporte não é receita).
  * Conta da SPE é o fluxo do mês: saldo inicial + receitas + aporte − custos. A planilha
    misturava meses (saldo de dois meses antes, todos os recebimentos desde o início e
    uma base fixa de 780.000).
  * Aporte do próximo mês segue a mesma regra do aporte do mês, partindo do saldo final
    projetado e considerando a receita projetada.
  * Receitas do mês = tudo o que a aba Recebidas (SharePoint) registra no mês selecionado
    (out/2026). A Recebidas é o banco de recebimentos da SPE e hoje traz os aportes do
    investidor; quando houver vendas, elas entram pela mesma tabela. Como o que já entrou
    no mês reduz o que falta aportar, o "aporte do mês" passa a ser o aporte ainda necessário.

Regra do aporte: cobrir os custos do mês e terminar com o caixa mínimo; nunca negativo.

    aporte necessário = custos do mês + caixa mínimo − saldo do fim do mês anterior
                        − receitas do mês (Recebidas)
"""
from __future__ import annotations

from datetime import date

from ..catalogo import LINHAS_RESUMO, Premissas
from ..config import CLIENTE_INVESTIDOR, EMPRESA_SPE
from ..excel_funcoes import DATA_ZERO, eomonth, texto_data, texto_igual, texto_mes
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
            + somar(base.filtrar("saidas", "classificacao", rotulo), lambda m: m.fim_mes < mes))


def _retorno_holding_ate(base: Base, rotulo: str, mes_analise: date) -> float:  # H41
    return (somar(base.transferencias, lambda t: t.empresa == EMPRESA_SPE
                  and t.empresa_credito != EMPRESA_SPE and t.fim_mes <= mes_analise)
            + somar(base.filtrar("saidas", "classificacao", rotulo),
                    lambda m: m.fim_mes <= mes_analise))


def _pago_no_mes(base: Base, rotulo: str, mes: date) -> float:      # coluna J
    pago = lambda d: d.fim_mes == mes and texto_igual(d.status, "Pago")
    return (somar(base.filtrar("custos_spe", "classificacao", rotulo), pago)
            + somar(base.filtrar("custos_nn", "classificacao", rotulo), pago)
            + somar(base.filtrar("saidas", "classificacao", rotulo), lambda m: m.fim_mes == mes))


def _a_pagar(base: Base, rotulo: str, ate: date) -> float:          # coluna L
    return somar(base.filtrar("custos_spe", "classificacao", rotulo),
                 lambda d: _ou_zero(d.data_pagamento) <= ate and texto_igual(d.status, "A Pagar"))


def _projetado_proximo(base: Base, rotulo: str, mes: date, ate: date) -> float:  # coluna S
    return (_projetado(base, rotulo, eomonth(mes, 1))
            + somar(base.filtrar("custos_spe", "classificacao", rotulo),
                    lambda d: texto_igual(d.status, "A pagar") and d.fim_mes == eomonth(ate, 1)))


def _dividir(a: float, b) -> float | None:
    return a / b if b else None


def aporte_necessario(saldo: float, receita: float, caixa_minimo: float, custo: float) -> float:
    """Resumo Z9: o que falta para pagar os custos do mês e terminar com o caixa mínimo."""
    return max(0.0, custo + caixa_minimo - saldo - receita)


def cronograma_do_aporte(premissas: Premissas, mes: date, aporte: float, recebidos: float) -> dict:
    """Parcelas do aporte do mês: data, percentual e valor. A última parcela fica com o
    arredondamento, para a soma ser exatamente o aporte. Status pelo que já foi recebido
    fora da Recebidas (transferências da holding): a Recebidas já abateu o aporte."""
    gravadas = premissas.cronogramas_aporte.get(mes.strftime("%Y-%m"))
    parcelas = gravadas or [{"data": mes.replace(day=1).isoformat(), "percentual": 100.0}]
    valores = [round(aporte * p["percentual"] / 100, 2) for p in parcelas]
    valores[-1] = round(aporte - sum(valores[:-1]), 2)
    pi, pj = premissas.participacao_investidor, premissas.participacao_joy
    saida, acumulado = [], 0.0
    for numero, (p, valor) in enumerate(zip(parcelas, valores), 1):
        anterior, acumulado = acumulado, acumulado + valor
        if valor <= 0:
            status = None
        elif recebidos >= acumulado - 0.005:
            status = "recebido"
        elif recebidos > anterior + 0.005:
            status = "parcial"
        else:
            status = "a receber"
        saida.append({"parcela": numero, "data": date.fromisoformat(p["data"]), "percentual": p["percentual"],
                      "valor": valor, "investidor": valor * pi, "joy": valor * pj, "status": status})
    return {"programado": bool(gravadas), "parcelas": saida, "total": aporte, "recebido": recebidos}


def receitas_do_mes(base: Base, mes: date) -> float:
    """Resumo Z6: tudo o que a aba Recebidas registra no mês (qualquer dia do mês, qualquer
    cliente). É a receita usada no cálculo do aporte. Rendimentos de aplicação (Controle
    Entradas) não entram: a fonte de receitas da SPE é a Recebidas."""
    return somar(base.recebidas, lambda r: r.fim_mes == mes)


def _recebidas_do_investidor(base: Base, mes: date) -> float:
    """Parte das receitas do mês que é aporte do investidor (Recebidas do CLIENTE_INVESTIDOR)."""
    return somar(base.recebidas, lambda r: r.fim_mes == mes and r.cliente == CLIENTE_INVESTIDOR)


def _transferencias_da_holding(base: Base, mes: date) -> float:
    """Transferências de outras empresas do grupo para a SPE no mês. São aportes que não
    passam pela Recebidas: não reduzem o aporte necessário e contam como parte dele já recebida."""
    return somar(base.transferencias, lambda t: t.empresa != EMPRESA_SPE
                 and t.empresa_credito == EMPRESA_SPE and t.fim_mes == mes)


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

    # Bloco "Relatório de Aporte" (colunas Y:Z): aporte do mês corrente
    saldo_anterior = saldo_fim_de_mes(base, eomonth(mes_analise))                 # Z5
    receita_mes = receitas_do_mes(base, mes)                                      # Z6 (Recebidas)
    custo_mes = sum((por_linha[r].get("pago_mes") or 0) + por_linha[r]["a_pagar"]
                    + por_linha[r]["projetado_mes"] for r in range(7, 42))          # Z7
    aporte_total = aporte_necessario(saldo_anterior, receita_mes, premissas.caixa_minimo, custo_mes)  # Z9

    # Conta da SPE (Z13:Z18): fluxo do mês. As Recebidas já estão nas receitas; das
    # transferências da holding, o que entrou abate o aporte que ainda falta receber.
    transferencias = _transferencias_da_holding(base, mes)
    saldo_final = saldo_anterior + receita_mes + aporte_total - custo_mes

    # Próximo mês (Z20:Z26): mesma regra, a partir do saldo final projetado
    custo_automatico = premissas.custo_projetado_proximo is None
    custo_proximo = (total["projetado_proximo"] if custo_automatico
                     else premissas.custo_projetado_proximo)                       # Z22
    aporte_proximo = aporte_necessario(saldo_final, premissas.receita_projetada_proximo,
                                       premissas.caixa_minimo_proximo, custo_proximo)  # Z24

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
            "custo_mes": f"Custo Realizado + Projetado (Mês) - {texto_mes(mes)}",
            "saldo_proximo": f"Saldo projetado - fim de {texto_mes(mes)}",
            "custo_proximo": f"Custo Projetado (Mês) - {texto_mes(proximo)}",
        },
        "linhas": linhas,
        "total": total,
        "aporte_mes": {
            "saldo_anterior": saldo_anterior, "receita_mes": receita_mes,
            "custo_mes": custo_mes, "caixa_minimo": premissas.caixa_minimo,
            "aporte_total": aporte_total, "investidor": aporte_total * pi, "joy": aporte_total * pj},
        "conta": {
            "saldo_inicial": saldo_anterior, "receitas": receita_mes, "aporte": aporte_total,
            "custos": custo_mes, "saldo_final": saldo_final,
            "receitas_investidor": _recebidas_do_investidor(base, mes),
            "transferencias_holding": transferencias,
            "aporte_a_receber": max(0.0, aporte_total - transferencias)},
        "aporte_proximo": {
            "saldo_anterior": saldo_final, "receita_projetada": premissas.receita_projetada_proximo,
            "custo_projetado": custo_proximo, "custo_automatico": custo_automatico,
            "caixa_minimo": premissas.caixa_minimo_proximo, "aporte_total": aporte_proximo,
            "investidor": aporte_proximo * pi, "joy": aporte_proximo * pj},
        "cronograma_aporte": cronograma_do_aporte(premissas, mes, aporte_total, transferencias),
        "ultima_atualizacao": base.ultima_atualizacao,
    }

"""Regras do aporte (correções aprovadas em relação à planilha), com dados sintéticos.

Aporte do mês = custos do mês + caixa mínimo − saldo inicial − receitas, nunca negativo;
85% investidor e 15% Joy+. Tudo filtrado pelo mês selecionado (fim de mês).
"""
from __future__ import annotations

import math
from datetime import date

from backend.app.catalogo import VIABILIDADE_PADRAO, Premissas
from backend.app.config import CLIENTE_INVESTIDOR, EMPRESA_SPE
from backend.app.motor.base import Base, Desembolso, Movimento, Recebimento, SaldoConta, Transferencia
from backend.app.motor.resumo import calcular_resumo

HOJE = date(2026, 10, 20)
OUT, SET, NOV = date(2026, 10, 31), date(2026, 9, 30), date(2026, 11, 30)


def _base(saldo=50_000.0, custos=(), saidas=(), entradas=(), recebidas=(), transferencias=()):
    return Base(custos_spe=list(custos), saidas=list(saidas), entradas=list(entradas),
                recebidas=list(recebidas), transferencias=list(transferencias),
                saldos=[SaldoConta(EMPRESA_SPE, "conta", SET, saldo)])


def _resumo(base, **premissas):
    return calcular_resumo(base, HOJE, VIABILIDADE_PADRAO, Premissas(**premissas))


def test_aporte_cobre_custos_e_deixa_caixa_minimo():
    base = _base(saldo=50_000, custos=[Desembolso("Projetos", "Pago", date(2026, 10, 5), OUT, 30_000),
                                       Desembolso("Projetos", "A Pagar", date(2026, 10, 25), OUT, 20_000)],
                 entradas=[Movimento("Rendimentos ", date(2026, 10, 10), OUT, 1_000)])
    r = _resumo(base)
    a = r["aporte_mes"]
    assert math.isclose(a["custo_mes"], 50_000)
    assert math.isclose(a["aporte_total"], 50_000 + 100_000 - 50_000 - 1_000)          # 99.000
    assert math.isclose(a["investidor"], a["aporte_total"] * 0.85)
    assert math.isclose(a["joy"], a["aporte_total"] * 0.15)
    assert math.isclose(r["conta"]["saldo_final"], 100_000)                           # sobra o mínimo


def test_sem_aporte_quando_o_caixa_cobre():
    base = _base(saldo=500_000, custos=[Desembolso("Projetos", "Pago", date(2026, 10, 5), OUT, 30_000)])
    r = _resumo(base)
    assert r["aporte_mes"]["aporte_total"] == 0
    assert math.isclose(r["conta"]["saldo_final"], 470_000)


def test_saidas_contam_em_qualquer_dia_do_mes():
    saida = Movimento("Despesas Adm. da SPE", date(2026, 10, 2), OUT, 169)
    linha = next(l for l in _resumo(_base(saidas=[saida]))["linhas"] if l["rubrica"] == "Despesas Adm. da SPE")
    assert linha["pago_mes"] == 169 and linha["pago_ate"] == 0


def test_aporte_nao_entra_como_receita():
    base = _base(entradas=[Movimento("Aporte", date(2026, 10, 3), OUT, 2_100_000),
                           Movimento("Rendimentos ", date(2026, 10, 3), OUT, 10)])
    assert _resumo(base)["aporte_mes"]["receita_projetada"] == 10


def test_valores_seguem_o_mes_selecionado():
    """Movimentos de outros meses não entram no mês selecionado."""
    base = _base(custos=[Desembolso("Projetos", "Pago", date(2026, 9, 28), SET, 7_000),
                         Desembolso("Projetos", "Pago", date(2026, 11, 2), NOV, 9_000)],
                 entradas=[Movimento("Rendimentos ", date(2026, 9, 3), SET, 500)],
                 recebidas=[Recebimento(CLIENTE_INVESTIDOR, SET, 40_000)])
    r = _resumo(base)
    assert r["aporte_mes"]["custo_mes"] == 0 and r["aporte_mes"]["receita_projetada"] == 0
    assert r["conta"]["aportes_recebidos"] == 0


def test_aportes_recebidos_no_mes():
    base = _base(custos=[Desembolso("Projetos", "A Pagar", date(2026, 10, 25), OUT, 300_000)],
                 recebidas=[Recebimento(CLIENTE_INVESTIDOR, OUT, 255_000), Recebimento(999, OUT, 1_000)],
                 transferencias=[Transferencia(10, EMPRESA_SPE, OUT, 45_000),
                                 Transferencia(EMPRESA_SPE, 10, OUT, 5_000)])
    c = _resumo(base)["conta"]
    assert c["aportes_recebidos"] == 300_000                 # investidor + transferência para a SPE
    assert math.isclose(c["aporte_a_receber"], 350_000 - 300_000)


def test_aporte_do_proximo_mes_pela_mesma_regra():
    base = _base(saldo=50_000, custos=[Desembolso("Projetos", "Pago", date(2026, 10, 5), OUT, 30_000),
                                       Desembolso("Projetos", "A Pagar", date(2026, 11, 10), NOV, 40_000)])
    r = _resumo(base, receita_projetada_proximo=5_000)
    p = r["aporte_proximo"]
    assert math.isclose(p["saldo_anterior"], 100_000)        # parte do saldo final projetado
    assert math.isclose(p["custo_projetado"], 40_000)        # coluna S: a pagar de novembro
    assert math.isclose(p["aporte_total"], 40_000 + 100_000 - 100_000 - 5_000)
    assert math.isclose(p["investidor"] + p["joy"], p["aporte_total"])


# ------------------------------------------------------------------------ dashboards
def test_pontos_da_exposicao_de_caixa():
    from backend.app.motor.dashboards import pontos_exposicao
    meses = [date(2026, m, 28) for m in range(1, 9)]
    mensal = [0, -100, -50, -30, 40, 60, 120, 10]
    acumulado = [sum(mensal[:i + 1]) for i in range(len(mensal))]       # 0 -100 -150 -180 -140 -80 40 50
    p = pontos_exposicao(meses, mensal, acumulado)
    assert p["A"] == {"mes": meses[1], "valor": -100}                    # investimento inicial
    assert p["B"] == {"mes": meses[3], "valor": -180}                    # máxima exposição
    assert p["C"]["mes"] == meses[4]                                     # primeiro fluxo positivo
    assert p["D"]["mes"] == meses[6]                                     # ponto de equilíbrio


def test_exposicao_sem_retorno_no_horizonte():
    from backend.app.motor.dashboards import pontos_exposicao
    meses = [date(2026, m, 28) for m in range(1, 4)]
    p = pontos_exposicao(meses, [-10, -10, -10], [-10, -20, -30])
    assert p["B"]["valor"] == -30 and p["C"] is None and p["D"] is None


def test_linha_de_total_abaixo_da_tabela_e_ignorada():
    """O usedRange do SharePoint traz a linha de total da aba: não é lançamento."""
    from backend.app.fontes.normalizacao import normalizar
    linhas = [{"Empresa_es": 73, "Num_es": 1, "Data_es": "2026-10-05", "Valor_es": 10, "HistLanc_es": ""},
              {"Empresa_es": "", "Num_es": "", "Data_es": "", "Valor_es": 2117312.68, "HistLanc_es": ""}]
    r = normalizar("entradas", linhas, {"73 - 1": "Rendimentos "})
    assert len(r.registros) == 1 and r.ignoradas == 1 and not r.pendentes


# ------------------------------------------------------------------------ cronograma do aporte
def test_cronograma_divide_o_aporte_do_mes():
    base = _base(saldo=50_000, custos=[Desembolso("Projetos", "A Pagar", date(2026, 10, 25), OUT, 50_000)],
                 recebidas=[Recebimento(CLIENTE_INVESTIDOR, OUT, 40_000)])
    parcelas = [{"data": "2026-10-01", "percentual": 100 / 3}, {"data": "2026-10-15", "percentual": 100 / 3},
                {"data": "2026-10-25", "percentual": 100 / 3}]
    r = _resumo(base, cronogramas_aporte={"2026-10": parcelas})
    c = r["cronograma_aporte"]
    assert c["programado"] and c["total"] == r["aporte_mes"]["aporte_total"] == 100_000
    assert [p["valor"] for p in c["parcelas"]] == [33_333.33, 33_333.33, 33_333.34]   # soma exata
    assert math.isclose(sum(p["valor"] for p in c["parcelas"]), c["total"])
    assert all(math.isclose(p["investidor"] + p["joy"], p["valor"]) for p in c["parcelas"])
    assert [p["status"] for p in c["parcelas"]] == ["recebido", "parcial", "a receber"]


def test_sem_cronograma_e_parcela_unica_no_dia_1():
    base = _base(saldo=0, custos=[Desembolso("Projetos", "A Pagar", date(2026, 10, 25), OUT, 10_000)])
    c = _resumo(base, cronogramas_aporte={"2026-09": [{"data": "2026-09-10", "percentual": 100}]})["cronograma_aporte"]
    assert not c["programado"]
    assert [(p["data"], p["valor"]) for p in c["parcelas"]] == [(date(2026, 10, 1), 110_000)]

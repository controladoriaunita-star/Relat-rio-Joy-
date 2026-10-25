"""Regras do aporte e do Painel (correções aprovadas em relação à planilha), com dados sintéticos.

Aporte do mês = custos do mês + caixa mínimo − saldo inicial − receitas (aba Recebidas),
nunca negativo; 85% investidor e 15% Joy+. Tudo filtrado pelo mês selecionado (fim de mês).
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
                 recebidas=[Recebimento(CLIENTE_INVESTIDOR, OUT, 1_000)])
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


def test_receitas_do_mes_vem_da_recebidas():
    """Receita do aporte = tudo o que a Recebidas registra no mês, de qualquer cliente e em
    qualquer dia; Controle Entradas (aportes e rendimentos) não entra."""
    base = _base(entradas=[Movimento("Aporte", date(2026, 10, 3), OUT, 2_100_000),
                           Movimento("Rendimentos ", date(2026, 10, 3), OUT, 10)],
                 recebidas=[Recebimento(CLIENTE_INVESTIDOR, OUT, 297_500), Recebimento(5_000, OUT, 2_500),
                            Recebimento(CLIENTE_INVESTIDOR, SET, 1_088_000)])
    r = _resumo(base)
    assert r["aporte_mes"]["receita_mes"] == 300_000
    assert r["conta"]["receitas"] == 300_000 and r["conta"]["receitas_investidor"] == 297_500


def test_recebidas_abatem_o_aporte_necessario():
    """O que já entrou pela Recebidas reduz o aporte; o saldo final continua no caixa mínimo."""
    custos = [Desembolso("Projetos", "A Pagar", date(2026, 10, 25), OUT, 500_000)]
    sem = _resumo(_base(saldo=50_000, custos=custos))
    com = _resumo(_base(saldo=50_000, custos=custos, recebidas=[Recebimento(CLIENTE_INVESTIDOR, OUT, 200_000)]))
    assert math.isclose(sem["aporte_mes"]["aporte_total"], 550_000)
    assert math.isclose(com["aporte_mes"]["aporte_total"], 350_000)
    assert math.isclose(com["conta"]["saldo_final"], 100_000)
    # Recebidas acima da necessidade: sem aporte, saldo final acima do mínimo.
    folga = _resumo(_base(saldo=50_000, custos=custos, recebidas=[Recebimento(CLIENTE_INVESTIDOR, OUT, 700_000)]))
    assert folga["aporte_mes"]["aporte_total"] == 0
    assert math.isclose(folga["conta"]["saldo_final"], 250_000)


def test_valores_seguem_o_mes_selecionado():
    """Movimentos de outros meses não entram no mês selecionado."""
    base = _base(custos=[Desembolso("Projetos", "Pago", date(2026, 9, 28), SET, 7_000),
                         Desembolso("Projetos", "Pago", date(2026, 11, 2), NOV, 9_000)],
                 entradas=[Movimento("Rendimentos ", date(2026, 9, 3), SET, 500)],
                 recebidas=[Recebimento(CLIENTE_INVESTIDOR, SET, 40_000)])
    r = _resumo(base)
    assert r["aporte_mes"]["custo_mes"] == 0 and r["aporte_mes"]["receita_mes"] == 0
    assert r["conta"]["transferencias_holding"] == 0


def test_transferencias_da_holding_contam_como_aporte_recebido():
    """Transferências para a SPE não são receita: são parte do aporte necessário já recebida."""
    base = _base(custos=[Desembolso("Projetos", "A Pagar", date(2026, 10, 25), OUT, 300_000)],
                 recebidas=[Recebimento(CLIENTE_INVESTIDOR, OUT, 255_000), Recebimento(999, OUT, 1_000)],
                 transferencias=[Transferencia(10, EMPRESA_SPE, OUT, 45_000),
                                 Transferencia(EMPRESA_SPE, 10, OUT, 5_000)])
    r = _resumo(base)
    c = r["conta"]
    assert r["aporte_mes"]["aporte_total"] == 300_000 + 100_000 - 50_000 - 256_000      # 94.000
    assert c["transferencias_holding"] == 45_000             # só a que entra na SPE
    assert math.isclose(c["aporte_a_receber"], 94_000 - 45_000)


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
                 transferencias=[Transferencia(10, EMPRESA_SPE, OUT, 40_000)])
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


# ------------------------------------------------------------------------ Painel (revisão out/2026)
from backend.app.motor.base import LinhaProjecao                      # noqa: E402
from backend.app.motor.painel import calcular_painel                  # noqa: E402

AGO = date(2026, 8, 31)


def _painel(base, **premissas):
    p = calcular_painel(base, HOJE, VIABILIDADE_PADRAO, Premissas(**premissas))
    return p, {l.linha_excel: l for l in p["linhas"]}


def _no_mes(painel, linha, mes):
    return linha.tl[painel["meses"].index(mes)]


def _base_painel():
    """Set/26 = mês de análise (realizado), out/26 = mês corrente (primeiro projetado)."""
    return Base(
        custos_spe=[Desembolso("Projetos", "Pago", date(2026, 9, 10), SET, 30_000)],
        saidas=[Movimento("Despesas Adm. da SPE", date(2026, 9, 2), SET, 1_000)],
        entradas=[Movimento("Rendimentos ", date(2026, 9, 15), SET, 50)],       # meio do mês
        recebidas=[Recebimento(CLIENTE_INVESTIDOR, SET, 100_000), Recebimento(CLIENTE_INVESTIDOR, OUT, 60_000),
                   Recebimento(4321, SET, 7_000)],                                # cliente de vendas
        transferencias=[Transferencia(10, EMPRESA_SPE, SET, 5_000)],
        saldos=[SaldoConta(EMPRESA_SPE, "conta", SET, 81_019)],
        projecao=[LinhaProjecao("Projetos", AGO, "Projetado Total", 99_000),     # mês passado sem realizado
                  LinhaProjecao("Projetos", SET, "Projetado Total", 25_000),     # mês passado com realizado
                  LinhaProjecao("Projetos", OUT, "Projetado Total", 40_000),
                  LinhaProjecao("Projetos", NOV, "Projetado Total", 10_000)])


def test_painel_meses_passados_so_realizado_e_projetado_do_corrente_em_diante():
    p, l = _painel(_base_painel())
    projetos = l[49]
    assert _no_mes(p, projetos, AGO) == 0                    # P1: projeção de mês passado não entra
    assert _no_mes(p, projetos, SET) == -30_000              # realizado
    assert projetos.H == -30_000                             # A: realizado até set/26
    assert projetos.L == -40_000                             # P3: B = projeção de out/26
    assert projetos.P == -50_000                             # P2: C = out + nov (sem meses passados)
    assert projetos.T == -80_000


def test_painel_receitas_recebidas_e_rendimentos():
    p, l = _painel(_base_painel())
    assert l[32].H == 50                                     # P5: rendimento no meio do mês conta
    assert l[25].H == 7_000                                  # P8: Recebidas de vendas
    assert l[36].H == 7_050 and l[41].H == 7_050
    assert l[106].H == 100_000 and l[106].L == 60_000        # P7: Recebidas do investidor
    assert l[106].X is None and l[105].X is None             # P11: sócios sem EVE


def test_painel_margem_resultado_e_saldo_de_caixa():
    p, l = _painel(_base_painel())
    assert l[59].H == 7_050 - 30_000                         # P6: margem = receita líquida − custos
    assert l[79].H == l[59].H - 1_000                        # EBITDA = margem − despesas
    assert l[83].H == l[79].H and l[93].H == l[83].H         # resultado e saldo com realizado
    assert l[59].X == l[41].X - sum(l[r].X for r in range(43, 57))
    for linha in p["linhas"]:                                # A + C = D em toda linha de fluxo
        if linha.extras.get("FT"):
            assert linha.extras["FT"] == linha.extras["FU"] == "OK!", linha.linha_excel
            assert math.isclose(linha.T, linha.H + linha.P), linha.linha_excel


def test_painel_saldo_acumulado_concilia_com_o_extrato():
    """P9: saldo acumulado no mês de análise = coluna A da linha 119 = extrato (aba Saldo)."""
    p, l = _painel(_base_painel(), ajuste_saldo_banco=0)
    fluxo_set = 7_050 - 30_000 - 1_000 + 100_000 + 5_000     # operação + investidor + holding
    assert _no_mes(p, l[119], SET) == fluxo_set
    assert l[119].H == fluxo_set == _no_mes(p, l[122], SET)
    assert p["conciliacao"] == {"mes": SET, "saldo_painel": 81_050, "saldo_banco": 81_019, "diferenca": 31}
    _, com_ajuste = _painel(_base_painel(), ajuste_saldo_banco=-31)
    assert com_ajuste[119].H == 81_019


def test_painel_exposicao_maxima():
    p, l = _painel(_base_painel())
    acumulado = l[95].tl
    assert l[101].T == min(acumulado)
    assert l[101].H == _no_mes(p, l[95], SET) and math.isclose(l[101].H + l[101].P, l[101].T)

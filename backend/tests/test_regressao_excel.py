"""Regressão contra a planilha: o motor precisa reproduzir os valores do Excel.

Lê as tabelas de dados, o DePara, a Projeção_2 e os saldos do .xlsm, calcula
Resumo e Painel com o motor e compara com os valores salvos pelo Excel em cada
célula. Toda célula de fórmula das colunas cobertas precisa ter equivalente.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time

import openpyxl
import pytest
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.formula import ArrayFormula

from backend.app.catalogo import VIABILIDADE_PADRAO, Premissas
from backend.app.config import ARQUIVO_EXCEL
from backend.app.excel_funcoes import DATA_ZERO
from backend.app.fontes.excel import ler_planilha
from backend.app.fontes.montagem import montar_base
from backend.app.motor.painel import calcular_painel
from backend.app.motor.resumo import calcular_resumo

pytestmark = pytest.mark.skipif(not ARQUIVO_EXCEL.exists(), reason="planilha de referência ausente")

COLUNA_INICIO_TL = column_index_from_string("CE")
COLUNAS_RESUMO = {"viabilidade": "D", "pct_consumido": "F", "pago_ate": "H", "pago_mes": "J",
                  "a_pagar": "L", "projetado_mes": "Q", "projetado_proximo": "S", "total_mes": "U"}
COLUNAS_PAINEL = ("H", "L", "P", "T", "X", "Y", "AB")
COLUNAS_PAINEL_COBERTAS = set(COLUNAS_PAINEL) | {"J", "N", "BA", "BB", "FS", "FT", "FU", "FV"} | {
    get_column_letter(COLUNA_INICIO_TL + i) for i in range(84)}


@pytest.fixture(scope="module")
def cenario():
    planilha = ler_planilha(ARQUIVO_EXCEL)
    base, resultados = montar_base(planilha.tabelas, planilha.depara, planilha.projecao,
                                   planilha.saldos, planilha.ultima_atualizacao)
    hoje = planilha.ultima_atualizacao.date()
    # Z22 é digitado na planilha; no sistema é automático. Para comparar, usa o valor do Excel.
    premissas = Premissas(custo_projetado_proximo=775384.9700000001)
    formulas = openpyxl.load_workbook(ARQUIVO_EXCEL)
    return {
        "planilha": planilha, "resultados": resultados, "formulas": formulas,
        "resumo": calcular_resumo(base, hoje, VIABILIDADE_PADRAO, premissas),
        "painel": calcular_painel(base, hoje, VIABILIDADE_PADRAO, premissas),
    }


def _eh_formula(valor) -> bool:
    return isinstance(valor, ArrayFormula) or (isinstance(valor, str) and valor.startswith("="))


def _normalizar(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, time):          # data vazia formatada (0)
        return 0.0
    return valor


def _igual(esperado, obtido) -> bool:
    esperado, obtido = _normalizar(esperado), _normalizar(obtido)
    if isinstance(obtido, date) and isinstance(esperado, (int, float)):   # data em formato número
        obtido = float((obtido - DATA_ZERO).days)
    if isinstance(esperado, (int, float)) and not isinstance(esperado, bool):
        if not isinstance(obtido, (int, float)):
            return esperado == 0 and obtido is None
        return math.isclose(esperado, obtido, rel_tol=1e-9, abs_tol=0.005)
    if esperado in (None, ""):
        return obtido in (None, "", 0)
    return esperado == obtido


def _comparar(valores_excel, celulas: dict, rotulo: str) -> None:
    divergencias = [f"{rotulo}!{c}: Excel={valores_excel[c].value!r} motor={v!r}"
                    for c, v in celulas.items() if not _igual(valores_excel[c].value, v)]
    assert not divergencias, f"{len(divergencias)} divergência(s):\n" + "\n".join(divergencias[:40])


def test_classificacao_depara_igual_a_planilha(cenario):
    """O DePara aplicado pelo sistema gera a mesma Classificação que a planilha."""
    for codigo, resultado in cenario["resultados"].items():
        assert not resultado.colunas_ausentes, codigo
        assert not resultado.pendentes, (codigo, resultado.pendentes[:3])


def test_resumo(cenario):
    resumo = cenario["resumo"]
    celulas = {}
    for linha in resumo["linhas"] + [{**resumo["total"], "linha_excel": 5}]:
        for campo, coluna in COLUNAS_RESUMO.items():
            if campo in linha:
                celulas[f"{coluna}{linha['linha_excel']}"] = linha[campo]
    blocos = {"aporte_mes": [("saldo_anterior", 5), ("receita_projetada", 6), ("custo_mes", 7),
                             ("caixa_minimo", 8), ("aporte_total", 9), ("investidor", 10), ("joy", 11)],
              "conta": [("saldo_mes_anterior", 13), ("valor_recebido", 14), ("pago_e_a_pagar", 15),
                        ("saldo_atual", 16), ("valor_a_aportar", 17), ("saldo_final", 18)],
              "aporte_proximo": [("saldo_anterior", 20), ("receita_projetada", 21),
                                 ("custo_projetado", 22), ("caixa_minimo", 23), ("aporte_total", 24),
                                 ("investidor", 25), ("joy", 26)]}
    for bloco, campos in blocos.items():
        for campo, linha in campos:
            celulas[f"Z{linha}"] = resumo[bloco][campo]
    for aporte, linha in zip(resumo["aportes_programados"], (33, 37)):
        celulas[f"Y{linha}"] = aporte["valor"]
        celulas[f"Y{linha + 1}"] = aporte["investidor"]
        celulas[f"Y{linha + 2}"] = aporte["joy"]
    celulas["Y43"] = resumo["total_aportes_programados"]
    titulos = resumo["titulos"]
    celulas.update({"H3": titulos["pago_ate"], "J3": titulos["pago_mes"], "L3": titulos["a_pagar"],
                    "S3": titulos["projetado_proximo"], "Y5": titulos["saldo_anterior"],
                    "Y7": titulos["custo_mes"], "Y14": titulos["valor_recebido"],
                    "Y15": titulos["pago_e_a_pagar"], "Y20": titulos["saldo_proximo"],
                    "Y22": titulos["custo_proximo"], "B4": resumo["datas"]["mes_atual"],
                    "L4": resumo["datas"]["a_pagar_ate"], "AD3": resumo["datas"]["mes_analise"]})
    _comparar(cenario["planilha"].livro["Resumo"], celulas, "Resumo")

    # Toda fórmula das colunas de valor precisa estar coberta.
    formulas = cenario["formulas"]["Resumo"]
    faltando = [c.coordinate for linha in formulas.iter_rows(min_row=5, max_row=43)
                for c in linha if c.column_letter in COLUNAS_RESUMO.values()
                and _eh_formula(c.value) and c.coordinate not in celulas]
    assert not faltando, faltando


def test_painel(cenario):
    painel = cenario["painel"]
    celulas = {}
    for linha in painel["linhas"]:
        r = linha.linha_excel
        for coluna in COLUNAS_PAINEL:
            valor = getattr(linha, coluna)
            if valor is not None:
                celulas[f"{coluna}{r}"] = valor
        for i, valor in enumerate(linha.tl):
            if valor is not None:
                celulas[f"{get_column_letter(COLUNA_INICIO_TL + i)}{r}"] = valor
        for coluna, valor in linha.extras.items():
            celulas[f"{coluna}{r}"] = valor
    for i, mes in enumerate(painel["meses"]):
        coluna = get_column_letter(COLUNA_INICIO_TL + i)
        celulas[f"{coluna}4"] = celulas[f"{coluna}23"] = celulas[f"{coluna}91"] = mes
    celulas.update({"D22": painel["datas"]["mes_analise"], "H21": painel["datas"]["mes_atual"],
                    "AI23": painel["datas"]["corte"], "G20": painel["titulos"]["ate"],
                    "H23": painel["titulos"]["realizado"]})

    valores = cenario["planilha"].livro["Painel"]
    formulas = cenario["formulas"]["Painel"]
    # Só compara células que existem na planilha (as demais são vazias lá).
    existentes = {c: v for c, v in celulas.items() if formulas[c].value is not None}
    _comparar(valores, existentes, "Painel")

    faltando = [c.coordinate for linha in formulas.iter_rows(min_row=24, max_row=122)
                for c in linha if _eh_formula(c.value)
                and get_column_letter(c.column) in COLUNAS_PAINEL_COBERTAS
                and c.coordinate not in celulas]
    assert not faltando, faltando

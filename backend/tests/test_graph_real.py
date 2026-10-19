"""Teste ponta a ponta das 6 rotas reais do Microsoft Graph.

Faz chamadas de verdade ao SharePoint; por isso só roda com APORTE_TESTE_GRAPH=1.
Valida autenticação, permissões do token e as colunas exigidas pelo cálculo.
"""
from __future__ import annotations

import os

import pytest

from backend.app.fontes.definicoes import FONTES
from backend.app.fontes.graph import ClienteGraph
from backend.app.fontes.normalizacao import normalizar, tabela_para_dicts

pytestmark = pytest.mark.skipif(os.environ.get("APORTE_TESTE_GRAPH") != "1",
                                reason="defina APORTE_TESTE_GRAPH=1 para chamar o Graph real")


@pytest.fixture(scope="module")
def graph():
    cliente = ClienteGraph()
    assert cliente.configurado(), "credenciais ausentes no .env"
    return cliente


def test_token_tem_permissoes(graph):
    papeis = graph.permissoes_do_token()
    assert {"Files.Read.All", "Sites.Read.All", "Sites.Selected"} & set(papeis), papeis


@pytest.mark.parametrize("fonte", FONTES, ids=lambda f: f.codigo)
def test_rota(graph, fonte):
    valores = graph.ler_aba(fonte.aba_graph)
    assert len(valores) > 1, "aba sem linhas"
    resultado = normalizar(fonte.codigo, tabela_para_dicts(valores), {})
    assert not resultado.colunas_ausentes, resultado.colunas_ausentes

"""Teste ponta a ponta das rotas reais do Microsoft Graph, para o arquivo de cada obra.

Faz chamadas de verdade ao SharePoint; por isso só roda com APORTE_TESTE_GRAPH=1.
Valida autenticação, permissões do token e as colunas exigidas pelo cálculo.
"""
from __future__ import annotations

import os

import pytest

from backend.app.fontes.definicoes import FONTES
from backend.app.fontes.graph import ClienteGraph, ErroGraph
from backend.app.fontes.normalizacao import normalizar, tabela_para_dicts
from backend.app.obras import OBRAS_PADRAO

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


@pytest.mark.parametrize("obra", OBRAS_PADRAO, ids=lambda o: o.codigo)
@pytest.mark.parametrize("fonte", FONTES, ids=lambda f: f.codigo)
def test_rota(graph, obra, fonte):
    valores = graph.ler_aba(obra.graph_item_id, obra.aba(fonte))
    assert valores, "aba sem cabeçalho"                 # pode não ter lançamentos ainda (ex.: Recebidas)
    resultado = normalizar(fonte.codigo, tabela_para_dicts(valores), {})
    assert not resultado.colunas_ausentes, resultado.colunas_ausentes


def test_aba_inexistente_diz_qual_arquivo_esta_configurado(graph):
    with pytest.raises(ErroGraph, match="não existe no arquivo configurado"):
        graph.ler_aba(OBRAS_PADRAO[0].graph_item_id, "Aba que não existe")

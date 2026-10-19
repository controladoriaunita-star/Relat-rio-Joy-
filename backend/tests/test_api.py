"""Testes ponta a ponta da API REST: sessão, permissões, projeção, fontes e saldos.

Usa um banco temporário carregado a partir da planilha (mesma carga inicial da produção).
"""
from __future__ import annotations

import json
import math

import openpyxl
import pytest
from fastapi.testclient import TestClient

from backend.app import auth
from backend.app.config import ARQUIVO_EXCEL
from backend.app.db import Banco
from backend.app.fontes.graph import ErroGraph
from backend.app.main import criar_app
from backend.app.servicos import Servico

pytestmark = pytest.mark.skipif(not ARQUIVO_EXCEL.exists(), reason="planilha de referência ausente")
HOJE = "2026-10-16"
USUARIOS = {"ana.mkt": "mkt", "caio.proj": "proj", "dora.dir": "diretor", "edu.adm": "adm"}


class GraphFalso:
    """Simula o Graph sem permissão (situação atual do app no Entra ID)."""

    @staticmethod
    def configurado():
        return True

    def ler_aba(self, aba):
        raise ErroGraph("Acesso negado pelo SharePoint.")


@pytest.fixture(scope="module")
def ambiente(tmp_path_factory):
    banco = Banco(tmp_path_factory.mktemp("dados") / "teste.sqlite3")
    servico = Servico(banco, graph=GraphFalso(), admin=auth.AdminLocal())
    servico.inicializar()
    relatorio = servico.migrar_do_excel()
    ids = {login: servico.criar_usuario(f"{login}@joy.test", login, perfil, None, None)
           for login, perfil in USUARIOS.items()}
    # O verificador local troca o JWT do Supabase nos testes ("local:<usuario_id>").
    app = criar_app(servico=servico, verificador=auth.VerificadorLocal())
    return {"app": app, "servico": servico, "relatorio": relatorio, "ids": ids,
            "excel": openpyxl.load_workbook(ARQUIVO_EXCEL, data_only=True)}


def cliente(ambiente, login: str | None = None) -> TestClient:
    c = TestClient(ambiente["app"])
    if login:
        usuario_id = ambiente["ids"].get(login, login)
        c.headers["Authorization"] = f"Bearer {auth.PREFIXO_TOKEN_LOCAL}{usuario_id}"
    return c


def linha_id(ambiente, nome: str) -> int:
    return ambiente["servico"].banco.um("SELECT id FROM linhas_projecao WHERE nome = ?", nome)["id"]


# ------------------------------------------------------------------------ sessão
def test_sem_token_bloqueia(ambiente):
    assert cliente(ambiente).get("/api/resumo").status_code == 401


def test_token_de_usuario_sem_perfil(ambiente):
    assert cliente(ambiente, "desconhecido").get("/api/eu").status_code == 401


def test_perfil(ambiente):
    eu = cliente(ambiente, "ana.mkt").get("/api/eu").json()
    assert eu["perfil"] == "mkt" and eu["perfil_nome"] == "Marketing"
    assert eu["permissoes"]["ver_apis"] is False


def test_config_publica_nao_exige_login(ambiente):
    assert cliente(ambiente).get("/api/config").json()["modo"] == "local"


# ------------------------------------------------------------------------ cálculo
def test_resumo_realizado_igual_planilha(ambiente):
    """Colunas que vêm das fontes (não da projeção) batem com o Excel via API."""
    resumo = cliente(ambiente, "dora.dir").get(f"/api/resumo?data={HOJE}").json()
    excel = ambiente["excel"]["Resumo"]
    for linha in resumo["linhas"]:
        for campo, coluna in (("pago_ate", "H"), ("pago_mes", "J"), ("a_pagar", "L")):
            if campo in linha:
                esperado = excel[f"{coluna}{linha['linha_excel']}"].value or 0
                assert math.isclose(linha[campo], esperado, abs_tol=0.005), (campo, linha["rubrica"])
    for campo, celula in (("saldo_anterior", "Z5"), ("receita_projetada", "Z6")):
        assert math.isclose(resumo["aporte_mes"][campo], excel[celula].value, abs_tol=0.005)
    for campo, celula in (("saldo_mes_anterior", "Z13"), ("valor_recebido", "Z14")):
        assert math.isclose(resumo["conta"][campo], excel[celula].value, abs_tol=0.005)


def test_painel_serializa(ambiente):
    painel = cliente(ambiente, "ana.mkt").get(f"/api/painel?data={HOJE}").json()
    assert len(painel["meses"]) == 84
    terreno = next(l for l in painel["linhas"] if l["linha_excel"] == 43)
    assert math.isclose(terreno["H"], ambiente["excel"]["Painel"]["H43"].value, abs_tol=0.005)


# ------------------------------------------------------------------------ projeção
def test_migracao_projecao_sem_duplicidade(ambiente):
    projecao = ambiente["relatorio"]["projecao"]
    assert projecao["importados"] > 0
    linhas = ambiente["servico"].banco.todos("SELECT linha_id, mes, COUNT(*) n FROM projecoes "
                                             "GROUP BY linha_id, mes HAVING n > 1")
    assert linhas == []


def test_setor_edita_somente_suas_linhas(ambiente):
    c = cliente(ambiente, "ana.mkt")
    ok = c.put(f"/api/projecao?data={HOJE}",
               json=[{"linha_id": linha_id(ambiente, "Marketing"), "mes": "2027-03-31", "valor": 1234.5}])
    assert ok.status_code == 200
    negado = c.put(f"/api/projecao?data={HOJE}",
                   json=[{"linha_id": linha_id(ambiente, "ARQUITETURA | RSA"), "mes": "2027-03-31",
                          "valor": 10}])
    assert negado.status_code == 422 and "permissão" in negado.json()["detail"]


def test_mes_passado_bloqueado_para_setor(ambiente):
    item = [{"linha_id": linha_id(ambiente, "Marketing"), "mes": "2026-09-30", "valor": 5}]
    assert cliente(ambiente, "ana.mkt").put(f"/api/projecao?data={HOJE}", json=item).status_code == 422
    assert cliente(ambiente, "dora.dir").put(f"/api/projecao?data={HOJE}", json=item).status_code == 200
    item[0]["valor"] = 0      # zerar remove a projeção
    assert cliente(ambiente, "dora.dir").put(f"/api/projecao?data={HOJE}", json=item).status_code == 200


def test_mes_invalido(ambiente):
    item = [{"linha_id": linha_id(ambiente, "Marketing"), "mes": "2027-03-15", "valor": 5}]
    assert cliente(ambiente, "ana.mkt").put(f"/api/projecao?data={HOJE}", json=item).status_code == 422


def test_projecao_alimenta_resumo_e_painel(ambiente):
    c = cliente(ambiente, "caio.proj")
    rubrica = "Projetos"
    antes_r = next(l for l in c.get(f"/api/resumo?data={HOJE}").json()["linhas"] if l["rubrica"] == rubrica)
    antes_p = next(l for l in c.get(f"/api/painel?data={HOJE}").json()["linhas"] if l["rotulo"] == rubrica)
    c.put(f"/api/projecao?data={HOJE}",
          json=[{"linha_id": linha_id(ambiente, "LAUDOS | C23"), "mes": "2026-11-30", "valor": 1000},
                {"linha_id": linha_id(ambiente, "LAUDOS | C23"), "mes": "2026-10-31", "valor": 250}])
    depois_r = next(l for l in c.get(f"/api/resumo?data={HOJE}").json()["linhas"] if l["rubrica"] == rubrica)
    depois_p = next(l for l in c.get(f"/api/painel?data={HOJE}").json()["linhas"] if l["rotulo"] == rubrica)
    assert math.isclose(depois_r["projetado_proximo"] - antes_r["projetado_proximo"], 1000)
    assert math.isclose(depois_r["projetado_mes"] - antes_r["projetado_mes"], 250)
    assert math.isclose(depois_p["P"] - antes_p["P"], -1250)          # Painel P = -Projetado Total
    grade = c.get(f"/api/projecao?data={HOJE}").json()
    projetos = next(s for s in grade["setores"] if s["codigo"] == "proj")
    assert projetos["editavel"] and not next(s for s in grade["setores"] if s["codigo"] == "mkt")["editavel"]


def test_novo_setor_cria_perfil(ambiente):
    adm = cliente(ambiente, "edu.adm")
    setor = adm.post("/api/setores", json={"codigo": "jur", "nome": "Jurídico"}).json()["id"]
    linha = adm.post("/api/linhas", json={"setor_id": setor, "nome": "Honorários",
                                          "rubrica": "Despesas de Incorporação"}).json()["id"]
    criado = adm.post("/api/usuarios", json={"email": "gil.jur@joy.test", "nome": "Gil", "perfil": "jur"})
    assert criado.status_code == 200
    gil = cliente(ambiente, criado.json()["id"])
    r = gil.put(f"/api/projecao?data={HOJE}", json=[{"linha_id": linha, "mes": "2027-01-31", "valor": 99}])
    assert r.status_code == 200
    assert adm.post("/api/setores", json={"codigo": "adm", "nome": "x"}).status_code == 422


def test_setor_nao_administra(ambiente):
    assert cliente(ambiente, "ana.mkt").post("/api/setores", json={"codigo": "x", "nome": "x"}).status_code == 403


# ------------------------------------------------------------------------ fontes
def test_aba_apis_restrita(ambiente):
    assert cliente(ambiente, "ana.mkt").get("/api/fontes").status_code == 403
    status = cliente(ambiente, "edu.adm").get("/api/fontes").json()
    assert {f["codigo"] for f in status["fontes"]} == {"custos_spe", "custos_nn", "saidas", "entradas",
                                                       "transferencias", "recebidas"}
    assert all(f["ultima_ok"] and f["pendentes"] == 0 for f in status["fontes"])


def test_falha_do_graph_preserva_ultima_carga(ambiente):
    adm = cliente(ambiente, "edu.adm")
    antes = adm.get(f"/api/resumo?data={HOJE}").json()["total"]
    relatorio = adm.post("/api/fontes/atualizar", json={"origem": "graph"}).json()
    assert all(r["status"] == "erro" and "Acesso negado" in r["mensagem"] for r in relatorio)
    assert adm.get(f"/api/resumo?data={HOJE}").json()["total"] == antes
    fontes = adm.get("/api/fontes").json()["fontes"]
    assert all(f["ultima"]["status"] == "erro" and f["ultima_ok"] for f in fontes)


def test_pendencia_de_classificacao(ambiente):
    servico = ambiente["servico"]
    carga = servico.banco.um("SELECT id, dados FROM cargas WHERE fonte = 'saidas' AND status = 'ok' "
                             "ORDER BY id DESC LIMIT 1")
    valores = json.loads(carga["dados"])
    cab = valores[0]
    nova = [None] * len(cab)
    nova[cab.index("Empresa_es")], nova[cab.index("Num_es")] = 73, 999
    nova[cab.index("Data_es")], nova[cab.index("Valor_es")] = "2026-10-05", 321.0
    with servico.banco.transacao() as con:
        con.execute("UPDATE cargas SET dados = ? WHERE id = ?", (json.dumps(valores + [nova]), carga["id"]))

    adm = cliente(ambiente, "edu.adm")
    pendentes = adm.get("/api/fontes/saidas/pendentes").json()
    assert [p["concat"] for p in pendentes] == ["73 - 999"]
    antes = next(l for l in adm.get(f"/api/resumo?data={HOJE}").json()["linhas"]
                 if l["rubrica"] == "Despesas Adm. da SPE")
    assert adm.post("/api/fontes/saidas/classificar",
                    json={"concat": "73 - 999", "classificacao": "Despesas Adm. da SPE"}).status_code == 200
    assert adm.get("/api/fontes/saidas/pendentes").json() == []
    depois = next(l for l in adm.get(f"/api/resumo?data={HOJE}").json()["linhas"]
                  if l["rubrica"] == "Despesas Adm. da SPE")
    # Regras da planilha para Controle_Saídas: J exige Data_es = fim do mês corrente e
    # H soma Data_es < fim do mês corrente; uma saída em 05/10 cai em H, não em J.
    assert math.isclose(depois["pago_mes"] - antes["pago_mes"], 0)
    assert math.isclose(depois["pago_ate"] - antes["pago_ate"], 321)


# ------------------------------------------------------------------------ saldos e premissas
def test_saldo_manual_altera_resumo(ambiente):
    adm = cliente(ambiente, "edu.adm")
    antes = adm.get(f"/api/resumo?data={HOJE}").json()["aporte_mes"]["saldo_anterior"]
    assert adm.post("/api/saldos", json={"conta": "99999-9", "data": "2026-09-30",
                                         "saldo": 1000}).status_code == 200
    depois = adm.get(f"/api/resumo?data={HOJE}").json()["aporte_mes"]["saldo_anterior"]
    assert math.isclose(depois - antes, 1000)
    assert cliente(ambiente, "ana.mkt").post("/api/saldos", json={}).status_code == 403


def test_premissas(ambiente):
    dir_ = cliente(ambiente, "dora.dir")
    r = dir_.put("/api/parametros/premissas", json={"caixa_minimo": 150000})
    assert r.status_code == 200 and r.json()["caixa_minimo"] == 150000
    assert dir_.get(f"/api/resumo?data={HOJE}").json()["aporte_mes"]["caixa_minimo"] == 150000
    assert dir_.put("/api/parametros/premissas", json={"inexistente": 1}).status_code == 422
    assert cliente(ambiente, "ana.mkt").put("/api/parametros/premissas", json={}).status_code == 403
    dir_.put("/api/parametros/premissas", json={"caixa_minimo": 100000})


def test_historico_registra_acoes(ambiente):
    acoes = {h["acao"] for h in cliente(ambiente, "edu.adm").get("/api/historico").json()}
    assert {"projecao.salvar", "depara.classificar", "fonte.atualizar", "saldo.salvar"} <= acoes


def test_custo_proximo_mes_automatico(ambiente):
    """Z22 deixa de ser digitado: é o projetado + contas a pagar do próximo mês (coluna S)."""
    resumo = cliente(ambiente, "dora.dir").get(f"/api/resumo?data={HOJE}").json()
    proximo = resumo["aporte_proximo"]
    assert proximo["custo_automatico"] is True
    assert math.isclose(proximo["custo_projetado"], resumo["total"]["projetado_proximo"])
    assert math.isclose(proximo["aporte_total"],
                        proximo["caixa_minimo"] - proximo["saldo_anterior"] + proximo["custo_projetado"])


def test_usuario_desativado_perde_acesso(ambiente):
    adm = cliente(ambiente, "edu.adm")
    novo = adm.post("/api/usuarios", json={"email": "temp@joy.test", "nome": "Temp", "perfil": "mkt"}).json()["id"]
    assert cliente(ambiente, novo).get("/api/eu").status_code == 200
    assert adm.patch(f"/api/usuarios/{novo}", json={"ativo": False}).status_code == 200
    assert cliente(ambiente, novo).get("/api/eu").status_code == 401
    assert adm.post("/api/usuarios", json={"email": "x", "nome": "X", "perfil": "mkt"}).status_code == 422

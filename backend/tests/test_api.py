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
from backend.app.catalogo import PERMISSOES
from backend.app.config import ARQUIVO_EXCEL
from backend.app.db import Banco
from backend.app.fontes.graph import ErroGraph
from backend.app.main import criar_app
from backend.app.servicos import Servico

pytestmark = pytest.mark.skipif(not ARQUIVO_EXCEL.exists(), reason="planilha de referência ausente")
HOJE = "2026-10-16"
USUARIOS = {"ana.mkt": "mkt", "caio.proj": "proj", "dora.dir": "diretor", "edu.adm": "admin"}


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
    app = criar_app(servico=servico, verificador=auth.VerificadorLocal(), login_ativo=True)
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
    assert eu["permissoes"]["apis.ver"] is False


def test_setor_ve_somente_a_projecao(ambiente):
    c = cliente(ambiente, "ana.mkt")
    eu = c.get("/api/eu").json()["permissoes"]
    assert eu["projecao.ver"] and not (eu["resumo.ver"] or eu["dashboards.ver"] or eu["painel.ver"] or eu["apis.ver"])
    for rota in ("/api/resumo", "/api/painel", "/api/parametros", "/api/fontes"):
        assert c.get(f"{rota}?data={HOJE}").status_code == 403, rota
    assert c.get(f"/api/projecao?data={HOJE}").status_code == 200
    for login in ("dora.dir", "edu.adm"):
        assert cliente(ambiente, login).get(f"/api/resumo?data={HOJE}").status_code == 200


def test_papeis_e_permissoes_padrao(ambiente):
    matriz = cliente(ambiente, "edu.adm").get("/api/permissoes").json()
    papeis = {p["key"]: set(p["permissoes"]) for p in matriz["papeis"]}
    assert papeis["admin"] == set(PERMISSOES)
    assert papeis["diretor"] == set(PERMISSOES) - {"setores.gerenciar", "usuarios.gerenciar"}
    assert papeis["mkt"] == papeis["proj"] == papeis["inc"] == {"projecao.ver"}
    assert cliente(ambiente, "dora.dir").get("/api/permissoes").status_code == 403


def test_conceder_permissao_a_um_setor(ambiente):
    adm = cliente(ambiente, "edu.adm")
    conceder = lambda valor: adm.put("/api/permissoes", json={"papel": "proj", "permissao": "painel.ver",
                                                               "concedida": valor})
    try:
        assert conceder(True).status_code == 200
        assert cliente(ambiente, "caio.proj").get(f"/api/painel?data={HOJE}").status_code == 200
        assert cliente(ambiente, "ana.mkt").get(f"/api/painel?data={HOJE}").status_code == 403
    finally:
        assert conceder(False).status_code == 200
    assert cliente(ambiente, "caio.proj").get(f"/api/painel?data={HOJE}").status_code == 403
    assert adm.put("/api/permissoes", json={"papel": "admin", "permissao": "resumo.ver",
                                            "concedida": False}).status_code == 422


def test_usuario_sem_papel_nao_entra(ambiente):
    banco = ambiente["servico"].banco
    usuario_id = ambiente["ids"]["ana.mkt"]
    with banco.transacao() as con:
        con.execute("DELETE FROM user_roles WHERE user_id = ?", (usuario_id,))
    try:
        assert cliente(ambiente, "ana.mkt").get("/api/eu").status_code == 401
    finally:
        auth.registrar_usuario(banco, usuario_id, "ana.mkt@joy.test", "ana.mkt", "mkt")


def test_config_publica_nao_exige_login(ambiente):
    assert cliente(ambiente).get("/api/config").json()["modo"] == "local"


# ------------------------------------------------------------------------ cálculo
def test_resumo_realizado_igual_planilha(ambiente):
    """Colunas que vêm das fontes (não da projeção) batem com o Excel via API."""
    resumo = cliente(ambiente, "dora.dir").get(f"/api/resumo?data={HOJE}").json()
    excel = ambiente["excel"]["Resumo"]
    for linha in resumo["linhas"]:
        r = linha["linha_excel"]
        if "pago_ate" in linha:   # H + J: saídas do mês passam de H para J (correção aprovada)
            esperado = (excel[f"H{r}"].value or 0) + (excel[f"J{r}"].value or 0)
            assert math.isclose(linha["pago_ate"] + linha["pago_mes"], esperado, abs_tol=0.005), linha["rubrica"]
        assert math.isclose(linha["a_pagar"], excel[f"L{r}"].value or 0, abs_tol=0.005), linha["rubrica"]
    for campo, celula in (("saldo_anterior", "Z5"), ("receita_projetada", "Z6")):
        assert math.isclose(resumo["aporte_mes"][campo], excel[celula].value, abs_tol=0.005)
    a, c = resumo["aporte_mes"], resumo["conta"]
    assert math.isclose(c["saldo_final"], a["saldo_anterior"] + a["receita_projetada"] + a["aporte_total"]
                        - a["custo_mes"])
    assert c["saldo_final"] >= a["caixa_minimo"] - 0.005


def test_painel_serializa(ambiente):
    painel = cliente(ambiente, "dora.dir").get(f"/api/painel?data={HOJE}").json()
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
    c, leitor = cliente(ambiente, "caio.proj"), cliente(ambiente, "dora.dir")
    rubrica = "Projetos"
    antes_r = next(l for l in leitor.get(f"/api/resumo?data={HOJE}").json()["linhas"] if l["rubrica"] == rubrica)
    antes_p = next(l for l in leitor.get(f"/api/painel?data={HOJE}").json()["linhas"] if l["rotulo"] == rubrica)
    c.put(f"/api/projecao?data={HOJE}",
          json=[{"linha_id": linha_id(ambiente, "LAUDOS | C23"), "mes": "2026-11-30", "valor": 1000},
                {"linha_id": linha_id(ambiente, "LAUDOS | C23"), "mes": "2026-10-31", "valor": 250}])
    depois_r = next(l for l in leitor.get(f"/api/resumo?data={HOJE}").json()["linhas"] if l["rubrica"] == rubrica)
    depois_p = next(l for l in leitor.get(f"/api/painel?data={HOJE}").json()["linhas"] if l["rotulo"] == rubrica)
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
    assert adm.post("/api/setores", json={"codigo": "admin", "nome": "x"}).status_code == 422


def test_setor_nao_administra(ambiente):
    assert cliente(ambiente, "ana.mkt").post("/api/setores", json={"codigo": "x", "nome": "x"}).status_code == 403


# ------------------------------------------------------------------------ fontes
def test_aba_apis_restrita(ambiente):
    assert cliente(ambiente, "ana.mkt").get("/api/fontes").status_code == 403
    status = cliente(ambiente, "edu.adm").get("/api/fontes").json()
    assert {f["codigo"] for f in status["fontes"]} == {"custos_spe", "custos_nn", "saidas", "entradas",
                                                       "transferencias", "recebidas", "saldos"}
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
    # Controle Saídas entram pelo mês da data: uma saída em 05/10 é "pago no mês" de outubro.
    assert math.isclose(depois["pago_mes"] - antes["pago_mes"], 321)
    assert math.isclose(depois["pago_ate"] - antes["pago_ate"], 0)


# ------------------------------------------------------------------------ saldos e premissas
def test_saldos_vem_da_fonte_e_alimentam_o_resumo(ambiente):
    """Saldo do mês anterior (Z5) = soma, por conta, do último saldo do mês na aba Saldo."""
    adm = cliente(ambiente, "edu.adm")
    resumo = adm.get(f"/api/resumo?data={HOJE}").json()
    saldos = adm.get("/api/saldos").json()
    fim = [x for x in saldos if x["fim_de_mes"] and x["data"][:7] == resumo["datas"]["mes_analise"][:7]]
    assert fim and math.isclose(sum(x["saldo"] for x in fim), resumo["aporte_mes"]["saldo_anterior"])
    assert len({x["conta"] for x in fim}) == len(fim)                 # um saldo por conta
    servico = ambiente["servico"]
    carga = servico.banco.um("SELECT id, dados FROM cargas WHERE fonte = 'saldos' AND status = 'ok' ORDER BY id DESC LIMIT 1")
    valores = json.loads(carga["dados"])
    cab = valores[0]
    nova = [None] * len(cab)
    for coluna, valor in (("Empresa", 73), ("Data", resumo["datas"]["mes_analise"]), ("Conta", "99999-9"), ("Saldo", 1000)):
        nova[cab.index(coluna)] = valor
    with servico.banco.transacao() as con:
        con.execute("UPDATE cargas SET dados = ? WHERE id = ?", (json.dumps(valores + [nova]), carga["id"]))
    depois = adm.get(f"/api/resumo?data={HOJE}").json()["aporte_mes"]["saldo_anterior"]
    assert math.isclose(depois - resumo["aporte_mes"]["saldo_anterior"], 1000)
    with servico.banco.transacao() as con:
        con.execute("UPDATE cargas SET dados = ? WHERE id = ?", (carga["dados"], carga["id"]))
    assert cliente(ambiente, "ana.mkt").get("/api/saldos").status_code == 403


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
    assert {"projecao.salvar", "depara.classificar", "fonte.atualizar"} <= acoes


def test_custo_proximo_mes_automatico(ambiente):
    """Z22 deixa de ser digitado: é o projetado + contas a pagar do próximo mês (coluna S)."""
    resumo = cliente(ambiente, "dora.dir").get(f"/api/resumo?data={HOJE}").json()
    proximo = resumo["aporte_proximo"]
    assert proximo["custo_automatico"] is True
    assert math.isclose(proximo["custo_projetado"], resumo["total"]["projetado_proximo"])
    assert math.isclose(proximo["aporte_total"], max(0, proximo["custo_projetado"] + proximo["caixa_minimo"]
                                                     - proximo["saldo_anterior"] - proximo["receita_projetada"]))


def test_usuario_desativado_perde_acesso(ambiente):
    adm = cliente(ambiente, "edu.adm")
    novo = adm.post("/api/usuarios", json={"email": "temp@joy.test", "nome": "Temp", "perfil": "mkt"}).json()["id"]
    assert cliente(ambiente, novo).get("/api/eu").status_code == 200
    assert adm.patch(f"/api/usuarios/{novo}", json={"ativo": False}).status_code == 200
    assert cliente(ambiente, novo).get("/api/eu").status_code == 401
    assert adm.post("/api/usuarios", json={"email": "x", "nome": "X", "perfil": "mkt"}).status_code == 422


# ------------------------------------------------------------------------ login inativo
def test_sem_login_acesso_direto_com_perfil_fixo(ambiente):
    app = criar_app(servico=ambiente["servico"], login_ativo=False)
    c = TestClient(app)
    assert c.get("/api/config").json() == {"modo": "sem_login"}
    eu = c.get("/api/eu").json()
    assert eu["nome"] == "Acesso livre" and eu["perfil"] == "admin" and eu["login_ativo"] is False
    assert eu["permissoes"]["gerir_usuarios"] is False
    assert c.get(f"/api/resumo?data={HOJE}").status_code == 200
    assert c.get("/api/usuarios").status_code == 409          # gestão de usuários indisponível
    assert c.post("/api/usuarios", json={"email": "a@b.c", "nome": "A", "perfil": "mkt"}).status_code == 409


def test_respostas_da_api_nao_ficam_em_cache(ambiente):
    resposta = cliente(ambiente, "dora.dir").get(f"/api/resumo?data={HOJE}")
    assert resposta.headers["Cache-Control"] == "no-store"


def test_comparativo_projetado_incorrido(ambiente):
    c = cliente(ambiente, "ana.mkt")          # setor consulta qualquer setor (só leitura)
    d = c.get(f"/api/projecao/comparativo?mes=2026-09-30&setor=proj").json()
    rubricas = {p["rubrica"] for p in d["projetado"]}
    assert rubricas == {"Projetos"} and all(i["rubrica"] in rubricas for i in d["incorrido"])
    assert all(i["data"].startswith("2026-09") for i in d["incorrido"])
    assert math.isclose(d["totais"]["incorrido"], sum(i["valor"] for i in d["incorrido"]))
    assert math.isclose(d["totais"]["projetado"], sum(p["valor"] for p in d["projetado"]))
    assert math.isclose(d["totais"]["pago"] + d["totais"]["a_pagar"], d["totais"]["incorrido"])
    todos = c.get("/api/projecao/comparativo?mes=2026-09-30").json()
    assert len(todos["projetado"]) > len(d["projetado"])
    assert c.get("/api/projecao/comparativo?mes=2026-09-30&setor=xyz").status_code == 422


def test_dashboards_coerentes_com_resumo_e_projecao(ambiente):
    dir_ = cliente(ambiente, "dora.dir")
    d = dir_.get(f"/api/dashboards?data={HOJE}").json()
    resumo = dir_.get(f"/api/resumo?data={HOJE}").json()
    serie = d["exposicao"]["serie"]
    acumulado = 0
    for ponto in serie:                                    # acumulado = soma corrida do mensal
        acumulado += ponto["mensal"]
        assert math.isclose(ponto["acumulado"], acumulado, abs_tol=0.01)
    assert d["exposicao"]["pontos"]["B"]["valor"] == min(p["acumulado"] for p in serie)
    mes = d["recebimentos"][-1]
    assert mes["mes"] == resumo["datas"]["mes_atual"]
    assert math.isclose(mes["investidor"] + mes["holding"], resumo["conta"]["aportes_recebidos"])
    assert math.isclose(mes["receitas"], resumo["aporte_mes"]["receita_projetada"])
    comparativo = dir_.get(f"/api/projecao/comparativo?mes={resumo['datas']['mes_atual']}").json()
    no_mes = [v for valores in d["setores"]["valores"].values() for v in valores if v["mes"] == resumo["datas"]["mes_atual"]]
    assert math.isclose(sum(v["incorrido"] for v in no_mes), comparativo["totais"]["incorrido"])
    assert math.isclose(sum(v["projetado"] for v in no_mes), comparativo["totais"]["projetado"])
    assert cliente(ambiente, "ana.mkt").get(f"/api/dashboards?data={HOJE}").status_code == 403


def test_salvar_cronograma_do_aporte(ambiente):
    dir_ = cliente(ambiente, "dora.dir")
    url = "/api/parametros/cronograma"
    parcelas = [{"data": "2026-10-20", "percentual": 40}, {"data": "2026-10-05", "percentual": 60}]
    assert dir_.put(url, json={"mes": "2026-10-31", "parcelas": parcelas}).status_code == 200
    c = dir_.get(f"/api/resumo?data={HOJE}").json()["cronograma_aporte"]
    assert [p["data"] for p in c["parcelas"]] == ["2026-10-05", "2026-10-20"]          # ordenadas por data
    assert math.isclose(sum(p["valor"] for p in c["parcelas"]), c["total"])
    erros = [[{"data": "2026-10-05", "percentual": 60}],                                  # não soma 100%
             [{"data": "2026-11-05", "percentual": 100}],                                 # fora do mês
             [{"data": "2026-10-05", "percentual": 0}, {"data": "2026-10-06", "percentual": 100}]]
    for p in erros:
        assert dir_.put(url, json={"mes": "2026-10-31", "parcelas": p}).status_code == 422
    assert cliente(ambiente, "ana.mkt").put(url, json={"mes": "2026-10-31", "parcelas": parcelas}).status_code == 403
    assert dir_.put(url, json={"mes": "2026-10-31", "parcelas": []}).status_code == 200      # volta à parcela única
    assert not dir_.get(f"/api/resumo?data={HOJE}").json()["cronograma_aporte"]["programado"]


def test_abas_em_breve_exceto_para_admin(ambiente):
    assert cliente(ambiente, "dora.dir").get("/api/eu").json()["em_breve"] == ["dashboards", "painel"]
    assert cliente(ambiente, "edu.adm").get("/api/eu").json()["em_breve"] == []

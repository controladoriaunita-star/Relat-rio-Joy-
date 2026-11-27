"""Login Microsoft 365 (Entra ID) e envio do Resumo por e-mail, com a Microsoft simulada."""
from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.app import auth, config, microsoft
from backend.app.db import Banco
from backend.app.main import criar_app
from backend.app.servicos import Servico

TENANT = "11111111-2222-3333-4444-555555555555"
PDF = b"%PDF-1.4\n% teste\n"


class RespostaFalsa:
    def __init__(self, status: int, dados: dict | None = None):
        self.status_code, self._dados = status, dados or {}

    def json(self):
        return self._dados


class MicrosoftFalsa:
    """Endpoint de token e sendMail. `conta` = claims do id_token devolvido no login."""

    def __init__(self):
        self.conta = {}
        self.chamadas = []
        self.refresh = 0

    def post(self, url, data=None, json=None, headers=None, timeout=None):
        self.chamadas.append({"url": url, "data": data, "json": json, "headers": headers})
        if url.endswith("/oauth2/v2.0/token") and data["grant_type"] == "authorization_code":
            id_token = jwt.encode({"tid": TENANT, **self.conta}, "assinatura-da-microsoft-nao-conferida", algorithm="HS256")
            return RespostaFalsa(200, {"id_token": id_token, "access_token": "at-login", "refresh_token": "rt-0"})
        if url.endswith("/oauth2/v2.0/token") and data["grant_type"] == "refresh_token":
            self.refresh += 1
            return RespostaFalsa(200, {"access_token": f"at-{self.refresh}", "refresh_token": f"rt-{self.refresh}"})
        if url.endswith("/me/sendMail"):
            return RespostaFalsa(202)
        return RespostaFalsa(404)


@pytest.fixture
def ms(monkeypatch):
    monkeypatch.delenv("APORTE_AUTH_LOCAL", raising=False)      # o .env local liga o seletor de perfil
    monkeypatch.setattr(config, "AUTH_MODE", "entra")
    monkeypatch.setattr(config, "ENTRA_TENANT_ID", TENANT)
    monkeypatch.setattr(config, "ENTRA_CLIENT_ID", "cliente-app")
    monkeypatch.setattr(config, "ENTRA_CLIENT_SECRET", "segredo-app")
    monkeypatch.setattr(config, "ENTRA_DOMINIO", "unitaengenharia.com.br")
    monkeypatch.setattr(config, "APP_URL", "")
    monkeypatch.setattr(config, "SESSAO_SEGREDO", "s" * 40)
    falsa = MicrosoftFalsa()
    monkeypatch.setattr(microsoft.requests, "post", falsa.post)
    return falsa


@pytest.fixture
def ambiente(ms, tmp_path):
    banco = Banco(tmp_path / "ms.sqlite3")
    servico = Servico(banco, admin=auth.AdminLocal())
    servico.inicializar()
    ids = {email: servico.criar_usuario(email, email.split("@")[0], perfil, None, None)
           for email, perfil in [("ana@unitaengenharia.com.br", "diretor"), ("caio@unitaengenharia.com.br", "mkt")]}
    app = criar_app(servico=servico, verificador=auth.criar_verificador(banco), login_ativo=True)
    return {"app": app, "banco": banco, "ids": ids, "ms": ms}


def entrar(ambiente, email: str, **claims) -> tuple[TestClient, object]:
    c = TestClient(ambiente["app"], follow_redirects=False)
    ida = c.get("/api/auth/microsoft/login")
    assert ida.status_code == 303
    consulta = parse_qs(urlparse(ida.headers["location"]).query)
    ambiente["ms"].conta = {"email": email, "nonce": consulta["nonce"][0], **claims}
    volta = c.get("/api/auth/microsoft/callback", params={"code": "abc", "state": consulta["state"][0]})
    return c, volta


def test_config_e_url_de_login(ambiente):
    c = TestClient(ambiente["app"], follow_redirects=False)
    assert c.get("/api/config").json() == {"modo": "entra", "dominio": "unitaengenharia.com.br"}
    ida = c.get("/api/auth/microsoft/login")
    url = urlparse(ida.headers["location"])
    consulta = parse_qs(url.query)
    assert url.netloc == "login.microsoftonline.com" and TENANT in url.path
    assert consulta["redirect_uri"] == ["http://testserver/api/auth/microsoft/callback"]
    assert "Mail.Send" in consulta["scope"][0] and consulta["prompt"] == ["select_account"]
    assert c.cookies.get(microsoft.COOKIE_ESTADO) == consulta["state"][0]


def test_login_completo_abre_sessao(ambiente):
    c, volta = entrar(ambiente, "Ana@UnitaEngenharia.com.br")
    assert volta.status_code == 303 and volta.headers["location"] == "/"
    eu = c.get("/api/eu")
    assert eu.status_code == 200 and eu.json()["email"] == "ana@unitaengenharia.com.br"
    guardado = ambiente["banco"].um("SELECT refresh_token FROM tokens_microsoft")["refresh_token"]
    assert "rt-0" not in guardado                         # token fica cifrado no banco


@pytest.mark.parametrize("email, claims, erro", [
    ("joao@unitaengenharia.com.br", {}, "ainda não tem acesso"),
    ("ana@gmail.com", {}, "@unitaengenharia.com.br"),
    ("ana@unitaengenharia.com.br", {"tid": "outro-tenant"}, "outra organização"),
    ("ana@unitaengenharia.com.br", {"nonce": "trocado"}, "Login inválido"),
])
def test_login_recusado(ambiente, email, claims, erro):
    c, volta = entrar(ambiente, email, **claims)
    assert volta.status_code == 303 and volta.headers["location"].startswith("/?erro_login=")
    assert erro in parse_qs(urlparse(volta.headers["location"]).query)["erro_login"][0]
    assert c.get("/api/eu").status_code == 401


def test_state_diferente_do_cookie(ambiente):
    c = TestClient(ambiente["app"], follow_redirects=False)
    c.get("/api/auth/microsoft/login")
    outro = microsoft.assinar("estado:xyz", 600)
    volta = c.get("/api/auth/microsoft/callback", params={"code": "abc", "state": outro})
    assert "expirado" in parse_qs(urlparse(volta.headers["location"]).query)["erro_login"][0]


def test_cookie_falso_nao_entra(ambiente):
    c = TestClient(ambiente["app"])
    c.cookies.set(microsoft.COOKIE_SESSAO, jwt.encode({"sub": ambiente["ids"]["ana@unitaengenharia.com.br"],
                                                       "aud": microsoft.AUDIENCIA}, "x" * 40, algorithm="HS256"))
    assert c.get("/api/eu").status_code == 401


def test_envio_sai_da_conta_do_usuario_e_salva_destinatarios(ambiente):
    c, _ = entrar(ambiente, "ana@unitaengenharia.com.br")
    corpo = {"para": ["Investidor@Fundo.com.br", "investidor@fundo.com.br", "socio@fundo.com.br"],
             "assunto": "Relatório", "mensagem": "Olá,\n\n<b>segue</b>", "nome_arquivo": "Resumo NOV-2026",
             "pdf_base64": base64.b64encode(PDF).decode()}
    r = c.post("/api/obras/berrini/resumo/enviar", json=corpo)
    assert r.status_code == 200, r.text
    assert r.json()["enviado_para"] == ["investidor@fundo.com.br", "socio@fundo.com.br"]
    envio = ambiente["ms"].chamadas[-1]
    assert envio["url"].endswith("/me/sendMail") and envio["headers"]["Authorization"] == "Bearer at-1"
    mensagem = envio["json"]["message"]
    assert [d["emailAddress"]["address"] for d in mensagem["toRecipients"]] == r.json()["enviado_para"]
    assert mensagem["attachments"][0]["name"] == "Resumo NOV-2026.pdf"
    assert base64.b64decode(mensagem["attachments"][0]["contentBytes"]) == PDF
    assert "&lt;b&gt;segue&lt;/b&gt;" in mensagem["body"]["content"]       # texto do usuário escapado

    lista = c.get("/api/obras/berrini/email/destinatarios").json()
    assert [d["email"] for d in lista] == ["investidor@fundo.com.br", "socio@fundo.com.br"]
    assert c.get("/api/obras/evans/email/destinatarios").json() == []      # lista é de cada obra
    assert c.delete(f"/api/obras/berrini/email/destinatarios/{lista[0]['id']}").status_code == 200
    assert [d["email"] for d in c.get("/api/obras/berrini/email/destinatarios").json()] == ["socio@fundo.com.br"]

    # O refresh token novo substitui o anterior a cada envio.
    c.post("/api/obras/berrini/resumo/enviar", json=corpo)
    assert ambiente["ms"].chamadas[-2]["data"]["refresh_token"] == "rt-1"


def test_envio_valida_entrada(ambiente):
    c, _ = entrar(ambiente, "ana@unitaengenharia.com.br")
    base = {"para": ["a@b.com"], "pdf_base64": base64.b64encode(PDF).decode()}
    assert c.post("/api/obras/evans/resumo/enviar", json={**base, "para": ["sem-arroba"]}).status_code == 422
    assert c.post("/api/obras/evans/resumo/enviar", json={**base, "para": []}).status_code == 422
    assert c.post("/api/obras/evans/resumo/enviar",
                  json={**base, "pdf_base64": base64.b64encode(b"nao e pdf").decode()}).status_code == 422
    assert c.post("/api/obras/evans/resumo/enviar", json={**base, "pdf_base64": "@@@"}).status_code == 422


def test_envio_exige_permissao(ambiente):
    c, _ = entrar(ambiente, "caio@unitaengenharia.com.br")              # setor Marketing
    assert c.get("/api/eu").json()["permissoes"]["resumo.enviar"] is False
    assert c.get("/api/obras/evans/email/destinatarios").status_code == 403


def test_sair_apaga_sessao_e_token(ambiente):
    c, _ = entrar(ambiente, "ana@unitaengenharia.com.br")
    assert c.post("/api/auth/sair").status_code == 200
    assert ambiente["banco"].um("SELECT 1 AS x FROM tokens_microsoft") is None
    assert c.get("/api/eu").status_code == 401


def test_sem_auth_mode_continua_supabase(monkeypatch, tmp_path):
    monkeypatch.delenv("APORTE_AUTH_LOCAL", raising=False)
    monkeypatch.setattr(config, "AUTH_MODE", "")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    assert isinstance(auth.criar_verificador(Banco(tmp_path / "s.sqlite3")), auth.VerificadorSupabase)

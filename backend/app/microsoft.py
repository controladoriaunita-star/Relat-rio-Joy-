"""Login Microsoft 365 (Entra ID) e envio de e-mail pelo Graph em nome do usuário logado.

Fluxo (AUTH_MODE=entra):
  1. /api/auth/microsoft/login manda o navegador para a Microsoft com um `state` assinado,
     que também fica num cookie.
  2. A Microsoft volta em /api/auth/microsoft/callback com um `code`. O backend troca o code
     pelos tokens, confere organização, nonce e domínio e procura o e-mail em `profiles`.
     O cadastro e os papéis continuam os do app (API's › Usuários).
  3. A sessão do app é um JWT HS256 próprio num cookie httpOnly, válido por 12 horas.

O escopo Mail.Send (delegado) faz o e-mail sair da caixa de quem está logado. O refresh
token fica cifrado no banco (tokens_microsoft) e só é usado no servidor, na hora do envio.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from urllib.parse import quote, urlencode

import jwt
import requests
from cryptography.fernet import Fernet, InvalidToken

from . import config
from .auth import ErroAutenticacao, papeis_do_usuario
from .db import Banco, agora

COOKIE_SESSAO = "aporte_sessao"
COOKIE_ESTADO = "aporte_login"
CALLBACK = "/api/auth/microsoft/callback"
ESCOPO_EMAIL = "offline_access https://graph.microsoft.com/Mail.Send"
ESCOPOS_LOGIN = f"openid profile email {ESCOPO_EMAIL}"
AUDIENCIA = "aporte-joy"
PREFIXO_ESTADO = "estado:"
GRAPH = "https://graph.microsoft.com/v1.0"
LIMITE_ANEXO = 3 * 1024 * 1024          # o sendMail do Graph aceita anexos de até 3 MB


class ErroMicrosoft(Exception):
    """Falha ao falar com a Microsoft na hora do envio (mensagem já pronta para o usuário)."""


def modo_entra() -> bool:
    return config.AUTH_MODE == "entra"


def configurado() -> bool:
    return all([config.ENTRA_TENANT_ID, config.ENTRA_CLIENT_ID, config.ENTRA_CLIENT_SECRET]) \
        and len(config.SESSAO_SEGREDO) >= 32


# --------------------------------------------------------------------- sessão do app
def _segredo() -> str:
    if len(config.SESSAO_SEGREDO) < 32:
        raise ErroAutenticacao("SESSAO_SEGREDO ausente ou curto (mínimo de 32 caracteres).")
    return config.SESSAO_SEGREDO


def assinar(sub: str, segundos: int) -> str:
    agora_s = int(time.time())
    return jwt.encode({"sub": sub, "aud": AUDIENCIA, "iat": agora_s, "exp": agora_s + segundos},
                      _segredo(), algorithm="HS256")


def ler_assinado(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        return jwt.decode(token, _segredo(), algorithms=["HS256"], audience=AUDIENCIA)
    except (jwt.PyJWTError, ErroAutenticacao):
        return None


def emitir_sessao(usuario_id: str) -> tuple[str, int]:
    duracao = config.SESSAO_HORAS * 3600
    return assinar(usuario_id, duracao), duracao


class VerificadorEntra:
    """Valida o cookie de sessão emitido depois do login Microsoft."""

    def verificar(self, token: str) -> dict:
        claims = ler_assinado(token)
        if not claims or str(claims.get("sub", "")).startswith(PREFIXO_ESTADO):
            raise ErroAutenticacao("Sessão inválida ou expirada.")
        return claims


# --------------------------------------------------------------------- login
def _tenant() -> str:
    return quote(config.ENTRA_TENANT_ID, safe="")


def redirect_uri(url_app: str) -> str:
    return f"{(config.APP_URL or url_app).rstrip('/')}{CALLBACK}"


def url_autorizacao(url_app: str) -> tuple[str, str]:
    """1ª etapa: URL de login da Microsoft e o state assinado (que vai também no cookie)."""
    if not configurado():
        raise ErroAutenticacao("Login Microsoft ainda não configurado (ENTRA_* e SESSAO_SEGREDO).")
    nonce = secrets.token_urlsafe(16)
    estado = assinar(f"{PREFIXO_ESTADO}{nonce}", 600)
    consulta = urlencode({
        "client_id": config.ENTRA_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri(url_app),
        "response_mode": "query",
        "scope": ESCOPOS_LOGIN,
        "state": estado,
        "nonce": nonce,
        "prompt": "select_account",          # sempre mostra a escolha de conta (PC compartilhado)
    })
    return f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0/authorize?{consulta}", estado


def _json(resposta) -> dict:
    try:
        return resposta.json()
    except ValueError:
        return {}


def _pedir_token(http, dados: dict) -> tuple[int, dict]:
    resposta = http.post(f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0/token", timeout=20,
                         data={"client_id": config.ENTRA_CLIENT_ID, "client_secret": config.ENTRA_CLIENT_SECRET,
                               **dados})
    return resposta.status_code, _json(resposta)


def _descricao(dados: dict) -> str:
    return str(dados.get("error_description") or "").split("\r\n")[0].strip()


def concluir_login(banco: Banco, code: str, estado: str, estado_cookie: str | None, url_app: str,
                   http=requests) -> str:
    """2ª etapa: valida o retorno, troca o code e devolve o id (profiles) do usuário do app."""
    st = ler_assinado(estado)
    if not st or not str(st.get("sub", "")).startswith(PREFIXO_ESTADO) or estado != estado_cookie:
        raise ErroAutenticacao("Login expirado. Tente entrar de novo.")
    status, dados = _pedir_token(http, {"grant_type": "authorization_code", "code": code,
                                        "redirect_uri": redirect_uri(url_app), "scope": ESCOPOS_LOGIN})
    if status >= 300 or not dados.get("id_token"):
        raise ErroAutenticacao(f"A Microsoft recusou o login. {_descricao(dados)}".strip())

    # O id_token veio direto do endpoint de token (TLS + client secret): basta ler as claims.
    try:
        claims = jwt.decode(dados["id_token"], options={"verify_signature": False})
    except jwt.PyJWTError as erro:
        raise ErroAutenticacao("Resposta de login inválida. Tente de novo.") from erro
    if claims.get("tid") and claims["tid"] != config.ENTRA_TENANT_ID:
        raise ErroAutenticacao("Conta de outra organização.")
    if claims.get("nonce") != st["sub"][len(PREFIXO_ESTADO):]:
        raise ErroAutenticacao("Login inválido. Tente de novo.")

    email = str(claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    if not email.endswith(f"@{config.ENTRA_DOMINIO}"):
        raise ErroAutenticacao(f"Entre com sua conta @{config.ENTRA_DOMINIO}.")
    perfil = banco.um("SELECT CAST(id AS TEXT) AS id, active FROM profiles WHERE lower(email) = ?", email)
    if not perfil or not perfil["active"] or not papeis_do_usuario(banco, perfil["id"]):
        raise ErroAutenticacao("Seu usuário ainda não tem acesso. Peça a liberação a quem administra o app.")
    if dados.get("refresh_token"):
        guardar_token(banco, perfil["id"], dados["refresh_token"])
    return perfil["id"]


# --------------------------------------------------------------------- token de e-mail (cifrado)
def _cifra() -> Fernet:
    chave = hashlib.sha256(f"tokens-microsoft:{_segredo()}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(chave))


def guardar_token(banco: Banco, usuario_id: str, refresh_token: str) -> None:
    banco.executar("INSERT INTO tokens_microsoft (usuario_id, refresh_token, atualizado_em) VALUES (?, ?, ?) "
                   "ON CONFLICT (usuario_id) DO UPDATE SET refresh_token = excluded.refresh_token, "
                   "atualizado_em = excluded.atualizado_em",
                   usuario_id, _cifra().encrypt(refresh_token.encode()).decode(), agora())


def apagar_token(banco: Banco, usuario_id: str) -> None:
    banco.executar("DELETE FROM tokens_microsoft WHERE usuario_id = ?", usuario_id)


def _token_graph(banco: Banco, usuario_id: str, http) -> str:
    sem_acesso = "Saia e entre de novo com a Microsoft para liberar o envio de e-mail."
    linha = banco.um("SELECT refresh_token FROM tokens_microsoft WHERE usuario_id = ?", usuario_id)
    if not linha:
        raise ErroMicrosoft(sem_acesso)
    try:
        refresh_token = _cifra().decrypt(linha["refresh_token"].encode()).decode()
    except InvalidToken as erro:
        raise ErroMicrosoft(sem_acesso) from erro
    status, dados = _pedir_token(http, {"grant_type": "refresh_token", "refresh_token": refresh_token,
                                        "scope": ESCOPO_EMAIL})
    if status >= 300 or not dados.get("access_token"):
        raise ErroMicrosoft(f"{sem_acesso} {_descricao(dados)}".strip())
    if dados.get("refresh_token"):
        guardar_token(banco, usuario_id, dados["refresh_token"])
    return dados["access_token"]


def enviar_email(banco: Banco, usuario_id: str, para: list[str], assunto: str, html: str,
                 anexo_nome: str, anexo: bytes, http=requests) -> None:
    """Envia pela caixa do próprio usuário (fica nos Itens Enviados dele)."""
    if len(anexo) > LIMITE_ANEXO:
        raise ErroMicrosoft("O PDF passou de 3 MB, o limite do Outlook para este envio.")
    token = _token_graph(banco, usuario_id, http)
    mensagem = {
        "subject": assunto,
        "body": {"contentType": "HTML", "content": html},
        "toRecipients": [{"emailAddress": {"address": e}} for e in para],
        "attachments": [{"@odata.type": "#microsoft.graph.fileAttachment", "name": anexo_nome,
                         "contentType": "application/pdf",
                         "contentBytes": base64.b64encode(anexo).decode()}],
    }
    resposta = http.post(f"{GRAPH}/me/sendMail", json={"message": mensagem, "saveToSentItems": True},
                         headers={"Authorization": f"Bearer {token}"}, timeout=40)
    if resposta.status_code != 202:
        detalhe = (_json(resposta).get("error") or {}).get("message") or f"erro {resposta.status_code}"
        raise ErroMicrosoft(f"O Outlook recusou o envio: {detalhe}")

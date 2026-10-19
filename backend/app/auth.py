"""Autenticação (Supabase Auth) e permissões.

O login acontece no navegador com o supabase-js; o backend recebe o access token
(JWT) no cabeçalho Authorization e o valida. O perfil de cada usuário fica na
tabela `perfis`: "adm" (desenvolvedores), "diretor" (Diretoria) ou o código de um
setor ("mkt", "proj", "inc"...). Um setor novo cria um perfil novo.
"""
from __future__ import annotations

import os
from typing import Protocol

import jwt
import requests

from . import config
from .db import Banco, agora

PERFIS_GESTORES = {"adm", "diretor"}
PREFIXO_TOKEN_LOCAL = "local:"


class ErroAutenticacao(Exception):
    pass


class Verificador(Protocol):
    def verificar(self, token: str) -> dict:
        """Devolve as claims (precisa de "sub") ou levanta ErroAutenticacao."""


class VerificadorSupabase:
    def __init__(self):
        self._jwks = None
        self._emissor = f"{config.SUPABASE_URL}/auth/v1"

    def verificar(self, token: str) -> dict:
        opcoes = {"audience": "authenticated", "issuer": self._emissor}
        try:
            if config.SUPABASE_JWT_SECRET:            # projetos com segredo HS256 (legado)
                return jwt.decode(token, config.SUPABASE_JWT_SECRET, algorithms=["HS256"], **opcoes)
            if self._jwks is None:                    # chaves assimétricas (padrão atual)
                self._jwks = jwt.PyJWKClient(f"{self._emissor}/.well-known/jwks.json", cache_keys=True)
            chave = self._jwks.get_signing_key_from_jwt(token)
            return jwt.decode(token, chave.key, algorithms=["ES256", "RS256"], **opcoes)
        except jwt.PyJWTError as erro:
            raise ErroAutenticacao("Sessão inválida ou expirada.") from erro


class VerificadorLocal:
    """Somente desenvolvimento: aceita "local:<usuario_id>" (ver modo_local())."""

    def verificar(self, token: str) -> dict:
        if not token.startswith(PREFIXO_TOKEN_LOCAL):
            raise ErroAutenticacao("Token local inválido.")
        return {"sub": token[len(PREFIXO_TOKEN_LOCAL):]}


def modo_local(banco: Banco) -> bool:
    """Modo de desenvolvimento sem Supabase: exige SQLite, a flag explícita e não estar na Vercel."""
    return (not banco.postgres and os.environ.get("APORTE_AUTH_LOCAL") == "1"
            and not os.environ.get("VERCEL"))


def criar_verificador(banco: Banco) -> Verificador:
    if modo_local(banco):
        return VerificadorLocal()
    if not config.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL não configurada (ou ative APORTE_AUTH_LOCAL=1 em desenvolvimento).")
    return VerificadorSupabase()


def usuario_do_token(banco: Banco, verificador: Verificador, token: str | None) -> dict | None:
    if not token:
        return None
    try:
        claims = verificador.verificar(token)
    except ErroAutenticacao:
        return None
    perfil = banco.um("SELECT usuario_id, email, nome, perfil FROM perfis WHERE usuario_id = ? AND ativo = 1",
                      str(claims["sub"]))
    if not perfil:
        return None
    return {**perfil, "id": perfil["usuario_id"], "login": perfil["email"]}


# --------------------------------------------------------------------- Admin API do Supabase
class AdminUsuarios(Protocol):
    def criar(self, email: str, nome: str, senha: str | None) -> str: ...
    def alterar(self, usuario_id: str, senha: str | None = None, bloqueado: bool | None = None) -> None: ...


class AdminSupabase:
    """Cria e altera usuários pela Admin API (exige a service role key, só no servidor)."""

    def _cabecalhos(self) -> dict:
        if not config.SUPABASE_SERVICE_ROLE_KEY:
            raise ErroAutenticacao("SUPABASE_SERVICE_ROLE_KEY não configurada.")
        chave = config.SUPABASE_SERVICE_ROLE_KEY
        return {"apikey": chave, "Authorization": f"Bearer {chave}"}

    def criar(self, email: str, nome: str, senha: str | None) -> str:
        base = f"{config.SUPABASE_URL}/auth/v1"
        if senha:
            resposta = requests.post(f"{base}/admin/users", headers=self._cabecalhos(), timeout=30, json={
                "email": email, "password": senha, "email_confirm": True, "user_metadata": {"nome": nome}})
        else:                                           # sem senha: envia convite por e-mail
            resposta = requests.post(f"{base}/invite", headers=self._cabecalhos(), timeout=30,
                                     json={"email": email, "data": {"nome": nome}})
        if resposta.status_code >= 300:
            raise ErroAutenticacao(f"Supabase recusou o usuário: {resposta.json().get('msg', resposta.text)[:200]}")
        return resposta.json()["id"]

    def alterar(self, usuario_id: str, senha: str | None = None, bloqueado: bool | None = None) -> None:
        corpo = {}
        if senha:
            corpo["password"] = senha
        if bloqueado is not None:
            corpo["ban_duration"] = "876000h" if bloqueado else "none"
        if not corpo:
            return
        resposta = requests.put(f"{config.SUPABASE_URL}/auth/v1/admin/users/{usuario_id}",
                                headers=self._cabecalhos(), json=corpo, timeout=30)
        if resposta.status_code >= 300:
            raise ErroAutenticacao(f"Supabase recusou a alteração: {resposta.text[:200]}")


class AdminLocal:
    """Desenvolvimento/testes: usuários só na tabela perfis."""

    def criar(self, email: str, nome: str, senha: str | None) -> str:
        return f"local-{email.lower()}"

    def alterar(self, usuario_id: str, senha: str | None = None, bloqueado: bool | None = None) -> None:
        return None


def registrar_perfil(banco: Banco, usuario_id: str, email: str, nome: str, perfil: str,
                     autor: str | None = None) -> None:
    with banco.transacao() as con:
        con.execute("INSERT INTO perfis (usuario_id, email, nome, perfil, criado_em) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT (usuario_id) DO UPDATE SET email = excluded.email, nome = excluded.nome, "
                    "perfil = excluded.perfil, ativo = 1",
                    (usuario_id, email.strip().lower(), nome.strip(), perfil, agora()))
        banco.registrar(con, autor, "usuario.salvar", {"email": email, "perfil": perfil})


# --------------------------------------------------------------------- permissões
def eh_gestor(usuario: dict) -> bool:
    return usuario["perfil"] in PERFIS_GESTORES


def pode_editar_setor(usuario: dict, codigo_setor: str) -> bool:
    return eh_gestor(usuario) or usuario["perfil"] == codigo_setor


def permissoes(usuario: dict) -> dict:
    gestor = eh_gestor(usuario)
    return {
        "ver_apis": gestor,
        "editar_premissas": gestor,
        "atualizar_fontes": gestor,
        "classificar": gestor,
        "editar_saldos": gestor,
        "editar_meses_passados": gestor,
        "administrar": usuario["perfil"] == "adm",
    }

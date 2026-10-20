"""Autenticação (Supabase Auth) e permissões.

O login acontece no navegador com o supabase-js; o backend recebe o access token
(JWT) no cabeçalho Authorization e o valida. As permissões seguem o padrão Unità:
profiles, roles, permissions, role_permissions e user_roles. Os papéis são "admin"
(desenvolvedores), "diretor" (Diretoria) e um por setor, com a chave do código do
setor ("mkt", "proj", "inc"...). Um setor novo cria o papel correspondente.
"""
from __future__ import annotations

import os
import uuid
from typing import Protocol

import jwt
import requests

from . import config
from .catalogo import PAPEIS_GERAIS, PERMISSOES
from .db import Banco

PAPEIS_RESERVADOS = set(PAPEIS_GERAIS)        # não podem virar código de setor
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


def usuario_sem_login(banco: Banco) -> dict:
    """Usuário único usado enquanto o login está inativo (config.LOGIN_ATIVO = False)."""
    return _montar_usuario(banco, {"id": "sem-login", "email": "", "full_name": "Acesso livre"},
                           [config.PERFIL_SEM_LOGIN])


def usuario_do_token(banco: Banco, verificador: Verificador, token: str | None) -> dict | None:
    if not token:
        return None
    try:
        claims = verificador.verificar(token)
    except ErroAutenticacao:
        return None
    perfil = banco.um("SELECT CAST(id AS TEXT) AS id, email, full_name FROM profiles WHERE id = ? AND active",
                      str(claims["sub"]))
    papeis = papeis_do_usuario(banco, perfil["id"]) if perfil else []
    return _montar_usuario(banco, perfil, papeis) if papeis else None


def _montar_usuario(banco: Banco, perfil: dict, papeis: list[str]) -> dict:
    papeis = sorted(papeis, key=lambda k: (k not in PAPEIS_GERAIS, list(PAPEIS_GERAIS).index(k)
                                           if k in PAPEIS_GERAIS else 0, k))
    concedidas = permissoes_dos_papeis(banco, papeis)
    return {"id": perfil["id"], "usuario_id": perfil["id"], "email": perfil["email"] or "",
            "login": perfil["email"] or perfil["id"], "nome": perfil["full_name"],
            "papeis": papeis, "perfil": papeis[0],
            "permissoes": {p: p in concedidas for p in PERMISSOES}}


def papeis_do_usuario(banco: Banco, usuario_id: str) -> list[str]:
    return [l["key"] for l in banco.todos("SELECT r.key FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
                                          "WHERE ur.user_id = ?", usuario_id)]


def permissoes_dos_papeis(banco: Banco, papeis: list[str]) -> set[str]:
    if not papeis:
        return set()
    marcas = ", ".join("?" * len(papeis))
    return {l["key"] for l in banco.todos(
        "SELECT DISTINCT p.key FROM roles r JOIN role_permissions rp ON rp.role_id = r.id "
        f"JOIN permissions p ON p.id = rp.permission_id WHERE r.key IN ({marcas})", *papeis)}


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
                "email": email, "password": senha, "email_confirm": True, "user_metadata": {"full_name": nome}})
        else:                                           # sem senha: envia convite por e-mail
            resposta = requests.post(f"{base}/invite", headers=self._cabecalhos(), timeout=30,
                                     json={"email": email, "data": {"full_name": nome}})
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
    """Desenvolvimento/testes: usuários só na tabela profiles."""

    def criar(self, email: str, nome: str, senha: str | None) -> str:
        return f"local-{email.lower()}"

    def alterar(self, usuario_id: str, senha: str | None = None, bloqueado: bool | None = None) -> None:
        return None


def uuid_ou_none(valor: str | None) -> str | None:
    """granted_by referencia auth.users: só um uuid real entra (o usuário "sem-login" não)."""
    try:
        return str(uuid.UUID(str(valor)))
    except ValueError:
        return None


def registrar_usuario(banco: Banco, usuario_id: str, email: str, nome: str, papel: str,
                      autor: dict | None = None) -> None:
    """Grava o profile e deixa o usuário com um único papel (o perfil escolhido na tela)."""
    with banco.transacao() as con:
        con.execute("INSERT INTO profiles (id, full_name, email, active) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (id) DO UPDATE SET full_name = excluded.full_name, email = excluded.email, "
                    "active = excluded.active", (usuario_id, nome.strip(), email.strip().lower(), True))
        con.execute("DELETE FROM user_roles WHERE user_id = ?", (usuario_id,))
        con.execute("INSERT INTO user_roles (id, user_id, role_id, granted_by) "
                    "SELECT ?, ?, id, ? FROM roles WHERE key = ?",
                    (str(uuid.uuid4()), usuario_id, uuid_ou_none(autor and autor["id"]), papel))
        banco.registrar(con, autor and autor["login"], "usuario.salvar", {"email": email, "papel": papel})


# --------------------------------------------------------------------- permissões
def permissoes(usuario: dict) -> dict[str, bool]:
    return usuario["permissoes"]


def pode_editar_setor(usuario: dict, codigo_setor: str) -> bool:
    return permissoes(usuario)["projecao.editar_todos_setores"] or codigo_setor in usuario["papeis"]

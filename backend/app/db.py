"""Persistência: Postgres (Supabase) em produção, SQLite nos testes e no uso local.

O SQL dos serviços é escrito uma vez, no subconjunto comum aos dois bancos
(placeholders "?", ON CONFLICT, RETURNING). O esquema do Postgres fica em
supabase/migrations; o do SQLite está abaixo, com as mesmas tabelas.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

ESQUEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS perfis (
    usuario_id TEXT PRIMARY KEY, email TEXT NOT NULL, nome TEXT NOT NULL, perfil TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1, criado_em TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS setores (
    id INTEGER PRIMARY KEY, codigo TEXT NOT NULL UNIQUE, nome TEXT NOT NULL,
    ordem INTEGER NOT NULL DEFAULT 0, ativo INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS linhas_projecao (
    id INTEGER PRIMARY KEY, setor_id INTEGER NOT NULL REFERENCES setores(id),
    nome TEXT NOT NULL, rubrica TEXT NOT NULL, ordem INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1, UNIQUE (setor_id, nome));
CREATE TABLE IF NOT EXISTS projecoes (
    linha_id INTEGER NOT NULL REFERENCES linhas_projecao(id), mes TEXT NOT NULL,
    valor REAL NOT NULL, atualizado_por TEXT, atualizado_em TEXT, PRIMARY KEY (linha_id, mes));
CREATE TABLE IF NOT EXISTS depara (
    fonte TEXT NOT NULL, chave TEXT NOT NULL, concat TEXT NOT NULL, classificacao TEXT NOT NULL,
    atualizado_por TEXT, atualizado_em TEXT, PRIMARY KEY (fonte, chave));
CREATE TABLE IF NOT EXISTS saldos (
    id INTEGER PRIMARY KEY, empresa INTEGER NOT NULL, conta TEXT NOT NULL, descricao TEXT,
    data TEXT NOT NULL, saldo REAL NOT NULL, UNIQUE (empresa, conta, data));
CREATE TABLE IF NOT EXISTS parametros (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cargas (
    id INTEGER PRIMARY KEY, fonte TEXT NOT NULL, origem TEXT NOT NULL, iniciado_em TEXT NOT NULL,
    duracao_s REAL, status TEXT NOT NULL, linhas INTEGER, mensagem TEXT, dados TEXT);
CREATE INDEX IF NOT EXISTS ix_cargas_fonte ON cargas (fonte, id);
CREATE TABLE IF NOT EXISTS historico (
    id INTEGER PRIMARY KEY, quando TEXT NOT NULL, usuario TEXT, acao TEXT NOT NULL, detalhe TEXT);
CREATE TABLE IF NOT EXISTS controle (id INTEGER PRIMARY KEY CHECK (id = 1), versao INTEGER NOT NULL);
INSERT INTO controle (id, versao) VALUES (1, 0) ON CONFLICT (id) DO NOTHING;
"""


def _json_padrao(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    raise TypeError(type(valor))


def para_json(valor) -> str:
    return json.dumps(valor, default=_json_padrao, ensure_ascii=False)


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ErroIntegridade(Exception):
    """Violação de chave única/estrangeira, igual nos dois bancos."""


class _ConexaoPostgres:
    """Adapta o psycopg para a interface do sqlite3 usada pelos serviços."""

    _PLACEHOLDER = re.compile(r"\?")

    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row
        self._psycopg = psycopg
        # prepare_threshold=None: compatível com o pooler do Supabase (modo transação).
        self._con = psycopg.connect(url, autocommit=True, row_factory=dict_row, prepare_threshold=None)

    def execute(self, sql: str, args=()):
        try:
            return self._con.execute(self._PLACEHOLDER.sub("%s", sql), tuple(args))
        except self._psycopg.errors.IntegrityError as erro:
            raise ErroIntegridade(str(erro)) from erro

    @property
    def fechada(self) -> bool:
        return self._con.closed


class Banco:
    def __init__(self, destino: str | Path):
        self._trava = threading.RLock()
        self.url = str(destino)
        self.postgres = self.url.startswith(("postgres://", "postgresql://"))
        self._versao_cache = None
        if self.postgres:
            self.caminho = None
            self._con = _ConexaoPostgres(self.url)
        else:
            self.caminho = Path(destino)
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
            self._con = sqlite3.connect(self.caminho, check_same_thread=False, isolation_level=None)
            self._con.row_factory = sqlite3.Row
            self._con.execute("PRAGMA foreign_keys = ON")
            self._con.executescript(ESQUEMA_SQLITE)

    def _conexao(self):
        if self.postgres and self._con.fechada:          # reconexão em funções serverless
            self._con = _ConexaoPostgres(self.url)
        return self._con

    def _executar(self, con, sql: str, args=()):
        try:
            return con.execute(sql, args)
        except sqlite3.IntegrityError as erro:
            raise ErroIntegridade(str(erro)) from erro

    @contextmanager
    def transacao(self):
        """Bloco atômico. Toda escrita incrementa a versão (invalida caches de cálculo)."""
        with self._trava:
            con = self._conexao()
            con.execute("BEGIN")
            try:
                yield _Executor(self, con)
                con.execute("UPDATE controle SET versao = versao + 1 WHERE id = 1")
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise

    def todos(self, sql: str, *args) -> list[dict]:
        with self._trava:
            return [dict(r) for r in self._executar(self._conexao(), sql, args).fetchall()]

    def um(self, sql: str, *args) -> dict | None:
        linhas = self.todos(sql, *args)
        return linhas[0] if linhas else None

    @property
    def versao(self) -> int:
        """Versão global dos dados, compartilhada entre instâncias (fica no banco)."""
        return self.um("SELECT versao FROM controle WHERE id = 1")["versao"]

    # ------------------------------------------------------------------ parâmetros
    def parametro(self, chave: str, padrao=None):
        linha = self.um("SELECT valor FROM parametros WHERE chave = ?", chave)
        return json.loads(linha["valor"]) if linha else padrao

    def salvar_parametro(self, chave: str, valor) -> None:
        with self.transacao() as con:
            con.execute("INSERT INTO parametros (chave, valor) VALUES (?, ?) "
                        "ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor",
                        (chave, para_json(valor)))

    def registrar(self, con, usuario: str | None, acao: str, detalhe=None) -> None:
        con.execute("INSERT INTO historico (quando, usuario, acao, detalhe) VALUES (?, ?, ?, ?)",
                    (agora(), usuario, acao, para_json(detalhe) if detalhe is not None else None))


class _Executor:
    """Conexão dentro de uma transação, com erros de integridade padronizados."""

    def __init__(self, banco: Banco, con):
        self._banco, self._con = banco, con

    def execute(self, sql: str, args=()):
        return self._banco._executar(self._con, sql, args)

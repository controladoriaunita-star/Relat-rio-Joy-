"""Validação do JWT do Supabase Auth (assinatura, audiência, emissor e expiração)."""
from __future__ import annotations

import time

import jwt
import pytest

from backend.app import auth, config

SEGREDO = "segredo-de-teste-com-mais-de-32-caracteres"
URL = "https://projeto-teste.supabase.co"


@pytest.fixture
def verificador(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", URL)
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", SEGREDO)
    return auth.VerificadorSupabase()


def token(**alteracoes) -> str:
    claims = {"sub": "0b8f0c2e-0000-4000-8000-000000000001", "aud": "authenticated",
              "iss": f"{URL}/auth/v1", "exp": int(time.time()) + 600, **alteracoes}
    return jwt.encode(claims, alteracoes.pop("_segredo", SEGREDO), algorithm="HS256")


def test_token_valido(verificador):
    assert verificador.verificar(token())["sub"].startswith("0b8f0c2e")


@pytest.mark.parametrize("alteracao", [
    {"aud": "anon"},
    {"iss": "https://outro.supabase.co/auth/v1"},
    {"exp": int(time.time()) - 10},
])
def test_token_rejeitado(verificador, alteracao):
    with pytest.raises(auth.ErroAutenticacao):
        verificador.verificar(token(**alteracao))


def test_assinatura_errada(verificador):
    falso = jwt.encode({"sub": "x", "aud": "authenticated", "iss": f"{URL}/auth/v1",
                        "exp": int(time.time()) + 600}, "outro-segredo-qualquer-com-32-caracteres!", algorithm="HS256")
    with pytest.raises(auth.ErroAutenticacao):
        verificador.verificar(falso)


def test_modo_local_nunca_na_vercel(monkeypatch, tmp_path):
    from backend.app.db import Banco
    banco = Banco(tmp_path / "x.sqlite3")
    monkeypatch.setenv("APORTE_AUTH_LOCAL", "1")
    assert auth.modo_local(banco)
    monkeypatch.setenv("VERCEL", "1")
    assert not auth.modo_local(banco)

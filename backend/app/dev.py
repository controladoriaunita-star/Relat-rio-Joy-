"""Servidor local para testar os acessos de cada perfil, sem Supabase.

  python -m backend.app.dev [porta]        (padrão 8061)

Usa o SQLite de data/ (nunca o Postgres do .env), liga o login com o seletor de
perfil e cria um usuário de teste por papel (admin, diretor e cada setor). O Graph
continua o do .env, então "Atualizar do SharePoint" funciona igual à produção.
"""
from __future__ import annotations

import os
import sys

# Antes de importar config: o .env não sobrescreve variáveis já definidas.
os.environ["DATABASE_URL"] = ""
os.environ["APORTE_AUTH_LOCAL"] = "1"
os.environ["APORTE_LOGIN_ATIVO"] = "1"

import uvicorn  # noqa: E402

from . import auth, config  # noqa: E402
from .db import Banco  # noqa: E402
from .main import criar_app  # noqa: E402
from .servicos import Servico  # noqa: E402


def preparar(servico: Servico) -> None:
    servico.inicializar()
    if not servico.banco.um("SELECT 1 FROM cargas LIMIT 1") and config.ARQUIVO_EXCEL.exists():
        print("Primeira execução: carregando dados da planilha...")
        servico.migrar_do_excel()
    com_usuario = {p for u in servico.listar_usuarios() if u["ativo"] for p in u["papeis"]}
    for papel, nome in servico.perfis().items():
        if papel not in com_usuario:
            auth.registrar_usuario(servico.banco, f"teste-{papel}", f"{papel}@teste.local", f"{nome} (teste)", papel)


def main(argumentos: list[str]) -> None:
    porta = int(argumentos[0]) if argumentos else 8061
    servico = Servico(Banco(config.DATABASE_URL))
    preparar(servico)
    print(f"Teste de perfis em http://127.0.0.1:{porta} (SQLite: {config.DATABASE_URL})")
    uvicorn.run(criar_app(servico), host="127.0.0.1", port=porta)


if __name__ == "__main__":
    main(sys.argv[1:])

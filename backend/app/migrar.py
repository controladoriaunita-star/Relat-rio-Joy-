"""Comandos de implantação.

  python -m backend.app.migrar planilha [--obra evans] [--sem-projecao] [--sem-viabilidade]
      Carga inicial a partir da planilha de controle da obra (padrão: evans): DePara, as sete
      fontes (inclusive os saldos bancários), a viabilidade (coluna D do Resumo) e a projeção
      (sem os blocos duplicados da Projeção_2).
  python -m backend.app.migrar admin <email> "<nome>" [senha]
      Cria o primeiro administrador (sem senha, o Supabase envia convite por e-mail).

O banco é o de DATABASE_URL (Supabase) ou o SQLite local em data/.
"""
from __future__ import annotations

import json
import sys

from .config import DATABASE_URL
from .db import Banco
from .obras import OBRA_PADRAO
from .servicos import Servico


def main(argumentos: list[str]) -> None:
    servico = Servico(Banco(DATABASE_URL))
    servico.inicializar()
    comando = argumentos[0] if argumentos else "planilha"
    if comando == "planilha":
        obra = argumentos[argumentos.index("--obra") + 1] if "--obra" in argumentos else OBRA_PADRAO
        relatorio = servico.obra(obra).migrar_do_excel(importar_projecao="--sem-projecao" not in argumentos,
                                                       importar_viabilidade="--sem-viabilidade" not in argumentos)
        print(json.dumps(relatorio, ensure_ascii=False, indent=2, default=str))
    elif comando == "admin" and len(argumentos) >= 3:
        senha = argumentos[3] if len(argumentos) > 3 else None
        usuario_id = servico.criar_usuario(argumentos[1], argumentos[2], "admin", senha, None)
        print(f"Administrador criado: {argumentos[1]} ({usuario_id})")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])

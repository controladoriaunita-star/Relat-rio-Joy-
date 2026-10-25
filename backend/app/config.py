"""Configuração central: caminhos, variáveis de ambiente e constantes de negócio."""
from __future__ import annotations

import os
from pathlib import Path

RAIZ_SISTEMA = Path(__file__).resolve().parents[2]
RAIZ_PROJETO = RAIZ_SISTEMA.parent
PASTA_WEB = RAIZ_SISTEMA / "public"      # na Vercel, servida como estático
PASTA_DADOS = Path(os.environ.get("APORTE_DATA_DIR", RAIZ_SISTEMA / "data"))
ARQUIVO_EXCEL = RAIZ_PROJETO / "Controle - Joy+ Evans.xlsm"


def _carregar_env(caminho: Path) -> None:
    """Lê o .env local (chave=valor) sem sobrescrever variáveis já definidas."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip())


_carregar_env(RAIZ_SISTEMA / ".env")

# Banco: Postgres do Supabase em produção (use a URL do pooler, porta 6543);
# sem DATABASE_URL, usa SQLite local em data/.
DATABASE_URL = os.environ.get("DATABASE_URL") or str(PASTA_DADOS / "aporte.sqlite3")

# Login (Supabase Auth). Temporariamente INATIVO: todos entram com o perfil
# PERFIL_SEM_LOGIN. Para reativar a tela de login, defina APORTE_LOGIN_ATIVO=1.
LOGIN_ATIVO = os.environ.get("APORTE_LOGIN_ATIVO", "0") == "1"
PERFIL_SEM_LOGIN = os.environ.get("APORTE_PERFIL_SEM_LOGIN", "admin")
PERFIL_SEM_LOGIN = {"adm": "admin"}.get(PERFIL_SEM_LOGIN, PERFIL_SEM_LOGIN)   # nome antigo do papel

# Supabase Auth. A anon key vai para o navegador; a service role key nunca.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")   # só projetos com HS256

GRAPH_TENANT_ID = os.environ.get("GRAPH_TENANT_ID", "")
GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID", "")
GRAPH_CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET", "")
GRAPH_DRIVE_ID = os.environ.get("GRAPH_DRIVE_ID", "")
GRAPH_ITEM_ID = os.environ.get("GRAPH_ITEM_ID", "")

# --- Regras de negócio fixas nas fórmulas da planilha -------------------------
EMPRESA_SPE = 73                                  # código da SPE Evans no UAU
CLIENTE_INVESTIDOR = 8213                         # Recebidas[CódigoCliente] do investidor
HISTORICO_APORTE_INVESTIDOR = "APORTE Bapema Kalil Evans I Spe Ltda"

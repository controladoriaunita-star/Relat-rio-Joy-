"""Função serverless da Vercel: expõe a API FastAPI (todas as rotas /api/*)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.main import criar_app  # noqa: E402

app = criar_app()

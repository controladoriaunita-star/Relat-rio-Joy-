"""API REST do Relatório de Aporte Joy+ Evans.

Produção (Vercel): api/index.py expõe `app = criar_app()`; os arquivos de public/
são servidos pela CDN da Vercel e o banco é o Postgres do Supabase.
Local: python -m uvicorn backend.app.main:criar_app --factory --port 8060
"""
from __future__ import annotations

import dataclasses
import os
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, config
from .db import Banco, ErroIntegridade
from .servicos import ErroNegocio, Servico


class ItemProjecao(BaseModel):
    linha_id: int
    mes: date
    valor: float


class PedidoAtualizacao(BaseModel):
    origem: str = "graph"
    fontes: list[str] | None = None


class Classificacao(BaseModel):
    concat: str
    classificacao: str


class NovoUsuario(BaseModel):
    email: str
    nome: str
    perfil: str
    senha: str | None = None        # sem senha: convite por e-mail


class AlteraUsuario(BaseModel):
    nome: str | None = None
    perfil: str | None = None
    ativo: bool | None = None
    senha: str | None = None


class ArquivosEstaticos(StaticFiles):
    """Interface servida localmente, sempre revalidada para cada versão nova chegar ao usuário."""

    def file_response(self, *args, **kwargs):
        resposta = super().file_response(*args, **kwargs)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta


def criar_app(servico: Servico | None = None, verificador: auth.Verificador | None = None,
              login_ativo: bool | None = None) -> FastAPI:
    servico = servico or Servico(Banco(config.DATABASE_URL))
    servico.inicializar()
    banco = servico.banco
    login_ativo = config.LOGIN_ATIVO if login_ativo is None else login_ativo
    if login_ativo:
        verificador = verificador or auth.criar_verificador(banco)
    local = isinstance(verificador, auth.VerificadorLocal)

    app = FastAPI(title="Relatório de Aporte · Joy+ Evans", docs_url="/api/docs",
                  openapi_url="/api/openapi.json", redoc_url=None)
    app.state.servico = servico

    @app.exception_handler(ErroNegocio)
    async def _erro_negocio(_: Request, erro: ErroNegocio):
        return JSONResponse({"detail": str(erro)}, status_code=422)

    @app.exception_handler(ErroIntegridade)
    async def _erro_integridade(_: Request, erro: ErroIntegridade):
        return JSONResponse({"detail": "Registro duplicado ou inválido."}, status_code=409)

    # ------------------------------------------------------------------ dependências
    def usuario_atual(request: Request) -> dict:
        if not login_ativo:                      # login inativo: acesso direto com perfil fixo
            return auth.usuario_sem_login()
        cabecalho = request.headers.get("Authorization", "")
        token = cabecalho[7:] if cabecalho.lower().startswith("bearer ") else None
        usuario = auth.usuario_do_token(banco, verificador, token)
        if not usuario:
            raise HTTPException(401, "Sessão expirada ou usuário sem perfil. Entre novamente.")
        return usuario

    def exigir(permissao: str):
        def verificar(usuario: dict = Depends(usuario_atual)) -> dict:
            if not auth.permissoes(usuario)[permissao]:
                raise HTTPException(403, "Seu perfil não tem acesso a esta ação.")
            return usuario
        return verificar

    def exigir_login_ativo() -> None:
        if not login_ativo:
            raise HTTPException(409, "O login está inativo; a gestão de usuários fica indisponível.")

    def data_base(data: date | None = None) -> date:
        return data or date.today()

    # ------------------------------------------------------------------ sessão
    @app.get("/api/config")
    def configuracao():
        """Dados públicos para o navegador iniciar o supabase-js (a anon key é pública)."""
        if not login_ativo:
            return {"modo": "sem_login"}
        if local:
            return {"modo": "local", "usuarios": banco.todos(
                "SELECT usuario_id, nome, perfil FROM perfis WHERE ativo = 1 ORDER BY nome")}
        return {"modo": "supabase", "supabase_url": config.SUPABASE_URL,
                "supabase_anon_key": config.SUPABASE_ANON_KEY}

    @app.get("/api/eu")
    def eu(usuario: dict = Depends(usuario_atual)):
        permissoes = {**auth.permissoes(usuario), "gerir_usuarios": login_ativo and usuario["perfil"] == "adm"}
        return {**usuario, "permissoes": permissoes, "login_ativo": login_ativo,
                "perfil_nome": servico.perfis().get(usuario["perfil"], usuario["perfil"])}

    # ------------------------------------------------------------------ relatórios
    @app.get("/api/resumo")
    def resumo(hoje: date = Depends(data_base), _: dict = Depends(usuario_atual)):
        return servico.calcular("resumo", hoje)

    @app.get("/api/painel")
    def painel(hoje: date = Depends(data_base), _: dict = Depends(usuario_atual)):
        resultado = servico.calcular("painel", hoje)
        return {**resultado, "linhas": [dataclasses.asdict(l) for l in resultado["linhas"]]}

    # ------------------------------------------------------------------ projeção
    @app.get("/api/projecao")
    def projecao(hoje: date = Depends(data_base), usuario: dict = Depends(usuario_atual)):
        return servico.grade_projecao(usuario, hoje)

    @app.put("/api/projecao")
    def salvar_projecao(itens: list[ItemProjecao], hoje: date = Depends(data_base),
                        usuario: dict = Depends(usuario_atual)):
        return {"salvos": servico.salvar_projecao([jsonable_encoder(i) for i in itens], usuario, hoje)}

    # ------------------------------------------------------------------ parâmetros
    @app.get("/api/parametros")
    def parametros(_: dict = Depends(usuario_atual)):
        return {"premissas": servico.premissas().como_dict(), "viabilidade": servico.viabilidade()}

    @app.put("/api/parametros/premissas")
    def salvar_premissas(dados: dict, usuario: dict = Depends(exigir("editar_premissas"))):
        return servico.salvar_premissas(dados, usuario).como_dict()

    @app.put("/api/parametros/viabilidade")
    def salvar_viabilidade(dados: dict[str, float], usuario: dict = Depends(exigir("editar_premissas"))):
        return servico.salvar_viabilidade(dados, usuario)

    # ------------------------------------------------------------------ fontes / APIs
    @app.get("/api/fontes")
    def fontes(_: dict = Depends(exigir("ver_apis"))):
        return servico.status_fontes()

    @app.post("/api/fontes/atualizar")
    def atualizar(pedido: PedidoAtualizacao, usuario: dict = Depends(exigir("atualizar_fontes"))):
        return servico.atualizar_fontes(pedido.origem, usuario, pedido.fontes)

    @app.get("/api/fontes/{codigo}/pendentes")
    def pendentes(codigo: str, _: dict = Depends(exigir("ver_apis"))):
        return servico.pendentes(codigo)

    @app.post("/api/fontes/{codigo}/classificar")
    def classificar(codigo: str, dados: Classificacao, usuario: dict = Depends(exigir("classificar"))):
        servico.classificar(codigo, dados.concat, dados.classificacao, usuario)
        return {"ok": True}

    # ------------------------------------------------------------------ saldos bancários
    @app.get("/api/saldos")
    def saldos(_: dict = Depends(exigir("ver_apis"))):
        return servico.listar_saldos()

    @app.post("/api/saldos")
    def salvar_saldo(dados: dict, usuario: dict = Depends(exigir("editar_saldos"))):
        servico.salvar_saldo(dados, usuario)
        return {"ok": True}

    @app.delete("/api/saldos/{saldo_id}")
    def excluir_saldo(saldo_id: int, usuario: dict = Depends(exigir("editar_saldos"))):
        servico.excluir_saldo(saldo_id, usuario)
        return {"ok": True}

    # ------------------------------------------------------------------ administração
    @app.get("/api/setores")
    def setores(_: dict = Depends(usuario_atual)):
        return servico.setores(incluir_inativos=True)

    @app.post("/api/setores")
    def salvar_setor(dados: dict, usuario: dict = Depends(exigir("administrar"))):
        return {"id": servico.salvar_setor(dados, usuario)}

    @app.post("/api/linhas")
    def salvar_linha(dados: dict, usuario: dict = Depends(exigir("administrar"))):
        return {"id": servico.salvar_linha(dados, usuario)}

    @app.get("/api/usuarios", dependencies=[Depends(exigir_login_ativo)])
    def usuarios(_: dict = Depends(exigir("administrar"))):
        return {"usuarios": servico.listar_usuarios(), "perfis": servico.perfis()}

    @app.post("/api/usuarios", dependencies=[Depends(exigir_login_ativo)])
    def criar_usuario(dados: NovoUsuario, usuario: dict = Depends(exigir("administrar"))):
        return {"id": servico.criar_usuario(dados.email, dados.nome, dados.perfil, dados.senha, usuario)}

    @app.patch("/api/usuarios/{usuario_id}", dependencies=[Depends(exigir_login_ativo)])
    def alterar_usuario(usuario_id: str, dados: AlteraUsuario, usuario: dict = Depends(exigir("administrar"))):
        servico.alterar_usuario(usuario_id, dados.model_dump(), usuario)
        return {"ok": True}

    @app.get("/api/historico")
    def historico(limite: int = 200, _: dict = Depends(exigir("ver_apis"))):
        return banco.todos("SELECT * FROM historico ORDER BY id DESC LIMIT ?", min(limite, 1000))

    # ------------------------------------------------------------------ interface (uso local)
    if config.PASTA_WEB.exists() and not os.environ.get("VERCEL"):
        app.mount("/", ArquivosEstaticos(directory=config.PASTA_WEB, html=True), name="web")

    return app

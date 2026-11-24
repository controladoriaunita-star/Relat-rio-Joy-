"""API REST do Relatório de Aporte Joy+ (várias obras: rotas de dados em /api/obras/{obra}/...).

Produção (Vercel): api/index.py expõe `app = criar_app()`; os arquivos de public/
são servidos pela CDN da Vercel e o banco é o Postgres do Supabase.
Local: python -m uvicorn backend.app.main:criar_app --factory --port 8060
"""
from __future__ import annotations

import dataclasses
import os
from datetime import date

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, config
from .catalogo import ABAS_EM_BREVE, PAPEL_ADMIN
from .db import Banco, ErroIntegridade, hoje
from .fontes.definicoes import FONTES
from .servicos import ErroConfirmacao, ErroNegocio, ObraNaoEncontrada, Servico, ServicoObra


class RubricaObra(BaseModel):
    nome: str
    grupo: str
    nome_anterior: str | None = None     # rubrica existente (renomeada ou não); vazio = nova


class RubricasObra(BaseModel):
    rubricas: list[RubricaObra]
    viabilidade: dict[str, float] | None = None
    forcar: bool = False


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


class Parcela(BaseModel):
    data: date
    percentual: float


class Cronograma(BaseModel):
    mes: date
    parcelas: list[Parcela] = []


class Concessao(BaseModel):
    papel: str
    permissao: str
    concedida: bool


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

    app = FastAPI(title="Relatório de Aporte · Joy+", docs_url="/api/docs",
                  openapi_url="/api/openapi.json", redoc_url=None)
    app.state.servico = servico

    @app.middleware("http")
    async def _sem_cache_na_api(request: Request, chamar):
        """Respostas da API nunca ficam em cache (navegador ou CDN): os dados mudam a cada carga."""
        resposta = await chamar(request)
        if request.url.path.startswith("/api/"):
            resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.exception_handler(ErroNegocio)
    async def _erro_negocio(_: Request, erro: ErroNegocio):
        return JSONResponse({"detail": str(erro)}, status_code=422)

    @app.exception_handler(ErroConfirmacao)
    async def _erro_confirmacao(_: Request, erro: ErroConfirmacao):
        return JSONResponse({"detail": str(erro), "confirmar": True}, status_code=409)

    @app.exception_handler(ObraNaoEncontrada)
    async def _obra_nao_encontrada(_: Request, erro: ObraNaoEncontrada):
        return JSONResponse({"detail": str(erro)}, status_code=404)

    @app.exception_handler(ErroIntegridade)
    async def _erro_integridade(_: Request, erro: ErroIntegridade):
        return JSONResponse({"detail": "Registro duplicado ou inválido."}, status_code=409)

    # ------------------------------------------------------------------ dependências
    def usuario_atual(request: Request) -> dict:
        if not login_ativo:                      # login inativo: acesso direto com perfil fixo
            return auth.usuario_sem_login(banco)
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
        return data or hoje()

    # ------------------------------------------------------------------ sessão
    @app.get("/api/config")
    def configuracao():
        """Dados públicos para o navegador iniciar o supabase-js (a anon key é pública)."""
        if not login_ativo:
            return {"modo": "sem_login"}
        if local:
            return {"modo": "local", "usuarios": [u for u in servico.listar_usuarios() if u["ativo"] and u["papeis"]]}
        return {"modo": "supabase", "supabase_url": config.SUPABASE_URL,
                "supabase_anon_key": config.SUPABASE_ANON_KEY}

    @app.get("/api/eu")
    def eu(usuario: dict = Depends(usuario_atual)):
        permissoes = {**auth.permissoes(usuario), "gerir_usuarios": login_ativo and auth.permissoes(usuario)["usuarios.gerenciar"]}
        em_breve = [] if PAPEL_ADMIN in usuario["papeis"] else ABAS_EM_BREVE
        return {**usuario, "permissoes": permissoes, "login_ativo": login_ativo, "em_breve": em_breve,
                "perfil_nome": servico.perfis().get(usuario["perfil"], usuario["perfil"])}

    # ------------------------------------------------------------------ obras (globais)
    @app.get("/api/obras")
    def listar_obras(usuario: dict = Depends(usuario_atual)):
        """Obras ativas para todos; quem gerencia obras vê também as inativas e a configuração."""
        gestor = auth.permissoes(usuario)["obras.gerenciar"]
        if not gestor:
            return [{"codigo": o.codigo, "nome": o.nome} for o in servico.obras()]
        return [{**o.como_dict(), "fontes": [{"codigo": f.codigo, "titulo": f.titulo, "aba_padrao": f.aba_graph,
                                               "aba": o.aba(f)} for f in FONTES]}
                for o in servico.obras(incluir_inativas=True)]

    @app.post("/api/obras")
    def salvar_obra(dados: dict, usuario: dict = Depends(exigir("obras.gerenciar"))):
        return servico.salvar_obra(dados, usuario).como_dict()

    @app.get("/api/inicio")
    def inicio(hoje: date = Depends(data_base), usuario: dict = Depends(usuario_atual)):
        """Cards da tela inicial: um por obra ativa. Todo usuário escolhe a obra aqui; os números
        financeiros só vão para quem pode ver o Resumo."""
        cards = servico.painel_inicio(hoje)
        if auth.permissoes(usuario)["resumo.ver"]:
            return cards
        publicos = ("codigo", "nome", "empresa_spe", "arquivo", "com_dados", "ultima_atualizacao", "erro")
        return [{k: c[k] for k in publicos if k in c} for c in cards]

    @app.get("/api/sharepoint/arquivos")
    def arquivos_sharepoint(_: dict = Depends(exigir("obras.gerenciar"))):
        """Planilhas da pasta de dados das obras, para escolher o arquivo no cadastro."""
        return servico.arquivos_sharepoint()

    # ------------------------------------------------------------------ dados de cada obra
    obra = APIRouter(prefix="/api/obras/{obra}")

    def servico_obra(obra: str) -> ServicoObra:
        return servico.obra(obra)

    @obra.get("/resumo")
    def resumo(hoje: date = Depends(data_base), so: ServicoObra = Depends(servico_obra),
               _: dict = Depends(exigir("resumo.ver"))):
        return so.calcular("resumo", hoje)

    @obra.get("/resumo/lancamentos")
    def lancamentos_resumo(rubrica: str, hoje: date = Depends(data_base), so: ServicoObra = Depends(servico_obra),
                           _: dict = Depends(exigir("resumo.ver"))):
        return so.lancamentos_da_rubrica(rubrica, hoje)

    @obra.get("/dashboards")
    def dashboards(hoje: date = Depends(data_base), so: ServicoObra = Depends(servico_obra),
                   _: dict = Depends(exigir("dashboards.ver"))):
        return so.dashboards(hoje)

    @obra.get("/aportes")
    def aportes(hoje: date = Depends(data_base), so: ServicoObra = Depends(servico_obra),
                _: dict = Depends(exigir("resumo.ver"))):
        return so.aportes(hoje)

    @obra.get("/painel")
    def painel(hoje: date = Depends(data_base), so: ServicoObra = Depends(servico_obra),
               _: dict = Depends(exigir("painel.ver"))):
        resultado = so.calcular("painel", hoje)
        return {**resultado, "linhas": [dataclasses.asdict(l) for l in resultado["linhas"]],
                "participacao": so.premissas().participacao()}

    @obra.get("/projecao")
    def projecao(hoje: date = Depends(data_base), so: ServicoObra = Depends(servico_obra),
                 usuario: dict = Depends(exigir("projecao.ver"))):
        return so.grade_projecao(usuario, hoje)

    @obra.get("/projecao/comparativo")
    def comparativo(mes: date | None = None, setor: str | None = None, hoje: date = Depends(data_base),
                    so: ServicoObra = Depends(servico_obra), _: dict = Depends(exigir("projecao.ver"))):
        return so.comparativo_projecao(mes or hoje, setor)

    @obra.put("/projecao")
    def salvar_projecao(itens: list[ItemProjecao], hoje: date = Depends(data_base),
                        so: ServicoObra = Depends(servico_obra), usuario: dict = Depends(exigir("projecao.ver"))):
        return {"salvos": so.salvar_projecao([jsonable_encoder(i) for i in itens], usuario, hoje)}

    @obra.get("/parametros")
    def parametros(so: ServicoObra = Depends(servico_obra), _: dict = Depends(exigir("resumo.ver"))):
        return {"premissas": so.premissas().como_dict(), "viabilidade": so.viabilidade(),
                "grupos": so.grupos_rubricas()}

    @obra.put("/parametros/premissas")
    def salvar_premissas(dados: dict, so: ServicoObra = Depends(servico_obra),
                         usuario: dict = Depends(exigir("premissas.editar"))):
        return so.salvar_premissas(dados, usuario).como_dict()

    @obra.put("/parametros/cronograma")
    def salvar_cronograma(dados: Cronograma, so: ServicoObra = Depends(servico_obra),
                          usuario: dict = Depends(exigir("premissas.editar"))):
        return so.salvar_cronograma(dados.mes, [p.model_dump() for p in dados.parcelas], usuario).como_dict()

    @obra.put("/parametros/viabilidade")
    def salvar_viabilidade(dados: dict[str, float], so: ServicoObra = Depends(servico_obra),
                           usuario: dict = Depends(exigir("premissas.editar"))):
        return so.salvar_viabilidade(dados, usuario)

    @obra.put("/parametros/rubricas")
    def salvar_rubricas(dados: RubricasObra, so: ServicoObra = Depends(servico_obra),
                        usuario: dict = Depends(exigir("premissas.editar"))):
        return so.salvar_rubricas([r.model_dump() for r in dados.rubricas], dados.viabilidade, usuario, dados.forcar)

    @obra.get("/fontes")
    def fontes(so: ServicoObra = Depends(servico_obra), _: dict = Depends(exigir("apis.ver"))):
        return so.status_fontes()

    @obra.post("/fontes/atualizar")
    def atualizar(pedido: PedidoAtualizacao, so: ServicoObra = Depends(servico_obra),
                  usuario: dict = Depends(exigir("fontes.atualizar"))):
        return so.atualizar_fontes(pedido.origem, usuario, pedido.fontes)

    @obra.get("/fontes/{codigo}/pendentes")
    def pendentes(codigo: str, so: ServicoObra = Depends(servico_obra), _: dict = Depends(exigir("apis.ver"))):
        return so.pendentes(codigo)

    @obra.post("/fontes/{codigo}/classificar")
    def classificar(codigo: str, dados: Classificacao, so: ServicoObra = Depends(servico_obra),
                    usuario: dict = Depends(exigir("fontes.classificar"))):
        so.classificar(codigo, dados.concat, dados.classificacao, usuario)
        return {"ok": True}

    @obra.get("/saldos")
    def saldos(so: ServicoObra = Depends(servico_obra), _: dict = Depends(exigir("apis.ver"))):
        return so.listar_saldos()

    @obra.get("/setores")
    def setores(so: ServicoObra = Depends(servico_obra), _: dict = Depends(usuario_atual)):
        return so.setores(incluir_inativos=True)

    @obra.post("/setores")
    def salvar_setor(dados: dict, so: ServicoObra = Depends(servico_obra),
                     usuario: dict = Depends(exigir("setores.gerenciar"))):
        return {"id": so.salvar_setor(dados, usuario)}

    @obra.post("/linhas")
    def salvar_linha(dados: dict, so: ServicoObra = Depends(servico_obra),
                     usuario: dict = Depends(exigir("setores.gerenciar"))):
        return {"id": so.salvar_linha(dados, usuario)}

    @obra.get("/historico")
    def historico(limite: int = 200, so: ServicoObra = Depends(servico_obra),
                  _: dict = Depends(exigir("apis.ver"))):
        return servico.historico(so.codigo, limite)

    app.include_router(obra)

    # ------------------------------------------------------------------ usuários e permissões (globais)
    @app.get("/api/usuarios", dependencies=[Depends(exigir_login_ativo)])
    def usuarios(_: dict = Depends(exigir("usuarios.gerenciar"))):
        return {"usuarios": servico.listar_usuarios(), "perfis": servico.perfis()}

    @app.post("/api/usuarios", dependencies=[Depends(exigir_login_ativo)])
    def criar_usuario(dados: NovoUsuario, usuario: dict = Depends(exigir("usuarios.gerenciar"))):
        return {"id": servico.criar_usuario(dados.email, dados.nome, dados.perfil, dados.senha, usuario)}

    @app.patch("/api/usuarios/{usuario_id}", dependencies=[Depends(exigir_login_ativo)])
    def alterar_usuario(usuario_id: str, dados: AlteraUsuario, usuario: dict = Depends(exigir("usuarios.gerenciar"))):
        servico.alterar_usuario(usuario_id, dados.model_dump(), usuario)
        return {"ok": True}

    @app.get("/api/permissoes")
    def permissoes(_: dict = Depends(exigir("usuarios.gerenciar"))):
        return servico.matriz_permissoes()

    @app.put("/api/permissoes")
    def alterar_permissao(dados: Concessao, usuario: dict = Depends(exigir("usuarios.gerenciar"))):
        servico.alterar_permissao(dados.papel, dados.permissao, dados.concedida, usuario)
        return {"ok": True}

    # ------------------------------------------------------------------ interface (uso local)
    if config.PASTA_WEB.exists() and not os.environ.get("VERCEL"):
        app.mount("/", ArquivosEstaticos(directory=config.PASTA_WEB, html=True), name="web")

    return app

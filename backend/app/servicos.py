"""Casos de uso do sistema: fontes, cálculo, projeção, cadastros e migração do Excel."""
from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from dataclasses import fields
from datetime import date

import requests

from . import auth
from .catalogo import (INICIO_LINHA_DO_TEMPO, MESES_LINHA_DO_TEMPO, PAPEIS_GERAIS, PAPEL_ADMIN, PERMISSOES,
                       PERMISSOES_PADRAO, PERMISSOES_SETOR, RUBRICAS, SETORES_PADRAO, VIABILIDADE_PADRAO,
                       Premissas)
from .config import ARQUIVO_EXCEL, EMPRESA_SPE
from .db import Banco, agora, para_json
from .excel_funcoes import chave_texto, como_data, eomonth, meses_entre, texto_igual
from .fontes.definicoes import FONTES, FONTES_POR_CODIGO
from .fontes.graph import ClienteGraph, ErroGraph
from .fontes.montagem import montar_base
from .fontes.normalizacao import montar_depara, normalizar, tabela_para_dicts
from .motor.base import Base, LinhaProjecao
from .motor import dashboards as painel_dashboards
from .motor.painel import calcular_painel
from .motor.resumo import calcular_resumo, saldo_fim_de_mes

TIPO_PROJETADO = "Projetado"
TIPO_PROJETADO_TOTAL = "Projetado Total"


class ErroNegocio(Exception):
    """Erro de validação com mensagem para o usuário."""


class Servico:
    def __init__(self, banco: Banco, graph: ClienteGraph | None = None,
                 admin: auth.AdminUsuarios | None = None):
        self.banco = banco
        self.graph = graph or ClienteGraph()
        self.admin = admin or (auth.AdminLocal() if auth.modo_local(banco) else auth.AdminSupabase())
        self._cache: dict[tuple, object] = {}

    # ================================================================ inicialização
    def inicializar(self) -> None:
        """Carga inicial idempotente: setores/linhas padrão, premissas e viabilidade."""
        with self.banco.transacao() as con:
            if not con.execute("SELECT 1 FROM setores LIMIT 1").fetchone():
                for ordem, setor in enumerate(SETORES_PADRAO):
                    sid = con.execute("INSERT INTO setores (codigo, nome, ordem) VALUES (?, ?, ?) "
                                      "RETURNING id", (setor["codigo"], setor["nome"], ordem)).fetchone()["id"]
                    for i, (nome, rubrica) in enumerate(setor["linhas"]):
                        con.execute("INSERT INTO linhas_projecao (setor_id, nome, rubrica, ordem) "
                                    "VALUES (?, ?, ?, ?)", (sid, nome, rubrica, i))
        self._semear_permissoes()
        if self.banco.parametro("premissas") is None:
            self.banco.salvar_parametro("premissas", Premissas().como_dict())
        if self.banco.parametro("viabilidade") is None:
            self.banco.salvar_parametro("viabilidade", VIABILIDADE_PADRAO)

    def _semear_permissoes(self) -> None:
        """Garante as permissões do catálogo e um papel para admin, diretor e cada setor.

        Papel novo recebe as permissões padrão; papel existente não é alterado (o que foi
        ajustado na tela de permissões fica). Toda permissão é concedida ao admin, como o
        gatilho permissions_grant_admin faz no Supabase.
        """
        with self.banco.transacao() as con:
            existentes = {l["key"] for l in con.execute("SELECT key FROM permissions").fetchall()}
            for chave, descricao in PERMISSOES.items():
                if chave in existentes:
                    continue
                con.execute("INSERT INTO permissions (id, key, description) VALUES (?, ?, ?)",
                            (str(uuid.uuid4()), chave, descricao))
                for papel, padrao in PERMISSOES_PADRAO.items():   # permissão nova: papéis que a têm no padrão
                    if chave in padrao:
                        con.execute("INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, p.id "
                                    "FROM roles r CROSS JOIN permissions p WHERE r.key = ? AND p.key = ? "
                                    "ON CONFLICT DO NOTHING", (papel, chave))
            papeis = {k: (nome, desc, PERMISSOES_PADRAO[k]) for k, (nome, desc) in PAPEIS_GERAIS.items()}
            for setor in con.execute("SELECT codigo, nome FROM setores").fetchall():
                papeis.setdefault(setor["codigo"], (setor["nome"], f"Setor {setor['nome']}", PERMISSOES_SETOR))
            for chave, (nome, descricao, padrao) in papeis.items():
                self._criar_papel(con, chave, nome, descricao, padrao)
            con.execute("INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, p.id "
                        "FROM roles r CROSS JOIN permissions p WHERE r.key = ? ON CONFLICT DO NOTHING",
                        (PAPEL_ADMIN,))

    @staticmethod
    def _criar_papel(con, chave: str, nome: str, descricao: str, permissoes: list[str]) -> None:
        if con.execute("SELECT 1 FROM roles WHERE key = ?", (chave,)).fetchone():
            return
        papel_id = str(uuid.uuid4())
        con.execute("INSERT INTO roles (id, key, name, description) VALUES (?, ?, ?, ?)",
                    (papel_id, chave, nome, descricao))
        for permissao in permissoes:
            con.execute("INSERT INTO role_permissions (role_id, permission_id) SELECT ?, id FROM permissions "
                        "WHERE key = ? ON CONFLICT DO NOTHING", (papel_id, permissao))

    # ================================================================ parâmetros
    def premissas(self) -> Premissas:
        dados = self.banco.parametro("premissas", {})
        validos = {f.name for f in fields(Premissas)}
        return Premissas(**{k: v for k, v in dados.items() if k in validos})

    def viabilidade(self) -> dict[str, float]:
        return {**VIABILIDADE_PADRAO, **self.banco.parametro("viabilidade", {})}

    def salvar_premissas(self, dados: dict, usuario: dict) -> Premissas:
        atual = self.premissas().como_dict()
        for chave, valor in dados.items():
            if chave not in atual:
                raise ErroNegocio(f"Premissa desconhecida: {chave}")
            if chave == "cronogramas_aporte":
                raise ErroNegocio("O cronograma do aporte é salvo em /api/parametros/cronograma.")
            if chave == "custo_projetado_proximo" and valor is None:
                pass                                    # volta ao cálculo automático
            else:
                valor = float(valor)
            atual[chave] = valor
        self.banco.salvar_parametro("premissas", atual)
        with self.banco.transacao() as con:
            self.banco.registrar(con, usuario["login"], "premissas.salvar", dados)
        return self.premissas()

    def salvar_cronograma(self, mes, parcelas: list[dict], usuario: dict) -> Premissas:
        """Cronograma do aporte de um mês: 1 a 12 parcelas com data no mês e percentuais que
        somam 100%. Sem parcelas, volta à parcela única no dia 1."""
        mes = como_data(mes)
        if not mes:
            raise ErroNegocio("Mês inválido.")
        mes = eomonth(mes)
        normalizadas = []
        for p in parcelas:
            data = como_data(p.get("data"))
            percentual = float(p.get("percentual") or 0)
            if not data or eomonth(data) != mes:
                raise ErroNegocio(f"Cada parcela precisa ter data dentro de {mes.strftime('%m/%Y')}.")
            if percentual <= 0:
                raise ErroNegocio("O percentual de cada parcela precisa ser maior que zero.")
            normalizadas.append({"data": data.isoformat(), "percentual": round(percentual, 6)})
        if len(normalizadas) > 12:
            raise ErroNegocio("No máximo 12 parcelas por mês.")
        if normalizadas and abs(sum(p["percentual"] for p in normalizadas) - 100) > 0.01:
            raise ErroNegocio("As parcelas precisam somar 100% do aporte do mês.")
        normalizadas.sort(key=lambda p: p["data"])
        atual = self.premissas().como_dict()
        cronogramas = dict(atual.get("cronogramas_aporte") or {})
        chave = mes.strftime("%Y-%m")
        if normalizadas:
            cronogramas[chave] = normalizadas
        else:
            cronogramas.pop(chave, None)
        atual["cronogramas_aporte"] = cronogramas
        self.banco.salvar_parametro("premissas", atual)
        with self.banco.transacao() as con:
            self.banco.registrar(con, usuario["login"], "cronograma.salvar", {"mes": chave, "parcelas": normalizadas})
        return self.premissas()

    def salvar_viabilidade(self, dados: dict[str, float], usuario: dict) -> dict:
        desconhecidas = set(dados) - set(RUBRICAS)
        if desconhecidas:
            raise ErroNegocio(f"Rubricas desconhecidas: {', '.join(sorted(desconhecidas))}")
        atual = {**self.viabilidade(), **{k: float(v) for k, v in dados.items()}}
        self.banco.salvar_parametro("viabilidade", atual)
        with self.banco.transacao() as con:
            self.banco.registrar(con, usuario["login"], "viabilidade.salvar", dados)
        return atual

    # ================================================================ base e cálculo
    def _ultima_carga_ok(self, fonte: str) -> dict | None:
        return self.banco.um("SELECT * FROM cargas WHERE fonte = ? AND status = 'ok' "
                             "ORDER BY id DESC LIMIT 1", fonte)

    def depara(self) -> dict[str, list[tuple]]:
        pares = defaultdict(list)
        for linha in self.banco.todos("SELECT fonte, concat, classificacao FROM depara"):
            pares[linha["fonte"]].append((linha["concat"], linha["classificacao"]))
        return pares

    def projecao_para_motor(self) -> list[LinhaProjecao]:
        """Gera a Projeção_2: uma linha por linha/mês e o total por rubrica/mês."""
        linhas, totais = [], defaultdict(float)
        for p in self.banco.todos(
                "SELECT l.nome, l.rubrica, p.mes, p.valor FROM projecoes p "
                "JOIN linhas_projecao l ON l.id = p.linha_id JOIN setores s ON s.id = l.setor_id "
                "WHERE p.valor <> 0 AND l.ativo = 1 AND s.ativo = 1"):
            mes = date.fromisoformat(p["mes"])
            linhas.append(LinhaProjecao(p["nome"], mes, TIPO_PROJETADO, p["valor"]))
            totais[(p["rubrica"], mes)] += p["valor"]
        linhas += [LinhaProjecao(r, m, TIPO_PROJETADO_TOTAL, v) for (r, m), v in totais.items()]
        return linhas

    def base(self) -> tuple[Base, dict]:
        chave = ("base", self.banco.versao)
        if chave not in self._cache:
            tabelas, ultima = {}, None
            for fonte in FONTES:
                carga = self._ultima_carga_ok(fonte.codigo)
                tabelas[fonte.codigo] = json.loads(carga["dados"]) if carga else []
                if carga and (ultima is None or carga["iniciado_em"] > ultima):
                    ultima = carga["iniciado_em"]
            self._cache = {chave: montar_base(tabelas, self.depara(), self.projecao_para_motor(), ultima)}
        return self._cache[chave]

    def calcular(self, aba: str, hoje: date) -> dict:
        chave = (aba, hoje, self.banco.versao)
        if chave not in self._cache:
            base, _ = self.base()
            funcao = calcular_resumo if aba == "resumo" else calcular_painel
            self._cache[chave] = funcao(base, hoje, self.viabilidade(), self.premissas())
        return self._cache[chave]

    # ================================================================ fontes (APIs)
    def atualizar_fontes(self, origem: str, usuario: dict | None, codigos=None,
                         tabelas_excel: dict | None = None) -> list[dict]:
        """Busca as fontes, valida e grava uma carga por fonte (a última 'ok' é a usada)."""
        if origem not in ("graph", "excel"):
            raise ErroNegocio("Origem inválida.")
        codigos = codigos or [f.codigo for f in FONTES]
        if origem == "excel" and tabelas_excel is None:
            if not ARQUIVO_EXCEL.exists():
                raise ErroNegocio("A planilha não está disponível neste servidor. Use o SharePoint.")
            from .fontes.excel import ler_planilha
            tabelas_excel = ler_planilha(ARQUIVO_EXCEL).tabelas
        depara = {k: montar_depara(v) for k, v in self.depara().items()}
        relatorio = []
        for codigo in codigos:
            fonte = FONTES_POR_CODIGO[codigo]
            inicio = time.perf_counter()
            status, mensagem, valores = "ok", None, []
            try:
                valores = (tabelas_excel[codigo] if origem == "excel"
                           else self.graph.ler_aba(fonte.aba_graph))
                avaliacao = normalizar(codigo, tabela_para_dicts(valores), depara.get(codigo, {}))
                if not valores:
                    status, mensagem = "erro", "A aba voltou vazia."
                elif avaliacao.colunas_ausentes:
                    status, mensagem = "erro", "Colunas ausentes: " + ", ".join(avaliacao.colunas_ausentes)
            except ErroGraph as erro:
                status, mensagem = "erro", str(erro)
            except requests.RequestException as erro:
                status, mensagem = "erro", f"Falha de comunicação: {erro}"
            duracao = round(time.perf_counter() - inicio, 2)
            with self.banco.transacao() as con:
                con.execute("INSERT INTO cargas (fonte, origem, iniciado_em, duracao_s, status, linhas, "
                            "mensagem, dados) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (codigo, origem, agora(), duracao, status, max(len(valores) - 1, 0),
                             mensagem, para_json(valores) if status == "ok" else None))
                con.execute("DELETE FROM cargas WHERE fonte = ? AND id NOT IN (SELECT id FROM cargas "
                            "WHERE fonte = ? ORDER BY id DESC LIMIT 30)", (codigo, codigo))
                self.banco.registrar(con, usuario and usuario["login"], "fonte.atualizar",
                                     {"fonte": codigo, "origem": origem, "status": status})
            relatorio.append({"fonte": codigo, "status": status, "mensagem": mensagem, "duracao_s": duracao})
        return relatorio

    def status_fontes(self) -> dict:
        _, resultados = self.base()
        fontes = []
        for fonte in FONTES:
            cargas = self.banco.todos("SELECT id, origem, iniciado_em, duracao_s, status, linhas, mensagem "
                                      "FROM cargas WHERE fonte = ? ORDER BY id DESC LIMIT 10", fonte.codigo)
            ok = [c for c in cargas if c["status"] == "ok"]
            resultado = resultados[fonte.codigo]
            fontes.append({
                "codigo": fonte.codigo, "titulo": fonte.titulo, "aba": fonte.aba_graph,
                "ultima": cargas[0] if cargas else None,
                "ultima_ok": ok[0] if ok else None,
                "variacao_linhas": (ok[0]["linhas"] - ok[1]["linhas"]) if len(ok) > 1 else None,
                "registros": len(resultado.registros),
                "valor_total": round(self._valor_da_carga(fonte.codigo, resultado.registros), 2),
                "pendentes": len(resultado.pendentes),
                "ignoradas": resultado.ignoradas,
                "classificavel": bool(fonte.chave),
                "historico": cargas,
            })
        return {"graph_configurado": ClienteGraph.configurado(), "fontes": fontes,
                "excel_disponivel": ARQUIVO_EXCEL.exists(),
                "rubricas": RUBRICAS + ["Rendimentos ", "Aporte", "Aporte Holding",
                                        "Retorno de Aporte", "Retorno de Aporte Holding"]}

    @staticmethod
    def _valor_da_carga(codigo: str, registros: list) -> float:
        """Conferência da carga: soma dos valores; para saldos, o saldo do último mês lançado
        (último saldo de cada conta naquele mês), que é o que o Resumo usa."""
        if codigo != "saldos":
            return sum(r.valor for r in registros)
        if not registros:
            return 0.0
        return saldo_fim_de_mes(Base(saldos=registros), max(eomonth(r.data) for r in registros))

    def pendentes(self, codigo: str) -> list[dict]:
        _, resultados = self.base()
        if codigo not in resultados:
            raise ErroNegocio("Fonte inválida.")
        return resultados[codigo].pendentes

    def classificar(self, codigo: str, concat: str, classificacao: str, usuario: dict) -> None:
        fonte = FONTES_POR_CODIGO.get(codigo)
        if not fonte or not fonte.chave:
            raise ErroNegocio("Fonte sem classificação.")
        if not classificacao.strip():
            raise ErroNegocio("Informe a classificação.")
        with self.banco.transacao() as con:
            con.execute("INSERT INTO depara (fonte, chave, concat, classificacao, atualizado_por, atualizado_em) "
                        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(fonte, chave) DO UPDATE SET "
                        "classificacao = excluded.classificacao, atualizado_por = excluded.atualizado_por, "
                        "atualizado_em = excluded.atualizado_em",
                        (codigo, concat.casefold(), concat, classificacao, usuario["login"], agora()))
            self.banco.registrar(con, usuario["login"], "depara.classificar",
                                 {"fonte": codigo, "concat": concat, "classificacao": classificacao})

    # ================================================================ saldos bancários
    def listar_saldos(self) -> list[dict]:
        """Saldos da aba Saldo do SharePoint. Marca o lançamento usado como saldo de fim de
        mês de cada conta (o último do mês, como Consulta2[Coluna1] = 1)."""
        _, resultados = self.base()
        saldos = resultados["saldos"].registros
        ultimo = {}
        for x in saldos:
            k = (x.empresa, (x.conta or "").casefold(), eomonth(x.data))
            if k not in ultimo or x.data > ultimo[k]:
                ultimo[k] = x.data
        return [{"empresa": x.empresa, "conta": x.conta, "data": x.data, "saldo": x.saldo,
                 "fim_de_mes": x.data == ultimo[(x.empresa, (x.conta or "").casefold(), eomonth(x.data))]}
                for x in sorted(saldos, key=lambda x: (x.data, x.conta or ""), reverse=True)]

    # ================================================================ setores e linhas
    def setores(self, incluir_inativos: bool = False) -> list[dict]:
        filtro = "" if incluir_inativos else "WHERE ativo = 1"
        setores = self.banco.todos(f"SELECT * FROM setores {filtro} ORDER BY ordem, nome")
        linhas = self.banco.todos(f"SELECT * FROM linhas_projecao {filtro} ORDER BY ordem, nome")
        por_setor = defaultdict(list)
        for linha in linhas:
            por_setor[linha["setor_id"]].append(linha)
        return [{**s, "linhas": por_setor[s["id"]]} for s in setores]

    def perfis(self) -> dict[str, str]:
        """Papéis disponíveis (chave → nome), na ordem: admin, diretor e setores."""
        ordem = {k: i for i, k in enumerate(PAPEIS_GERAIS)}
        papeis = self.banco.todos("SELECT key, name FROM roles")
        papeis.sort(key=lambda p: (ordem.get(p["key"], len(ordem)), p["name"]))
        return {p["key"]: p["name"] for p in papeis}

    # ================================================================ usuários
    def listar_usuarios(self) -> list[dict]:
        usuarios = self.banco.todos("SELECT CAST(id AS TEXT) AS usuario_id, email, full_name AS nome, "
                                    "active AS ativo, created_at AS criado_em FROM profiles ORDER BY full_name")
        papeis = defaultdict(list)
        for l in self.banco.todos("SELECT CAST(ur.user_id AS TEXT) AS usuario_id, r.key FROM user_roles ur "
                                  "JOIN roles r ON r.id = ur.role_id ORDER BY r.key"):
            papeis[l["usuario_id"]].append(l["key"])
        return [{**u, "ativo": bool(u["ativo"]), "criado_em": str(u["criado_em"]),
                 "papeis": papeis[u["usuario_id"]], "perfil": (papeis[u["usuario_id"]] or [None])[0]}
                for u in usuarios]

    def criar_usuario(self, email: str, nome: str, perfil: str, senha: str | None, autor: dict | None) -> str:
        """Cria o usuário no Supabase Auth (com senha ou convite por e-mail), o profile e o papel."""
        email = email.strip().lower()
        if "@" not in email or not nome.strip():
            raise ErroNegocio("Informe nome e e-mail válidos.")
        if perfil not in self.perfis():
            raise ErroNegocio("Perfil inválido.")
        if senha and len(senha) < 8:
            raise ErroNegocio("A senha precisa ter ao menos 8 caracteres.")
        try:
            usuario_id = self.admin.criar(email, nome, senha)
        except auth.ErroAutenticacao as erro:
            raise ErroNegocio(str(erro)) from erro
        auth.registrar_usuario(self.banco, usuario_id, email, nome, perfil, autor)
        return usuario_id

    def alterar_usuario(self, usuario_id: str, dados: dict, autor: dict) -> None:
        atual = self.banco.um("SELECT full_name, active FROM profiles WHERE id = ?", usuario_id)
        if not atual:
            raise ErroNegocio("Usuário não encontrado.")
        if dados.get("perfil") and dados["perfil"] not in self.perfis():
            raise ErroNegocio("Perfil inválido.")
        if dados.get("senha") and len(dados["senha"]) < 8:
            raise ErroNegocio("A senha precisa ter ao menos 8 caracteres.")
        ativo = bool(atual["active"]) if dados.get("ativo") is None else bool(dados["ativo"])
        try:
            self.admin.alterar(usuario_id, senha=dados.get("senha"),
                               bloqueado=None if dados.get("ativo") is None else not ativo)
        except auth.ErroAutenticacao as erro:
            raise ErroNegocio(str(erro)) from erro
        with self.banco.transacao() as con:
            con.execute("UPDATE profiles SET full_name = ?, active = ? WHERE id = ?",
                        (dados.get("nome") or atual["full_name"], ativo, usuario_id))
            if dados.get("perfil"):                    # a tela trabalha com um papel por usuário
                con.execute("DELETE FROM user_roles WHERE user_id = ?", (usuario_id,))
                con.execute("INSERT INTO user_roles (id, user_id, role_id, granted_by) "
                            "SELECT ?, ?, id, ? FROM roles WHERE key = ?",
                            (str(uuid.uuid4()), usuario_id, auth.uuid_ou_none(autor["id"]), dados["perfil"]))
            self.banco.registrar(con, autor["login"], "usuario.alterar",
                                 {"usuario_id": usuario_id, "perfil": dados.get("perfil"), "ativo": ativo,
                                  "senha_redefinida": bool(dados.get("senha"))})

    # ================================================================ papéis e permissões
    def matriz_permissoes(self) -> dict:
        concessoes = defaultdict(list)
        for l in self.banco.todos("SELECT r.key AS papel, p.key AS permissao FROM role_permissions rp "
                                  "JOIN roles r ON r.id = rp.role_id JOIN permissions p ON p.id = rp.permission_id"):
            concessoes[l["papel"]].append(l["permissao"])
        papeis = {p["key"]: p for p in self.banco.todos("SELECT key, name, description FROM roles")}
        ordem = list(PERMISSOES)
        permissoes = self.banco.todos("SELECT key, description FROM permissions")
        permissoes.sort(key=lambda p: ordem.index(p["key"]) if p["key"] in ordem else len(ordem))
        permissoes = [p for p in permissoes if p["key"] in PERMISSOES]   # só as que o app usa
        return {"permissoes": permissoes, "papel_admin": PAPEL_ADMIN,
                "papeis": [{**papeis[k], "permissoes": sorted(concessoes[k])} for k in self.perfis()]}

    def alterar_permissao(self, papel: str, permissao: str, concedida: bool, autor: dict) -> None:
        if papel == PAPEL_ADMIN:
            raise ErroNegocio("O papel admin tem sempre todas as permissões.")
        ids = self.banco.um("SELECT r.id AS papel_id, p.id AS permissao_id FROM roles r, permissions p "
                            "WHERE r.key = ? AND p.key = ?", papel, permissao)
        if not ids:
            raise ErroNegocio("Papel ou permissão inválidos.")
        with self.banco.transacao() as con:
            if concedida:
                con.execute("INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?) "
                            "ON CONFLICT DO NOTHING", (ids["papel_id"], ids["permissao_id"]))
            else:
                con.execute("DELETE FROM role_permissions WHERE role_id = ? AND permission_id = ?",
                            (ids["papel_id"], ids["permissao_id"]))
            self.banco.registrar(con, autor["login"], "permissao.alterar",
                                 {"papel": papel, "permissao": permissao, "concedida": concedida})

    def salvar_setor(self, dados: dict, usuario: dict) -> int:
        codigo = str(dados.get("codigo", "")).strip().lower()
        nome = str(dados.get("nome", "")).strip()
        if not codigo.isalnum() or not nome:
            raise ErroNegocio("Código (letras/números) e nome são obrigatórios.")
        if codigo in auth.PAPEIS_RESERVADOS:
            raise ErroNegocio("Código reservado.")
        with self.banco.transacao() as con:
            if dados.get("id"):
                anterior = con.execute("SELECT codigo FROM setores WHERE id = ?", (dados["id"],)).fetchone()
                con.execute("UPDATE setores SET codigo = ?, nome = ?, ativo = ?, ordem = ? WHERE id = ?",
                            (codigo, nome, int(dados.get("ativo", 1)), int(dados.get("ordem", 0)), dados["id"]))
                if anterior:                           # o papel do setor acompanha código e nome
                    con.execute("UPDATE roles SET key = ?, name = ? WHERE key = ?", (codigo, nome, anterior["codigo"]))
                setor_id = dados["id"]
            else:
                setor_id = con.execute("INSERT INTO setores (codigo, nome, ordem) VALUES (?, ?, ?) RETURNING id",
                                       (codigo, nome, int(dados.get("ordem", 99)))).fetchone()["id"]
            self._criar_papel(con, codigo, nome, f"Setor {nome}", PERMISSOES_SETOR)
            self.banco.registrar(con, usuario["login"], "setor.salvar", dados)
        return setor_id

    def salvar_linha(self, dados: dict, usuario: dict) -> int:
        nome = str(dados.get("nome", "")).strip()
        rubrica = dados.get("rubrica")
        if not nome or rubrica not in RUBRICAS:
            raise ErroNegocio("Nome e rubrica válida são obrigatórios.")
        if not self.banco.um("SELECT 1 FROM setores WHERE id = ?", dados.get("setor_id")):
            raise ErroNegocio("Setor inválido.")
        with self.banco.transacao() as con:
            if dados.get("id"):
                con.execute("UPDATE linhas_projecao SET setor_id = ?, nome = ?, rubrica = ?, ordem = ?, "
                            "ativo = ? WHERE id = ?", (dados["setor_id"], nome, rubrica,
                                                       int(dados.get("ordem", 0)),
                                                       int(dados.get("ativo", 1)), dados["id"]))
                linha_id = dados["id"]
            else:
                linha_id = con.execute("INSERT INTO linhas_projecao (setor_id, nome, rubrica, ordem) "
                                       "VALUES (?, ?, ?, ?) RETURNING id",
                                       (dados["setor_id"], nome, rubrica,
                                        int(dados.get("ordem", 99)))).fetchone()["id"]
            self.banco.registrar(con, usuario["login"], "linha.salvar", dados)
        return linha_id

    # ================================================================ projeção
    def grade_projecao(self, usuario: dict, hoje: date) -> dict:
        mes_atual = eomonth(hoje)
        meses = meses_entre(INICIO_LINHA_DO_TEMPO, MESES_LINHA_DO_TEMPO)
        valores = defaultdict(dict)
        for p in self.banco.todos("SELECT linha_id, mes, valor, atualizado_por, atualizado_em FROM projecoes"):
            valores[p["linha_id"]][p["mes"]] = p["valor"]
        setores = []
        for setor in self.setores():
            editavel = auth.pode_editar_setor(usuario, setor["codigo"])
            setores.append({**setor, "editavel": editavel, "linhas": [
                {**l, "valores": valores[l["id"]], "total": sum(valores[l["id"]].values())}
                for l in setor["linhas"]]})

        resumo = self.calcular("resumo", hoje)
        projetado_rubrica = defaultdict(float)
        for setor in setores:
            for linha in setor["linhas"]:
                projetado_rubrica[linha["rubrica"]] += linha["total"]
        rubricas = []
        for linha in resumo["linhas"]:
            if linha["grupo"] not in ("despesa", "custo"):
                continue
            realizado = (linha.get("pago_ate") or 0) + (linha.get("pago_mes") or 0)
            projetado = projetado_rubrica[linha["rubrica"]]
            rubricas.append({"rubrica": linha["rubrica"], "viabilidade": linha["viabilidade"],
                             "realizado": realizado, "a_pagar": linha["a_pagar"], "projetado": projetado,
                             "saldo": linha["viabilidade"] - realizado - linha["a_pagar"] - projetado})
        return {"meses": meses, "mes_atual": mes_atual,
                "pode_editar_passado": auth.permissoes(usuario)["projecao.editar_meses_passados"],
                "setores": setores, "rubricas": rubricas}

    def comparativo_projecao(self, mes: date, codigo_setor: str | None) -> dict:
        """Projetado por linha × lançamentos da base de custos (Custos SPE e NN's) no mês,
        nas rubricas das linhas do setor (ou de todos os setores, sem código)."""
        mes = eomonth(mes)
        setores = [s for s in self.setores() if not codigo_setor or s["codigo"] == codigo_setor]
        if codigo_setor and not setores:
            raise ErroNegocio("Setor inválido.")
        valores = {p["linha_id"]: p["valor"] for p in self.banco.todos(
            "SELECT linha_id, valor FROM projecoes WHERE mes = ?", mes.isoformat())}
        projetado = [{"setor": s["nome"], "linha": l["nome"], "rubrica": l["rubrica"],
                      "valor": valores.get(l["id"], 0)} for s in setores for l in s["linhas"]]
        rubricas = {chave_texto(p["rubrica"]): p["rubrica"] for p in projetado}

        base, _ = self.base()
        incorrido = []
        for fonte in ("custos_spe", "custos_nn"):
            for d in getattr(base, fonte):
                rubrica = rubricas.get(chave_texto(d.classificacao))
                if d.fim_mes == mes and rubrica:
                    incorrido.append({"fonte": FONTES_POR_CODIGO[fonte].titulo, "rubrica": rubrica,
                                      "fornecedor": d.fornecedor, "insumo": d.insumo, "processo": d.processo,
                                      "data": d.data_pagamento, "status": d.status, "valor": d.valor})
        incorrido.sort(key=lambda i: (i["rubrica"], i["data"] or mes, i["fornecedor"] or ""))
        pago = sum(i["valor"] for i in incorrido if texto_igual(i["status"], "Pago"))
        total_incorrido = sum(i["valor"] for i in incorrido)
        return {"mes": mes, "setor": codigo_setor or None, "projetado": projetado, "incorrido": incorrido,
                "totais": {"projetado": sum(p["valor"] for p in projetado), "incorrido": total_incorrido,
                           "pago": pago, "a_pagar": total_incorrido - pago}}

    def dashboards(self, hoje: date) -> dict:
        """Séries da aba Dashboards (ver motor/dashboards.py)."""
        painel, resumo = self.calcular("painel", hoje), self.calcular("resumo", hoje)
        base, _ = self.base()
        projecoes = self.banco.todos("SELECT p.linha_id, p.mes, p.valor FROM projecoes p "
                                     "JOIN linhas_projecao l ON l.id = p.linha_id WHERE l.ativo = 1")
        return {"datas": {**resumo["datas"], "corte": painel["datas"]["corte"]},
                "exposicao": painel_dashboards.exposicao_de_caixa(painel),
                "recebimentos": painel_dashboards.recebimentos(base, resumo["datas"]["mes_atual"]),
                "setores": painel_dashboards.gasto_por_setor(base, self.setores(), projecoes),
                "custos": painel_dashboards.custos_por_rubrica(resumo),
                "ultima_atualizacao": resumo["ultima_atualizacao"]}

    def salvar_projecao(self, itens: list[dict], usuario: dict, hoje: date) -> int:
        mes_atual = eomonth(hoje)
        linhas = {l["id"]: l for l in self.banco.todos(
            "SELECT l.id, l.nome, s.codigo FROM linhas_projecao l JOIN setores s ON s.id = l.setor_id "
            "WHERE l.ativo = 1 AND s.ativo = 1")}
        pode_passado = auth.permissoes(usuario)["projecao.editar_meses_passados"]
        normalizados = []
        for item in itens:
            linha = linhas.get(item.get("linha_id"))
            if not linha:
                raise ErroNegocio("Linha de projeção inválida.")
            if not auth.pode_editar_setor(usuario, linha["codigo"]):
                raise ErroNegocio(f"Sem permissão para editar '{linha['nome']}'.")
            mes = como_data(item.get("mes"))
            if not mes or mes != eomonth(mes):
                raise ErroNegocio("Mês inválido.")
            if mes < mes_atual and not pode_passado:
                raise ErroNegocio("Meses anteriores ao atual não podem ser alterados.")
            normalizados.append((linha["id"], mes.isoformat(), float(item.get("valor") or 0)))
        with self.banco.transacao() as con:
            for linha_id, mes, valor in normalizados:
                if valor == 0:
                    con.execute("DELETE FROM projecoes WHERE linha_id = ? AND mes = ?", (linha_id, mes))
                else:
                    con.execute("INSERT INTO projecoes (linha_id, mes, valor, atualizado_por, atualizado_em) "
                                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(linha_id, mes) DO UPDATE SET "
                                "valor = excluded.valor, atualizado_por = excluded.atualizado_por, "
                                "atualizado_em = excluded.atualizado_em",
                                (linha_id, mes, valor, usuario["login"], agora()))
            self.banco.registrar(con, usuario["login"], "projecao.salvar",
                                 [{"linha_id": l, "mes": m, "valor": v} for l, m, v in normalizados])
        return len(normalizados)

    # ================================================================ migração do Excel
    def migrar_do_excel(self, caminho=ARQUIVO_EXCEL, importar_projecao: bool = True) -> dict:
        """Carga inicial a partir da planilha: DePara, fontes (inclusive saldos) e projeção (sem duplicidades)."""
        from .fontes.excel import ler_planilha
        planilha = ler_planilha(caminho)
        with self.banco.transacao() as con:
            for codigo, pares in planilha.depara.items():
                for concat, classificacao in pares:
                    if concat and classificacao:
                        con.execute("INSERT INTO depara (fonte, chave, concat, classificacao, "
                                    "atualizado_por, atualizado_em) VALUES (?, ?, ?, ?, 'migracao', ?) "
                                    "ON CONFLICT (fonte, chave) DO NOTHING",
                                    (codigo, str(concat).casefold(), str(concat), classificacao, agora()))
        self.atualizar_fontes("excel", None, tabelas_excel=planilha.tabelas)
        relatorio = {"depara": sum(len(v) for v in planilha.depara.values())}
        if importar_projecao:
            relatorio["projecao"] = self._importar_projecao(planilha.projecao)
        return relatorio

    def _importar_projecao(self, projecao: list[LinhaProjecao]) -> dict:
        """Importa as linhas "Projetado" da Projeção_2 para as linhas cadastradas.

        A Projeção_2 tem blocos repetidos; para cada linha/mês vale a última ocorrência.
        Linhas sem correspondência e meses com valores conflitantes vão no relatório.
        """
        linhas = {l["nome"].casefold(): l for l in self.banco.todos("SELECT * FROM linhas_projecao")}
        escolhidos, conflitos, sem_linha = {}, [], defaultdict(float)
        for p in projecao:
            if p.tipo != TIPO_PROJETADO or not p.valor or not p.descricao:
                continue
            linha = linhas.get(p.descricao.casefold())
            if not linha:
                sem_linha[p.descricao] += p.valor
                continue
            chave = (linha["id"], p.data.isoformat())
            if chave in escolhidos and escolhidos[chave] != p.valor:
                conflitos.append({"linha": linha["nome"], "mes": p.data.isoformat(),
                                  "anterior": escolhidos[chave], "importado": p.valor})
            escolhidos[chave] = p.valor
        with self.banco.transacao() as con:
            for (linha_id, mes), valor in escolhidos.items():
                con.execute("INSERT INTO projecoes (linha_id, mes, valor, atualizado_por, atualizado_em) "
                            "VALUES (?, ?, ?, 'migracao', ?) ON CONFLICT (linha_id, mes) DO UPDATE SET "
                            "valor = excluded.valor, atualizado_por = excluded.atualizado_por, "
                            "atualizado_em = excluded.atualizado_em", (linha_id, mes, valor, agora()))
        return {"importados": len(escolhidos), "conflitos": conflitos,
                "sem_linha_cadastrada": dict(sem_linha)}

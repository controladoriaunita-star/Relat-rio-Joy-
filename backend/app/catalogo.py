"""Estrutura fixa do relatório, transcrita das abas Resumo e Painel da planilha.

Cada linha guarda o número da linha no Excel (`linha_excel`) para rastreabilidade
e para o teste de regressão. Valores de viabilidade e premissas são os padrões
iniciais; em operação eles ficam no banco e podem ser editados pela Diretoria.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# --- Rubricas de custo e despesa -------------------------------------------------
# (rubrica, linha no Resumo, linha no Painel, valor de viabilidade/EVE)
DESPESAS = [
    ("Despesas de Incorporação", 7, 61, 639535.0129999997),
    ("Marketing e Publicidade", 8, 62, 1729744.8236691577),
    ("Comissão de Vendas", 9, 63, 3805438.612072141),
    ("Stand de Vendas", 10, 64, 1100000),
    ("Outras Despesas Comerciais", 11, 65, 152200.00000000003),
    ("Despesas Adm. da SPE", 12, 66, 27200),
    ("G&A de Terceiros (Taxa Incorporação)", 13, 67, 0),
    ("G&A Holding (Taxa Incorporação)", 14, 68, 1383795.8589353263),
    ("Agente Financeiro", 15, 69, 55680),
    ("Reciprocidade", 16, 70, 107999.99999999999),
    ("Mobiliário e Decoração", 17, 71, 438698.6116845723),
    ("Manutenção Pós Obra", 18, 72, 660610.3140052612),
    ("ITBI e Registros UH's", 19, 73, 1432640.0000000002),
    ("Outras Despesas", 20, 74, 0),
    ("Despesas Não Previstas", 21, 75, 0),
    ("Outras Receitas e Despesas / Reembolsos", 22, 76, 0),
]
CUSTOS = [
    ("Terreno", 26, 43, 3072000),
    ("Custo da Construção", 27, 44, 40411745.4433408),
    ("Taxa de Obra - Holding", 28, 45, 2234340.88311816),
    ("Taxa de Obra - Terceiros", 29, 46, 0),
    ("Outros Custos de Construção", 30, 47, 0),
    ("Outros Custos do Terreno", 31, 48, 780110),
    ("Projetos", 32, 49, 689330.0000000001),
    ("Seguros", 33, 50, 115500),
    ("Outorga", 34, 51, 0),
    ("Infra Externa e Contrapartidas", 35, 52, 186462.18403510272),
    ("Comissão do Terreno", 36, 53, 297100),
    ("Outros Custos", 37, 54, 0),
    ("Custos Não Previstos", 38, 55, 0),
    ("Juros do Financiamento", 39, 56, 352227.2237086735),
]
VIABILIDADE_PADRAO = {nome: valor for nome, _, _, valor in DESPESAS + CUSTOS}
RUBRICAS = [nome for nome, *_ in DESPESAS + CUSTOS]
GRUPOS_RUBRICA = ("despesa", "custo")


@dataclass(frozen=True)
class Rubrica:
    """Rubrica de custo/despesa de uma obra. `linha_resumo`/`linha_painel` posicionam a rubrica
    no relatório: as do catálogo mantêm a linha da planilha; as criadas na obra entram no fim do
    grupo com linha fracionária (22.01, 22.02… no Resumo), sem deslocar as linhas fixas."""
    nome: str
    grupo: str                       # "despesa" | "custo"
    linha_resumo: float
    linha_painel: float
    padrao: str | None = None        # nome da rubrica do catálogo de origem (None = criada na obra)


RUBRICAS_PADRAO = ([Rubrica(n, "despesa", r, p, n) for n, r, p, _ in DESPESAS]
                   + [Rubrica(n, "custo", r, p, n) for n, r, p, _ in CUSTOS])
# Última linha de cada grupo na planilha: as rubricas criadas na obra vêm logo depois.
_FIM_GRUPO = {"despesa": (22, 76), "custo": (39, 56)}
MAX_RUBRICAS_NOVAS = 99


def config_rubricas_padrao() -> list[dict]:
    return [{"nome": r.nome, "grupo": r.grupo, "padrao": r.padrao} for r in RUBRICAS_PADRAO]


def montar_rubricas(config: list[dict] | None) -> list[Rubrica]:
    """Rubricas da obra a partir da configuração salva ([{nome, grupo, padrao}], na ordem)."""
    if not config:
        return list(RUBRICAS_PADRAO)
    do_catalogo = {r.padrao: r for r in RUBRICAS_PADRAO}
    novas = {g: 0 for g in GRUPOS_RUBRICA}
    saida = []
    for item in config:
        grupo, origem = item["grupo"], do_catalogo.get(item.get("padrao"))
        if origem and origem.grupo == grupo:
            saida.append(Rubrica(item["nome"], grupo, origem.linha_resumo, origem.linha_painel, origem.padrao))
        else:
            novas[grupo] += 1
            resumo, painel = _FIM_GRUPO[grupo]
            frac = novas[grupo] / 100
            saida.append(Rubrica(item["nome"], grupo, round(resumo + frac, 2), round(painel + frac, 2)))
    return sorted(saida, key=lambda r: r.linha_resumo)


# --- Resumo ---------------------------------------------------------------------
@dataclass(frozen=True)
class LinhaResumo:
    linha_excel: float             # inteira nas linhas da planilha; fracionária nas rubricas novas
    rotulo: str                    # coluna B
    grupo: str                     # "despesa" | "custo" | "aporte" | "vazia" | "subtotal"
    rotulo_pago_ate: str | None = None   # Resumo H40 usa a coluna A em vez da B
    tem_pago: bool = True          # colunas H e J existem
    viabilidade: bool = True       # coluna D/F existe


def linhas_resumo(rubricas: list[Rubrica] | None = None) -> list[LinhaResumo]:
    """Linhas do Resumo para as rubricas da obra (sem rubricas = catálogo da planilha)."""
    rubricas = RUBRICAS_PADRAO if rubricas is None else rubricas
    linhas = [LinhaResumo(r.linha_resumo, r.nome, "despesa") for r in rubricas if r.grupo == "despesa"]
    linhas += [LinhaResumo(23, "", "vazia", tem_pago=False, viabilidade=False),
               LinhaResumo(24, "Total de Despesas ", "subtotal", tem_pago=False),
               LinhaResumo(25, "", "vazia", tem_pago=False, viabilidade=False)]
    linhas += [LinhaResumo(r.linha_resumo, r.nome, "custo") for r in rubricas if r.grupo == "custo"]
    linhas += [LinhaResumo(40, "Retorno de Aporte Investidor", "aporte",
                           rotulo_pago_ate="Retorno de Aporte", viabilidade=False),
               LinhaResumo(41, "Retorno de Aporte Holding", "aporte", viabilidade=False),
               LinhaResumo(42, "", "vazia", tem_pago=False, viabilidade=False),
               LinhaResumo(43, "Total de Custos", "subtotal", tem_pago=False)]
    return linhas


LINHAS_RESUMO = linhas_resumo()


# --- Premissas manuais (células digitadas na planilha) ----------------------------
@dataclass
class Premissas:
    caixa_minimo: float = 100000            # Resumo Z8
    receita_projetada_proximo: float = 0    # Resumo Z21
    # Resumo Z22. Na planilha é digitado; no sistema, None = automático
    # (projetado + contas a pagar do próximo mês, coluna S do Resumo).
    custo_projetado_proximo: float | None = None
    caixa_minimo_proximo: float = 100000    # Resumo Z23
    participacao_investidor: float = 0.85   # Resumo Z10/Z25 e Y34/Y38
    participacao_joy: float = 0.15          # Resumo Z11/Z26 e Y35/Y39
    ajuste_saldo_banco: float = 372288.53   # Painel H119: saldo inicial + o que as fontes não trazem
    # Cronograma do aporte do mês (Resumo Y32:Y43): "AAAA-MM" → parcelas [{"data", "percentual"}].
    # O percentual é do aporte necessário do mês, então as parcelas sempre somam o aporte.
    # Mês sem cronograma: parcela única no dia 1.
    cronogramas_aporte: dict[str, list[dict]] = field(default_factory=dict)

    def como_dict(self) -> dict:
        return dict(self.__dict__)

    @property
    def com_investidor(self) -> bool:
        return self.participacao_investidor > 0

    def participacao(self) -> dict:
        """Divisão do aporte da obra: obra sem investidor = 100% Joy+."""
        return {"investidor": self.participacao_investidor, "joy": self.participacao_joy,
                "com_investidor": self.com_investidor}


# --- Painel -----------------------------------------------------------------------
INICIO_LINHA_DO_TEMPO = date(2024, 1, 31)   # Painel CE23
MESES_LINHA_DO_TEMPO = 84                   # CE..FJ = jan/2024 a dez/2030

# Receitas: valor previsto no EVE (coluna X) por linha do Painel.
RECEITAS_EVE = {
    25: ("Clientes - Direto com SPE", 13837958.589353263),
    26: ("CAIXA - Fração do Terreno", 9300011.940727768),
    27: ("CAIXA - Medições de Obra", 46051822.416685276),
    28: ("INCC+Juros s/ Carteira (pós-entrega)", 1055521.6544027221),
    29: ("Comissão de Vendas Direta", None),
    30: ("Perda / Inadimplência", -297869.60487511975),
    31: ("", None),
    32: ("Rendimentos ", None),
    33: ("", None),
    34: ("", None),
    35: ("Receita de Permuta Física", None),
}
IMPOSTO_RECEITA_EVE = -2797897.7998517565   # Painel X38
IMPOSTO_RECEITA_ALIQUOTA = 0.04             # Painel AR38
TIR_EVE = {97: 0.043432518687977595, 99: 0.003463053912590386}   # Painel X97 / X99

# Premissas de desembolso (Painel AR..AX), apenas exibidas.
PREMISSAS_DESEMBOLSO = {
    43: {"valor_mes": 1440, "valor_total": None, "primeiro_mes": date(2024, 1, 1), "parcelas": 24},
    45: {"valor_mes": None, "valor_total": 14952244.656201007, "primeiro_mes": None, "parcelas": None},
}


# --- Setores e linhas de projeção (carga inicial; editável pelo admin) -------------
SETORES_PADRAO = [
    {"codigo": "mkt", "nome": "Marketing", "linhas": [("Marketing", "Marketing e Publicidade")]},
    {"codigo": "proj", "nome": "Projetos", "linhas": [(nome, "Projetos") for nome in [
        "ARQUITETURA | RSA", "ESTRUTURA | MB ENGENHARIA", "FUNDAÇÃO | SOLODACTHA",
        "INSTALAÇÕES | FORMATO", "INCÊNDIO | FEUERTEC", "COMPATIBILIZAÇÃO | ARQTECHNE",
        "DECORAÇÃO | BY ARQ", "CLIMATIZAÇÃO | ÉOLO", "PAISAGISMO | PAOLA SILVA",
        "ACESSIBILIDADE | C23", "ATP ESTRUTURA | ALEXANDRE SOUZA", "ELEVADOR | TECNITRI",
        "IMPERMEABILIZAÇÃO | SONCINI", "LAUDOS | C23", "TERRAPLANAGEM | RAMBLA",
        "PLANIALTIMÉTRICO | HS PROJETOS"]]},
    {"codigo": "inc", "nome": "Incorporação", "linhas": [
        ("Stand de Vendas", "Stand de Vendas"),
        ("Manutenção do Stand", "Stand de Vendas"),
        ("Seguro Stand", "Stand de Vendas"),
        ("Comissão do Terreno", "Comissão do Terreno"),
        ("Demolição", "Outros Custos do Terreno"),
        ("Ambiental", "Outros Custos do Terreno"),
        ("ITBI de terreno", "Outros Custos do Terreno"),
        ("Escritura de terreno", "Outros Custos do Terreno"),
        ("Registro de escritura de terreno", "Outros Custos do Terreno"),
        ("IPTU de terreno", "Outros Custos do Terreno"),
        ("Despesas de Incorporação", "Despesas de Incorporação"),
        ("Due Dilligence (Jurídico)", "Despesas de Incorporação"),
        ("Registro do Contrato PJ da CEF no Cartório", "Despesas de Incorporação"),
        ("Prestação de Serviços Jurídicos", "Despesas de Incorporação"),
        ("Prestação de Serviços Contábeis", "Despesas de Incorporação"),
        ("Instituição/Averbação de Condomínio", "Despesas de Incorporação"),
    ]},
]
# --------------------------------------------------------------------- papéis e permissões
# Padrão de permissões Unità: papéis (roles), permissões e concessões por usuário (user_roles).
# Cada setor é um papel com a mesma chave do código do setor (mkt, proj, inc...).
PAPEL_ADMIN = "admin"
PAPEIS_GERAIS = {
    PAPEL_ADMIN: ("Administrador", "Desenvolvedores: acesso total ao app"),
    "diretor": ("Diretoria", "Vê todas as abas e edita todos os setores e meses"),
}
PERMISSOES = {
    "resumo.ver": "Ver a aba Resumo",
    "resumo.enviar": "Enviar o Resumo em PDF por e-mail (sai da conta Microsoft de quem envia)",
    "dashboards.ver": "Ver a aba Dashboards",
    "painel.ver": "Ver a aba Painel",
    "projecao.ver": "Ver a aba Projeção e editar as linhas do próprio setor",
    "projecao.editar_todos_setores": "Editar a projeção de qualquer setor",
    "projecao.editar_meses_passados": "Editar meses anteriores ao corrente",
    "apis.ver": "Ver a aba API's (fontes, pendências, saldos, viabilidade e histórico)",
    "fontes.atualizar": "Atualizar as fontes (SharePoint ou Excel)",
    "fontes.classificar": "Classificar lançamentos pendentes (DePara)",
    "premissas.editar": "Editar premissas do aporte e viabilidade",
    "setores.gerenciar": "Criar e alterar setores e linhas de projeção",
    "usuarios.gerenciar": "Gerenciar usuários, papéis e permissões dentro do app",
    "obras.gerenciar": "Cadastrar obras e alterar a configuração de cada uma",
}
PERMISSOES_PADRAO = {                       # concedidas quando o papel é criado
    PAPEL_ADMIN: list(PERMISSOES),
    "diretor": [p for p in PERMISSOES if p not in ("setores.gerenciar", "usuarios.gerenciar", "obras.gerenciar")],
}
PERMISSOES_SETOR = ["projecao.ver"]         # papel de setor novo
# Abas ainda em construção: aparecem como "Em breve" para todos, menos para o papel admin.
ABAS_EM_BREVE = ["dashboards", "painel"]

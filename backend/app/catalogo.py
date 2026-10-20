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


# --- Resumo ---------------------------------------------------------------------
@dataclass(frozen=True)
class LinhaResumo:
    linha_excel: int
    rotulo: str                    # coluna B
    grupo: str                     # "despesa" | "custo" | "aporte" | "vazia" | "subtotal"
    rotulo_pago_ate: str | None = None   # Resumo H40 usa a coluna A em vez da B
    tem_pago: bool = True          # colunas H e J existem
    viabilidade: bool = True       # coluna D/F existe


def _linhas_resumo() -> list[LinhaResumo]:
    linhas = [LinhaResumo(r, nome, "despesa") for nome, r, _, _ in DESPESAS]
    linhas += [LinhaResumo(23, "", "vazia", tem_pago=False, viabilidade=False),
               LinhaResumo(24, "Total de Despesas ", "subtotal", tem_pago=False),
               LinhaResumo(25, "", "vazia", tem_pago=False, viabilidade=False)]
    linhas += [LinhaResumo(r, nome, "custo") for nome, r, _, _ in CUSTOS]
    linhas += [LinhaResumo(40, "Retorno de Aporte Investidor", "aporte",
                           rotulo_pago_ate="Retorno de Aporte", viabilidade=False),
               LinhaResumo(41, "Retorno de Aporte Holding", "aporte", viabilidade=False),
               LinhaResumo(42, "", "vazia", tem_pago=False, viabilidade=False),
               LinhaResumo(43, "Total de Custos", "subtotal", tem_pago=False)]
    return linhas


LINHAS_RESUMO = _linhas_resumo()


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
    ajuste_saldo_banco: float = 372288.53   # Painel H119 (constante somada ao saldo)
    # Cronograma do aporte do mês (Resumo Y32:Y43): "AAAA-MM" → parcelas [{"data", "percentual"}].
    # O percentual é do aporte necessário do mês, então as parcelas sempre somam o aporte.
    # Mês sem cronograma: parcela única no dia 1.
    cronogramas_aporte: dict[str, list[dict]] = field(default_factory=dict)

    def como_dict(self) -> dict:
        return dict(self.__dict__)


# --- Painel -----------------------------------------------------------------------
INICIO_LINHA_DO_TEMPO = date(2024, 1, 31)   # Painel CE23
MESES_LINHA_DO_TEMPO = 84                   # CE..FJ = jan/2024 a dez/2030
MESES_SEM_INVERSAO_SINAL = 12               # CE..CP (2024) não multiplicam por -1

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

# Painel linhas 43..56: o termo de Controle_Entradas usa uma referência relativa
# (R43C[-79] / R43C[-75]) que aponta para células diferentes da linha 43 a cada mês.
# Só as células de texto podem casar com Classificação; estas são as únicas:
# D43, AI43 e CC43 = "Terreno"; AS43 = "OU". Chave = índice do mês na linha do tempo.
ROTULO_ENTRADAS_CUSTOS_POR_MES = {0: "Terreno", 27: "Terreno", 37: "OU", 73: "Terreno"}

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
    "dashboards.ver": "Ver a aba Dashboards",
    "painel.ver": "Ver a aba Painel",
    "projecao.ver": "Ver a aba Projeção e editar as linhas do próprio setor",
    "projecao.editar_todos_setores": "Editar a projeção de qualquer setor",
    "projecao.editar_meses_passados": "Editar meses anteriores ao corrente",
    "apis.ver": "Ver a aba API's (fontes, pendências, saldos, viabilidade e histórico)",
    "fontes.atualizar": "Atualizar as fontes (SharePoint ou Excel)",
    "fontes.classificar": "Classificar lançamentos pendentes (DePara)",
    "saldos.editar": "Lançar e excluir saldos bancários",
    "premissas.editar": "Editar premissas do aporte e viabilidade",
    "setores.gerenciar": "Criar e alterar setores e linhas de projeção",
    "usuarios.gerenciar": "Gerenciar usuários, papéis e permissões dentro do app",
}
PERMISSOES_PADRAO = {                       # concedidas quando o papel é criado
    PAPEL_ADMIN: list(PERMISSOES),
    "diretor": [p for p in PERMISSOES if p not in ("setores.gerenciar", "usuarios.gerenciar")],
}
PERMISSOES_SETOR = ["projecao.ver"]         # papel de setor novo
# Abas ainda em construção: aparecem como "Em breve" para todos, menos para o papel admin.
ABAS_EM_BREVE = ["dashboards", "painel"]

"""Aba Painel: realizado x projetado x EVE por rubrica, com linha do tempo mensal.

Colunas (letra da planilha → letra na tela):
  H → A  Realizado até o mês de análise    L → B  Projetado do mês corrente
  P → C  Projetado (mês corrente em diante) T → D  Total (A + C)
  X → E  Previsto no EVE                    Y → AV % do VGV
  AB → F % do EVE (D ÷ E)                   CE..FJ  linha do tempo jan/2024 a dez/2030

Regra única de corte: REALIZADO = meses até o mês de análise (fim do mês anterior à
data-base); PROJETADO = do mês corrente em diante. Toda linha é fechada por `_fechar`,
então A = soma da linha do tempo até o corte e C = soma depois dele (a conferência
"linha do tempo × colunas" fica garantida por construção).

Correções aprovadas em relação à planilha (revisão do Painel, out/2026):
  P1. Meses passados mostram só o realizado. A planilha usava o projetado quando o
      realizado do mês era zero (e um termo de Controle Entradas que só valia em 4 meses).
  P2. C (Projetado) = projeção do mês corrente em diante. A planilha somava a projeção de
      todos os meses, inclusive os já realizados (contava em dobro).
  P3. B (Projetado do mês) = valor do mês corrente. Na planilha filtrava o tipo
      "Projetado (Mês)", que nenhuma linha usa: era sempre zero.
  P4. Mesmo corte em todas as linhas. Na planilha o realizado ia até o mês de análise e o
      projetado começava depois do mês corrente: o mês corrente ficava fora das duas colunas
      em receitas, resultado e sócios.
  P5. Rendimentos entram pelo mês da data (a planilha só contava os do último dia do mês).
  P6. Margem Operacional inclui a Receita Líquida (era só a soma dos custos), e Resultado e
      Saldo de Caixa têm o realizado (a coluna A era zero fixo).
  P7. Aporte Investidor: Recebidas do investidor em todos os meses. A planilha somava, na
      linha do tempo, Recebidas de qualquer cliente e só a partir de jul/2026.
  P8. Clientes - Direto com SPE: Recebidas dos demais clientes (vendas). Era vazia.
  P9. Saldo de Caixa (Banco): linha do tempo = fluxo de caixa do mês (operação + investidor +
      holding) e linha 122 = saldo acumulado, que no mês de análise é igual à coluna A.
      A planilha somava dividendos duas vezes no projetado e a linha 122 não acumulava.
  P10. Sem sinal invertido em 2024, sem "#VALUE!" (B da Exposição Máxima) e % do EVE com o
      sinal da natureza da linha (receita: D ÷ E; custo/despesa: −D ÷ E = % consumido).
  P11. Coluna E só com o previsto no EVE: vazia em sócios e no Saldo de Caixa (Banco), onde a
      planilha repetia o total da linha, e Resultado / VGV só no EVE (sem vendas, o realizado
      dividido pelo VGV realizado dava percentuais sem sentido).
O teste de regressão compara todas as demais células com a planilha.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..catalogo import (CUSTOS, DESPESAS, IMPOSTO_RECEITA_ALIQUOTA, IMPOSTO_RECEITA_EVE,
                        INICIO_LINHA_DO_TEMPO, MESES_LINHA_DO_TEMPO, PREMISSAS_DESEMBOLSO,
                        RECEITAS_EVE, TIR_EVE, Premissas)
from ..config import CLIENTE_INVESTIDOR, EMPRESA_SPE, HISTORICO_APORTE_INVESTIDOR
from ..excel_funcoes import arredondar, eomonth, meses_entre, texto_igual, texto_mes
from .base import Base, somar
from .resumo import saldo_fim_de_mes

TIPO_PROJETADO_TOTAL = "Projetado Total"   # tipo das linhas da Projeção (Painel P23)
LINHA_CLIENTES = 25                        # Clientes - Direto com SPE (Recebidas de vendas)
LINHA_RENDIMENTOS = 32

# Linhas cuja linha do tempo não é fluxo do mês (índice, acumulado ou saldo): não entram
# na conferência "linha do tempo × colunas" (FS..FV).
SEM_CONFERENCIA = {95, 97, 99, 101, 119, 122}


@dataclass
class Linha:
    linha_excel: int
    rotulo: str
    grupo: str
    H: float | None = None
    L: float | None = None
    P: float | None = None
    T: float | None = None
    X: float | None = None
    Y: float | None = None
    AB: float | None = None
    tl: list[float | None] = field(default_factory=lambda: [None] * MESES_LINHA_DO_TEMPO)
    extras: dict = field(default_factory=dict)


def _n(valor) -> float:
    return valor if isinstance(valor, (int, float)) else 0.0


def _zeros() -> list[float]:
    return [0.0] * MESES_LINHA_DO_TEMPO


def _razao(a, b) -> float:
    return 0.0 if _n(b) == 0 else _n(a) / _n(b)


class _Painel:
    def __init__(self, base: Base, hoje: date, viabilidade: dict[str, float], premissas: Premissas):
        self.base = base
        self.viab = viabilidade
        self.premissas = premissas
        self.d22 = eomonth(hoje, -1)            # mês de análise: último mês realizado
        self.h21 = eomonth(hoje, 0)             # mês corrente: primeiro mês projetado
        self.meses = meses_entre(INICIO_LINHA_DO_TEMPO, MESES_LINHA_DO_TEMPO)
        self.i_corrente = self.meses.index(self.h21) if self.h21 in self.meses else None
        self.linhas: dict[int, Linha] = {}

    # ---------------------------------------------------------------- utilitários
    def realizado(self, tl) -> float:           # meses até o mês de análise
        return sum(_n(v) for m, v in zip(self.meses, tl) if m <= self.d22)

    def projetado_tl(self, tl) -> float:        # mês corrente em diante
        return sum(_n(v) for m, v in zip(self.meses, tl) if m > self.d22)

    def do_mes_corrente(self, tl) -> float | None:
        return None if self.i_corrente is None else _n(tl[self.i_corrente])

    def soma_linhas(self, campo: str, linhas) -> float:
        return sum(_n(getattr(self.linhas[r], campo)) for r in linhas if r in self.linhas)

    def soma_tl(self, linhas) -> list[float]:
        return [sum(_n(self.linhas[r].tl[i]) for r in linhas if r in self.linhas)
                for i in range(MESES_LINHA_DO_TEMPO)]

    def add(self, linha: Linha) -> Linha:
        self.linhas[linha.linha_excel] = linha
        return linha

    def fechar(self, linha: Linha) -> Linha:
        """Colunas A, B, C e D a partir da linha do tempo, com o corte único."""
        linha.H = self.realizado(linha.tl)
        linha.L = self.do_mes_corrente(linha.tl)
        linha.P = self.projetado_tl(linha.tl)
        linha.T = linha.H + linha.P
        return self.add(linha)

    def total(self, r: int, rotulo: str, faixa, grupo: str = "total") -> Linha:
        """Linha de total: soma a linha do tempo e o EVE (X) das linhas da faixa."""
        linha = Linha(r, rotulo, grupo, tl=self.soma_tl(faixa), X=self.soma_linhas("X", faixa))
        return self.fechar(linha)

    def projecao(self, rotulo: str, mes: date) -> float:
        return somar(self.base.filtrar("projecao", "descricao", rotulo),
                     lambda p: p.data == mes and texto_igual(p.tipo, TIPO_PROJETADO_TOTAL))

    def por_mes(self, registros, condicao=lambda r: True) -> list[float]:
        """Soma de `registros` por fim de mês, na grade da linha do tempo."""
        totais: dict[date, float] = {}
        for r in registros:
            if condicao(r):
                totais[r.fim_mes] = totais.get(r.fim_mes, 0.0) + r.valor
        return [totais.get(m, 0.0) for m in self.meses]

    # ---------------------------------------------------------------- receitas
    def receitas(self) -> None:
        b = self.base
        for r, (rotulo, eve) in RECEITAS_EVE.items():
            linha = Linha(r, rotulo, "receita", X=eve, tl=_zeros())
            if r == LINHA_CLIENTES:            # P8: Recebidas de clientes que não são o investidor
                linha.tl = self.por_mes(b.recebidas, lambda x: x.cliente != CLIENTE_INVESTIDOR)
            elif r == LINHA_RENDIMENTOS:       # P5: Controle Entradas pelo mês da data
                linha.tl = self.por_mes(b.filtrar("entradas", "classificacao", rotulo))
            self.fechar(linha)

        self.total(36, "Receita Total (VGV)", range(25, 36))

        imposto = self.fechar(Linha(38, "2.1 Impostos s/ R.B. (Pis e Cofins)", "receita",
                                    X=IMPOSTO_RECEITA_EVE, tl=_zeros()))
        imposto.extras = {"AR": IMPOSTO_RECEITA_ALIQUOTA,
                          "BB": IMPOSTO_RECEITA_ALIQUOTA * _n(self.linhas[34].P)}

        self.total(41, "Receita Líquida", (36, 38))

    # ---------------------------------------------------------------- custos/despesas
    def rubrica(self, r: int, nome: str, grupo: str) -> Linha:
        """Custo ou despesa, com sinal negativo. Realizado = Custos SPE e NN's pagos + Controle
        Saídas, pelo fim de mês; projetado = Projeção dos setores (P1: meses passados só realizado)."""
        b = self.base
        pago = lambda d: texto_igual(d.status, "Pago")
        realizado = [a + c + s for a, c, s in zip(
            self.por_mes(b.filtrar("custos_spe", "classificacao", nome), pago),
            self.por_mes(b.filtrar("custos_nn", "classificacao", nome), pago),
            self.por_mes(b.filtrar("saidas", "classificacao", nome)))]
        tl = [0.0 - (feito if m <= self.d22 else self.projecao(nome, m))   # 0.0 − x: sem "-0,00"
              for m, feito in zip(self.meses, realizado)]

        linha = self.fechar(Linha(r, nome, grupo, tl=tl, X=self.viab.get(nome, 0)))
        premissa = PREMISSAS_DESEMBOLSO.get(r, {})
        primeiro, parcelas = premissa.get("primeiro_mes"), premissa.get("parcelas")
        valor_mes, valor_total = premissa.get("valor_mes"), premissa.get("valor_total")
        linha.extras = {
            "BA": (date(primeiro.year + (primeiro.month + parcelas - 2) // 12,
                        (primeiro.month + parcelas - 2) % 12 + 1, 1)
                   if primeiro and parcelas else 0),
            "BB": (valor_mes * (parcelas or 0)) if valor_mes else _n(valor_total),
        }
        return linha

    def custos_e_despesas(self) -> None:
        # P6: margem = receita líquida − custos; o EVE dos custos é positivo (viabilidade).
        for nome, _, r, _ in CUSTOS:
            self.rubrica(r, nome, "custo")
        custos = [r for _, _, r, _ in CUSTOS]
        margem = self.total(59, "Margem Operacional (Bruta)", [41, *custos])
        margem.X = _n(self.linhas[41].X) - self.soma_linhas("X", custos)

        for nome, _, r, _ in DESPESAS:
            self.rubrica(r, nome, "despesa")
        despesas = [r for _, _, r, _ in DESPESAS]
        ebitda = self.total(79, "EBITDA", [59, *despesas])
        ebitda.X = _n(margem.X) - self.soma_linhas("X", despesas)

    # ---------------------------------------------------------------- resultado e caixa
    def resultado(self) -> None:
        self.fechar(Linha(81, "Impostos s/ Lucro (I.R./CSLL)", "resultado", X=0.0, tl=_zeros()))
        self.total(83, "RESULTADO (antes dos empréstimos)", (79, 81))
        for r, rotulo in ((85, "Empréstimos na SPE (Terceiros)"),
                          (86, "Remuneração do Capital de Investidores"),
                          (87, "Receita Financeira da SPE"),
                          (88, "Impostos s/ Lucro (I.R./CSLL)")):
            self.fechar(Linha(r, rotulo, "resultado", X=0.0, tl=_zeros()))
        saldo = self.total(93, "SALDO DE CAIXA", range(83, 89))

        # 95: saldo de caixa acumulado na linha do tempo; coluna E = Resultado ÷ VGV do EVE.
        # A, B, C e D ficam vazias: sem vendas, o realizado ÷ VGV dá percentuais sem sentido.
        acumulado, soma = [], 0.0
        for v in saldo.tl:
            soma += _n(v)
            acumulado.append(soma)
        self.add(Linha(95, "Resultado / VGV", "indicador", tl=acumulado,
                       X=_razao(saldo.X, self.linhas[36].X)))
        self.add(Linha(97, "", "indicador", T=0.0, X=TIR_EVE[97]))
        self.add(Linha(99, "M T I R (a.m.)", "indicador", T=0.0, X=TIR_EVE[99]))

        # 101: A = acumulado no mês de análise; D = pior acumulado do horizonte; C = D − A.
        no_corte = next((v for m, v in zip(self.meses, acumulado) if m == self.d22), 0.0)
        pior = min(acumulado)
        self.add(Linha(101, "Exposição Máxima", "indicador", H=no_corte, P=pior - no_corte,
                       T=pior, X=0.0))

    # ---------------------------------------------------------------- investidor / holding
    def socios(self) -> None:
        b = self.base
        transferencias_para_spe = [t for t in b.transferencias
                                   if t.empresa != EMPRESA_SPE and t.empresa_credito == EMPRESA_SPE]
        transferencias_da_spe = [t for t in b.transferencias
                                 if t.empresa == EMPRESA_SPE and t.empresa_credito != EMPRESA_SPE]
        entradas_investidor = lambda e: texto_igual(e.historico, HISTORICO_APORTE_INVESTIDOR)
        mais = lambda *listas: [sum(v) for v in zip(*listas)]
        menos = lambda tl: [0.0 - v for v in tl]

        # P7: aportes do investidor = Controle Entradas "Aporte" (até jun/2026, antes da
        # Recebidas existir) + Recebidas do investidor, pelo fim de mês.
        investidor = [
            Linha(106, "Aporte Investidor", "socio", tl=mais(
                self.por_mes(b.filtrar("entradas", "classificacao", "Aporte"), entradas_investidor),
                self.por_mes(b.recebidas, lambda x: x.cliente == CLIENTE_INVESTIDOR))),
            Linha(107, "Retorno de Aporte Investidor", "socio",
                  tl=menos(self.por_mes(b.filtrar("saidas", "classificacao", "Retorno de Aporte")))),
            Linha(108, "Remuneração Investidor", "socio", tl=_zeros()),
            Linha(109, "Dividendos Investidor", "socio", tl=_zeros()),
        ]
        holding = [
            Linha(112, "Aporte Holding", "socio", tl=mais(
                self.por_mes(transferencias_para_spe),
                self.por_mes(b.filtrar("entradas", "classificacao", "Aporte Holding")))),
            Linha(113, "Retorno de Aporte Holding", "socio", tl=menos(mais(
                self.por_mes(transferencias_da_spe),
                self.por_mes(b.filtrar("saidas", "classificacao", "Retorno de Aporte Holding"))))),
            Linha(114, "Custo Financeiro", "socio", tl=_zeros()),
            Linha(115, "Remuneração Holding", "socio", tl=_zeros()),
            Linha(116, "Dividendos Holding", "socio", tl=_zeros()),
        ]
        # Sócios não têm previsto no EVE: coluna E vazia (a planilha repetia o total da linha).
        for linha in investidor + holding:
            self.fechar(linha)
        self.total(105, "INVESTIDOR", range(106, 110)).X = None
        self.total(111, "HOLDING", range(112, 117)).X = None

    def saldo_banco(self) -> None:
        """P9: fluxo de caixa do mês (operação + investidor + holding) e saldo acumulado.
        A = saldo no fim do mês de análise = ajuste inicial (premissa) + fluxos realizados."""
        fluxo = self.soma_tl((93, 105, 111))
        saldo = self.add(Linha(119, "Saldo de Caixa (Banco)", "total", tl=fluxo))
        saldo.H = self.realizado(fluxo) + self.premissas.ajuste_saldo_banco
        saldo.L = self.do_mes_corrente(fluxo)
        saldo.P = arredondar(self.projetado_tl(fluxo), 2)
        saldo.T = saldo.H + saldo.P

        acumulado, soma = [], self.premissas.ajuste_saldo_banco
        for v in fluxo:
            soma += v
            acumulado.append(soma)
        self.add(Linha(122, "Saldo de caixa acumulado", "auxiliar", tl=acumulado))

    # ---------------------------------------------------------------- colunas derivadas
    def derivadas(self) -> None:
        x36 = _n(self.linhas[36].X)
        sem_y = {95, 97, 99, 101, 119, 122} | set(range(105, 117))
        for r, linha in self.linhas.items():
            if r not in sem_y:
                linha.Y = (0.0 if x36 == 0 else
                           (_n(linha.X) / x36 if r == 36 else abs(_n(linha.X) / x36)))
            # F = D ÷ E. Receita: % realizado do previsto; custo/despesa: % consumido.
            # Totais que misturam receita e custo (margem, EBITDA, resultado) não têm F.
            if linha.grupo in ("receita", "custo", "despesa") or r in (36, 41):
                sinal = -1 if linha.grupo in ("custo", "despesa") else 1
                linha.AB = 0.0 if _n(linha.X) == 0 else sinal * _n(linha.T) / _n(linha.X)
            elif linha.grupo == "resultado":        # 81, 85..88: desvio sobre o EVE
                linha.AB = 0.0 if _n(linha.X) == 0 else _n(linha.T) / _n(linha.X) - 1
        # Conferência linha do tempo × colunas (FS..FV), só nas linhas de fluxo.
        for r, linha in self.linhas.items():
            if r in SEM_CONFERENCIA:
                continue
            realizado, projetado = self.realizado(linha.tl), self.projetado_tl(linha.tl)
            linha.extras.update({
                "FS": realizado, "FV": projetado,
                "FT": "OK!" if arredondar(realizado - _n(linha.H), 2) == 0 else "ERRO",
                "FU": "OK!" if arredondar(projetado - _n(linha.P), 2) == 0 else "ERRO"})

    def conciliacao(self) -> dict:
        """Saldo do Painel (coluna A da linha 119) × saldo dos extratos (aba Saldo) no fim do
        mês de análise. Diferença ≠ 0 indica lançamento sem classificação ou ajuste a revisar."""
        painel = _n(self.linhas[119].H)
        tem_saldo = any(eomonth(s.data) == self.d22 for s in self.base.saldos)
        banco = saldo_fim_de_mes(self.base, self.d22) if tem_saldo else None
        return {"mes": self.d22, "saldo_painel": painel, "saldo_banco": banco,
                "diferenca": None if banco is None else arredondar(painel - banco, 2)}

    def calcular(self) -> dict:
        self.receitas()
        self.custos_e_despesas()
        self.resultado()
        self.socios()
        self.saldo_banco()
        self.derivadas()
        return {
            # corte = primeiro mês projetado (destacado na linha do tempo)
            "datas": {"mes_analise": self.d22, "mes_atual": self.h21, "corte": self.h21},
            "titulos": {"ate": f"ATÉ {texto_mes(self.d22).upper()}",
                        "realizado": f"Realizado até {texto_mes(self.d22)[:4]}{str(self.d22.year)[2:]}",
                        "projetado_mes": f"Projetado {texto_mes(self.h21)[:4]}{str(self.h21.year)[2:]}"},
            "meses": self.meses,
            "linhas": [self.linhas[r] for r in sorted(self.linhas)],
            "conciliacao": self.conciliacao(),
        }


def calcular_painel(base: Base, hoje: date, viabilidade: dict[str, float],
                    premissas: Premissas) -> dict:
    return _Painel(base, hoje, viabilidade, premissas).calcular()

"""Aba Painel: realizado x projetado x EVE por rubrica, com linha do tempo mensal.

Colunas da planilha (linha 22/23):
  H = Realizado até o mês de análise     L = Projetado (Mês)      P = Projetado Total
  T = Total (H + P)                      X = Previsto no EVE      Y = AV (% do VGV)
  AB = Desvio                            CE..FJ = jan/2024 a dez/2030
As peculiaridades das fórmulas originais são mantidas de propósito e estão
comentadas onde ocorrem (os valores precisam bater com a planilha).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..catalogo import (CUSTOS, DESPESAS, IMPOSTO_RECEITA_ALIQUOTA, IMPOSTO_RECEITA_EVE,
                        INICIO_LINHA_DO_TEMPO, MESES_LINHA_DO_TEMPO, MESES_SEM_INVERSAO_SINAL,
                        PREMISSAS_DESEMBOLSO, RECEITAS_EVE, ROTULO_ENTRADAS_CUSTOS_POR_MES,
                        TIR_EVE, Premissas)
from ..config import (CLIENTE_INVESTIDOR, EMPRESA_SPE, HISTORICO_APORTE_INVESTIDOR,
                      MES_INICIO_RECEBIDAS_NO_APORTE)
from ..excel_funcoes import DATA_ZERO, arredondar, eomonth, meses_entre, texto_igual, texto_mes
from .base import Base, somar

TIPO_PROJETADO_MES = "Projetado (Mês)"     # Painel L23 (nenhuma linha da Projeção usa este tipo)
TIPO_PROJETADO_TOTAL = "Projetado Total"   # Painel P23
ERRO_VALOR = "#VALUE!"


@dataclass
class Linha:
    linha_excel: int
    rotulo: str
    grupo: str
    H: float | None = None
    L: float | str | None = None
    P: float | None = None
    T: float | None = None
    X: float | None = None
    Y: float | None = None
    AB: float | None = None
    tl: list[float | None] = field(default_factory=lambda: [None] * MESES_LINHA_DO_TEMPO)
    extras: dict = field(default_factory=dict)


def _n(valor) -> float:
    return valor if isinstance(valor, (int, float)) else 0.0


class _Painel:
    def __init__(self, base: Base, hoje: date, viabilidade: dict[str, float], premissas: Premissas):
        self.base = base
        self.viab = viabilidade
        self.premissas = premissas
        self.d22 = eomonth(hoje, -1)            # mês de análise
        self.h21 = eomonth(hoje, 0)             # mês corrente
        self.ai23 = eomonth(self.d22, 1)        # corte realizado/projetado
        self.meses = meses_entre(INICIO_LINHA_DO_TEMPO, MESES_LINHA_DO_TEMPO)
        self.linhas: dict[int, Linha] = {}

    # ---------------------------------------------------------------- utilitários
    def soma_ate(self, tl) -> float:            # SUMIF(datas;"<="&AI23;linha)
        return sum(_n(v) for m, v in zip(self.meses, tl) if m <= self.ai23)

    def soma_apos(self, tl, corte: date | None = None) -> float:   # SUMIF(datas;">"&AI23;linha)
        corte = corte or self.ai23
        return sum(_n(v) for m, v in zip(self.meses, tl) if m > corte)

    def soma_linhas(self, campo: str, linhas) -> float:
        return sum(_n(getattr(self.linhas[r], campo)) for r in linhas if r in self.linhas)

    def soma_tl(self, linhas, i: int) -> float:
        return sum(_n(self.linhas[r].tl[i]) for r in linhas if r in self.linhas)

    def add(self, linha: Linha) -> Linha:
        self.linhas[linha.linha_excel] = linha
        return linha

    def projetado(self, rotulo: str, tipo: str, data: date | None = None) -> float:
        return somar(self.base.filtrar("projecao", "descricao", rotulo),
                     lambda p: texto_igual(p.tipo, tipo) and (data is None or p.data == data))

    # ---------------------------------------------------------------- receitas
    def receitas(self) -> None:
        b = self.base
        for r, (rotulo, eve) in RECEITAS_EVE.items():
            linha = Linha(r, rotulo, "receita", X=eve)
            if r == 32:   # Rendimentos: Controle_Entradas com Data_es igual ao fim do mês
                entradas = b.filtrar("entradas", "classificacao", rotulo)
                linha.tl = [somar(entradas, lambda e, m=m: e.data == m) for m in self.meses]
                linha.H = somar(entradas, lambda e: (e.data or DATA_ZERO) <= self.d22)
            elif r in (25, 26, 29):
                linha.H = 0.0
            else:
                linha.H = self.soma_ate(linha.tl)
            if r not in (26, 29):
                linha.L = linha.P = self.soma_apos(linha.tl)
            linha.T = _n(linha.H) + _n(linha.P)
            self.add(linha)

        total = self.add(Linha(36, "Receita Total (VGV)", "total"))
        faixa = range(25, 36)
        for campo in ("H", "L", "P", "T", "X"):
            setattr(total, campo, self.soma_linhas(campo, faixa))
        # CE36..CP36 (2024) não têm fórmula na planilha.
        total.tl = [None if i < MESES_SEM_INVERSAO_SINAL else self.soma_tl(faixa, i)
                    for i in range(MESES_LINHA_DO_TEMPO)]

        imposto = self.add(Linha(38, "2.1 Impostos s/ R.B. (Pis e Cofins)", "receita",
                                 X=IMPOSTO_RECEITA_EVE, tl=[0.0] * MESES_LINHA_DO_TEMPO))
        imposto.H = self.soma_ate(imposto.tl)
        imposto.L = imposto.P = self.soma_apos(imposto.tl)
        imposto.T = imposto.H + imposto.P
        imposto.extras = {"AR": IMPOSTO_RECEITA_ALIQUOTA,
                          "BB": IMPOSTO_RECEITA_ALIQUOTA * _n(self.linhas[34].P)}

        liquida = self.add(Linha(41, "Receita Líquida", "total"))
        for campo in ("H", "L", "P", "T", "X"):
            setattr(liquida, campo, _n(getattr(total, campo)) + _n(getattr(imposto, campo)))
        liquida.tl = [_n(a) + _n(b) for a, b in zip(total.tl, imposto.tl)]

    # ---------------------------------------------------------------- custos/despesas
    def rubrica(self, r: int, nome: str, grupo: str) -> Linha:
        b = self.base
        spe = b.filtrar("custos_spe", "classificacao", nome)
        nn = b.filtrar("custos_nn", "classificacao", nome)
        saidas = b.filtrar("saidas", "classificacao", nome)
        pago = lambda d, m: d.fim_mes == m and texto_igual(d.status, "Pago")

        tl = []
        for i, m in enumerate(self.meses):
            realizado = (somar(spe, lambda d: pago(d, m)) + somar(nn, lambda d: pago(d, m))
                         + somar(saidas, lambda s: s.fim_mes == m))
            teste = realizado
            if grupo == "custo" and i in ROTULO_ENTRADAS_CUSTOS_POR_MES:
                # Termo de Controle_Entradas que só entra no teste "=0" (ver catálogo).
                teste += somar(b.filtrar("entradas", "classificacao",
                                         ROTULO_ENTRADAS_CUSTOS_POR_MES[i]),
                               lambda e: e.fim_mes <= self.d22)
            projecao = self.projetado(nome, TIPO_PROJETADO_TOTAL, m)
            valor = (projecao if teste == 0 else realizado) if m <= self.d22 else projecao
            tl.append(valor if i < MESES_SEM_INVERSAO_SINAL else -valor)

        ate = lambda d: d.fim_mes <= self.d22 and texto_igual(d.status, "Pago")
        linha = Linha(r, nome, grupo, tl=tl, X=self.viab.get(nome, 0))
        linha.H = -(somar(spe, ate) + somar(nn, ate) + somar(saidas, lambda s: s.fim_mes <= self.d22))
        linha.L = self.projetado(nome, TIPO_PROJETADO_MES, self.h21)
        linha.P = -self.projetado(nome, TIPO_PROJETADO_TOTAL)
        linha.T = linha.H + linha.P
        premissa = PREMISSAS_DESEMBOLSO.get(r, {})
        primeiro, parcelas = premissa.get("primeiro_mes"), premissa.get("parcelas")
        valor_mes, valor_total = premissa.get("valor_mes"), premissa.get("valor_total")
        linha.extras = {
            "BA": (date(primeiro.year + (primeiro.month + parcelas - 2) // 12,
                        (primeiro.month + parcelas - 2) % 12 + 1, 1)
                   if primeiro and parcelas else 0),
            "BB": (valor_mes * (parcelas or 0)) if valor_mes else _n(valor_total),
        }
        return self.add(linha)

    def custos_e_despesas(self) -> None:
        for nome, _, r, _ in CUSTOS:
            self.rubrica(r, nome, "custo")
        margem = self.add(Linha(59, "Margem Operacional (Bruta)", "total"))
        for campo in ("H", "L", "P", "T", "X"):
            setattr(margem, campo, self.soma_linhas(campo, range(43, 57)))
        margem.tl = [self.soma_tl(range(43, 57), i) for i in range(MESES_LINHA_DO_TEMPO)]

        for nome, _, r, _ in DESPESAS:
            self.rubrica(r, nome, "despesa")
        ebitda = self.add(Linha(79, "EBITDA", "total"))
        ebitda.H = self.soma_linhas("H", range(59, 77))
        ebitda.L = self.soma_linhas("L", range(61, 77))      # L79 = SUM(L61:L76)
        ebitda.P = self.soma_linhas("P", range(59, 77))
        ebitda.T = self.soma_linhas("T", range(59, 77))
        ebitda.X = self.soma_linhas("X", range(61, 77))      # X79 = SUM(X61:X76)
        ebitda.tl = [self.soma_tl(range(59, 77), i) for i in range(MESES_LINHA_DO_TEMPO)]

    # ---------------------------------------------------------------- resultado e caixa
    def resultado(self) -> None:
        zeros = [0.0] * MESES_LINHA_DO_TEMPO
        ir = self.add(Linha(81, "Impostos s/ Lucro (I.R./CSLL)", "resultado", H=0.0, X=0.0))
        ir.L = ir.P = self.soma_apos(ir.tl)
        ir.T = ir.H + ir.P

        res = self.add(Linha(83, "RESULTADO (antes dos empréstimos)", "total", H=0.0))
        res.tl = [_n(a) + _n(b) for a, b in zip(self.linhas[79].tl, ir.tl)]
        res.L = res.P = self.soma_apos(res.tl)
        res.T = res.H + res.P
        res.X = _n(self.linhas[79].X) + _n(ir.X)

        for r, rotulo in ((85, "Empréstimos na SPE (Terceiros)"),
                          (86, "Remuneração do Capital de Investidores"),
                          (87, "Receita Financeira da SPE")):
            linha = self.add(Linha(r, rotulo, "resultado", H=0.0, X=0.0, tl=list(zeros)))
            linha.L = linha.P = self.soma_apos(linha.tl, self.h21)
            linha.T = linha.H + linha.P
        ir2 = self.add(Linha(88, "Impostos s/ Lucro (I.R./CSLL)", "resultado", X=0.0, tl=list(zeros)))
        ir2.L = ir2.P = self.soma_apos(ir2.tl)
        ir2.T = _n(ir2.H) + ir2.P

        saldo = self.add(Linha(93, "SALDO DE CAIXA", "total"))
        faixa = range(83, 89)
        for campo in ("H", "L", "P", "T", "X"):
            setattr(saldo, campo, self.soma_linhas(campo, faixa))
        saldo.tl = [_n(res.tl[i]) + self.soma_tl(range(85, 89), i)
                    for i in range(MESES_LINHA_DO_TEMPO)]

        vgv = self.linhas[36]
        razao = lambda a, b: 0.0 if _n(b) == 0 else _n(a) / _n(b)
        acumulado, acc = [], 0.0
        for v in saldo.tl:
            acc += _n(v)
            acumulado.append(acc)
        self.add(Linha(95, "Resultado / VGV", "indicador", H=0.0, tl=acumulado,
                       L=razao(saldo.L, vgv.L), P=razao(None, vgv.P),   # P95 usa P91 (vazio)
                       T=razao(saldo.T, vgv.T), X=razao(saldo.X, vgv.X)))
        self.add(Linha(97, "", "indicador", T=0.0, X=TIR_EVE[97]))
        self.add(Linha(99, "M T I R (a.m.)", "indicador", T=0.0, X=TIR_EVE[99]))

        no_corte = next((v for m, v in zip(self.meses, acumulado) if m == self.ai23), 0.0)
        exposicao = self.add(Linha(101, "Exposição Máxima", "indicador", H=no_corte, X=0.0,
                                   L=ERRO_VALOR))       # L101 = MIN(...) - D101 (texto) → #VALUE!
        exposicao.P = min(acumulado) - exposicao.H
        exposicao.T = exposicao.H + exposicao.P

    # ---------------------------------------------------------------- investidor / holding
    def socios(self) -> None:
        b = self.base
        ent_aporte = [e for e in b.filtrar("entradas", "classificacao", "Aporte")
                      if texto_igual(e.historico, HISTORICO_APORTE_INVESTIDOR)]
        aporte = Linha(106, "Aporte Investidor", "socio")
        aporte.tl = [somar(ent_aporte, lambda e, m=m: e.fim_mes == m)
                     + (somar(b.recebidas, lambda x, m=m: x.fim_mes == m)
                        if i >= MES_INICIO_RECEBIDAS_NO_APORTE else 0.0)
                     for i, m in enumerate(self.meses)]
        aporte.H = (somar(ent_aporte, lambda e: e.fim_mes <= self.d22)
                    + somar(b.recebidas, lambda x: x.fim_mes <= self.d22
                            and x.cliente == CLIENTE_INVESTIDOR))

        saidas_retorno = b.filtrar("saidas", "classificacao", "Retorno de Aporte")
        retorno = Linha(107, "Retorno de Aporte Investidor", "socio")
        retorno.tl = [-somar(saidas_retorno, lambda s, m=m: s.fim_mes == m) for m in self.meses]
        retorno.H = -somar(saidas_retorno, lambda s: (s.data or DATA_ZERO) <= self.d22)

        remuneracao = Linha(108, "Remuneração Investidor", "socio")
        dividendos = Linha(109, "Dividendos Investidor", "socio")
        dividendos.H = self.soma_ate(dividendos.tl)

        entrada_holding = lambda m_ok: (
            somar(b.transferencias, lambda t: t.empresa != EMPRESA_SPE
                  and t.empresa_credito == EMPRESA_SPE and m_ok(t.fim_mes))
            + somar(b.filtrar("entradas", "classificacao", "Aporte Holding"),
                    lambda e: m_ok(e.fim_mes)))
        saida_holding = lambda m_ok: -(
            somar(b.transferencias, lambda t: t.empresa == EMPRESA_SPE
                  and t.empresa_credito != EMPRESA_SPE and m_ok(t.fim_mes))
            + somar(b.filtrar("saidas", "classificacao", "Retorno de Aporte Holding"),
                    lambda s: m_ok(s.fim_mes)))
        aporte_h = Linha(112, "Aporte Holding", "socio",
                         tl=[entrada_holding(lambda f, m=m: f == m) for m in self.meses],
                         H=entrada_holding(lambda f: f <= self.d22))
        retorno_h = Linha(113, "Retorno de Aporte Holding", "socio",
                          tl=[saida_holding(lambda f, m=m: f == m) for m in self.meses],
                          H=saida_holding(lambda f: f <= self.d22))
        outros_h = [Linha(114, "Custo Financeiro", "socio", H=0.0),
                    Linha(115, "Remuneração Holding", "socio", H=0.0),
                    Linha(116, "Dividendos Holding", "socio", H=0.0)]

        for linha in [aporte, retorno, remuneracao, dividendos, aporte_h, retorno_h, *outros_h]:
            linha.L = linha.P = self.soma_apos(linha.tl)
            linha.T = _n(linha.H) + linha.P
            linha.X = sum(_n(v) for v in linha.tl)
            self.add(linha)

        for r, rotulo, faixa in ((105, "INVESTIDOR", range(106, 110)),
                                 (111, "HOLDING", range(112, 117))):
            total = self.add(Linha(r, rotulo, "total"))
            for campo in ("H", "L", "P", "T", "X"):
                setattr(total, campo, self.soma_linhas(campo, faixa))
            total.tl = [self.soma_tl(faixa, i) for i in range(MESES_LINHA_DO_TEMPO)]

        # Linha 117 só existe em CE e CF: IF(data<=AI23; 0; anterior - L111 - L116).
        auxiliar = self.add(Linha(117, "", "auxiliar"))
        anterior = 0.0
        for i in range(2):
            anterior = (0.0 if self.meses[i] <= self.ai23 else
                        anterior - _n(self.linhas[111].tl[i]) - _n(self.linhas[116].tl[i]))
            auxiliar.tl[i] = anterior

    def saldo_banco(self) -> None:
        get = lambda r, c: _n(getattr(self.linhas[r], c))
        saldo = self.add(Linha(119, "Saldo de Caixa (Banco)", "total"))
        saldo.H = (get(36, "H") + get(79, "H") + get(105, "H") + get(111, "H")
                   + self.premissas.ajuste_saldo_banco)
        for campo in ("L", "P"):
            setattr(saldo, campo, arredondar(sum(get(r, campo) for r in (93, 105, 109, 111, 116)), 2))
        saldo.T = saldo.H + saldo.P
        saldo.X = arredondar(get(93, "X") + get(105, "X") + get(111, "X"), 1)
        saldo.tl = [-_n(self.linhas[111].tl[i]) if i < 30 else None
                    for i in range(MESES_LINHA_DO_TEMPO)]

        acumulado = self.add(Linha(122, "Inadimplência Atual", "auxiliar"))
        acumulado.tl = [_n(self.linhas[93].tl[i]) + _n(self.linhas[105].tl[i])
                        + _n(self.linhas[111].tl[i]) for i in range(MESES_LINHA_DO_TEMPO)]
        h36 = get(36, "H")
        acumulado.extras = {"J": ERRO_VALOR, "N": 0.0 if h36 == 0 else 0.0 / h36}

    # ---------------------------------------------------------------- colunas derivadas
    def derivadas(self) -> None:
        x36 = _n(self.linhas[36].X)
        sem_y = {56, 76, 95, 97, 99, 101, 117, 119, 122} | set(range(105, 117))
        desvio_menos_um = {81, 85, 86, 87, 88}
        for r, linha in self.linhas.items():
            if r not in sem_y:
                linha.Y = (0.0 if x36 == 0 else
                           (_n(linha.X) / x36 if r == 36 else abs(_n(linha.X) / x36)))
            if r <= 93 and r not in (95, 97, 99):
                if r in desvio_menos_um:
                    linha.AB = 0.0 if _n(linha.X) == 0 else _n(linha.T) / _n(linha.X) - 1
                else:
                    linha.AB = (0.0 if _n(linha.X) == 0 else _n(linha.T) / _n(linha.X)) * -1
        self.linhas[101].AB = 0.0
        # Verificação da própria planilha (colunas FS:FV)
        for linha in self.linhas.values():
            realizado, projetado = self.soma_ate(linha.tl), self.soma_apos(linha.tl)
            linha.extras.update({
                "FS": realizado, "FV": projetado,
                "FT": "OK!" if arredondar(realizado - _n(linha.H), 2) == 0 else "ERRO",
                "FU": "OK!" if arredondar(projetado - _n(linha.P), 2) == 0 else "ERRO"})

    def calcular(self) -> dict:
        self.receitas()
        self.custos_e_despesas()
        self.resultado()
        self.socios()
        self.saldo_banco()
        self.derivadas()
        return {
            "datas": {"mes_analise": self.d22, "mes_atual": self.h21, "corte": self.ai23},
            "titulos": {"ate": f"ATÉ {texto_mes(self.d22).upper()}",
                        "realizado": f"Realizado até {texto_mes(self.d22)[:4]}{str(self.d22.year)[2:]}"},
            "meses": self.meses,
            "linhas": [self.linhas[r] for r in sorted(self.linhas)],
        }


def calcular_painel(base: Base, hoje: date, viabilidade: dict[str, float],
                    premissas: Premissas) -> dict:
    return _Painel(base, hoje, viabilidade, premissas).calcular()

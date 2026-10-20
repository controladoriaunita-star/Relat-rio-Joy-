"""Aba Dashboards: séries dos gráficos, com as mesmas definições do Resumo, Painel e Projeção.

  * Exposição de caixa: linha do tempo do Painel — saldo de caixa do mês (linha 93) e o
    acumulado (linha 95 = soma corrida da 93); realizado até o mês de corte, projetado depois.
  * Recebimentos: direto das fontes, pelo fim de mês, com as definições do Painel (106 e 112)
    e da receita do Resumo (Z6).
  * Gasto × projetado e setores: projeção de cada setor × base de custos (Custos SPE e NN's,
    pago + a pagar) nas rubricas das linhas do setor, pelo fim de mês — a mesma regra da tela
    Projeção › Projetado × Incorrido.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from ..config import CLIENTE_INVESTIDOR, EMPRESA_SPE, HISTORICO_APORTE_INVESTIDOR
from ..excel_funcoes import DATA_ZERO, chave_texto, eomonth, texto_igual
from .base import Base
from .resumo import CLASSIFICACOES_APORTE


def _n(v) -> float:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def pontos_exposicao(meses: list[date], mensal: list[float], acumulado: list[float]) -> dict:
    """Pontos do gráfico de exposição de caixa (A, B, C e D da curva clássica).

    A: investimento inicial (acumulado no primeiro mês com movimento);
    B: máxima exposição (menor acumulado);
    C: primeiro fluxo de caixa positivo depois de B;
    D: ponto de equilíbrio (acumulado volta a ser >= 0 depois de B).
    C e D ficam None quando não ocorrem no horizonte.
    """
    ponto = lambda i: {"mes": meses[i], "valor": acumulado[i]} if i is not None else None
    inicio = next((i for i, v in enumerate(mensal) if v), None)
    if inicio is None:
        return {"A": None, "B": None, "C": None, "D": None}
    b = min(range(inicio, len(acumulado)), key=lambda i: (acumulado[i], i))
    c = next((i for i in range(b + 1, len(mensal)) if mensal[i] > 0), None)
    d = next((i for i in range(b + 1, len(acumulado)) if acumulado[i] >= 0), None) if acumulado[b] < 0 else None
    return {"A": ponto(inicio), "B": ponto(b), "C": ponto(c), "D": ponto(d)}


def exposicao_de_caixa(painel: dict) -> dict:
    linhas = {l.linha_excel: l for l in painel["linhas"]}
    meses = painel["meses"]
    mensal = [_n(v) for v in linhas[93].tl]
    acumulado = [_n(v) for v in linhas[95].tl]
    usados = [i for i, v in enumerate(mensal) if v]
    if not usados:
        return {"serie": [], "pontos": pontos_exposicao(meses, mensal, acumulado), "corte": painel["datas"]["corte"]}
    ini, fim = usados[0], usados[-1]
    return {"serie": [{"mes": meses[i], "mensal": mensal[i], "acumulado": acumulado[i]} for i in range(ini, fim + 1)],
            "pontos": pontos_exposicao(meses, mensal, acumulado), "corte": painel["datas"]["corte"]}


def recebimentos(base: Base, ate: date) -> list[dict]:
    """Recebimentos por mês, direto das fontes e pelo fim de mês, até o mês corrente:
    investidor = Recebidas do investidor + entradas "Aporte" do investidor (Painel 106);
    holding = transferências para a SPE + entradas "Aporte Holding" (Painel 112);
    receitas = entradas que não são aporte (Resumo Z6)."""
    por_mes = defaultdict(lambda: {"investidor": 0.0, "holding": 0.0, "receitas": 0.0})
    for r in base.recebidas:
        if r.cliente == CLIENTE_INVESTIDOR:
            por_mes[r.fim_mes]["investidor"] += r.valor
    for t in base.transferencias:
        if t.empresa != EMPRESA_SPE and t.empresa_credito == EMPRESA_SPE:
            por_mes[t.fim_mes]["holding"] += t.valor
    for e in base.entradas:
        classe = chave_texto((e.classificacao or "").strip())
        if classe == chave_texto("Aporte") and texto_igual(e.historico, HISTORICO_APORTE_INVESTIDOR):
            por_mes[e.fim_mes]["investidor"] += e.valor
        elif classe == chave_texto("Aporte Holding"):
            por_mes[e.fim_mes]["holding"] += e.valor
        elif classe not in CLASSIFICACOES_APORTE:
            por_mes[e.fim_mes]["receitas"] += e.valor
    meses = sorted(m for m in por_mes if m <= ate and m > DATA_ZERO)
    if not meses:
        return []
    todos, m = [], meses[0]
    while m <= ate:                                   # meses sem movimento entram zerados
        todos.append({"mes": m, **por_mes.get(m, {"investidor": 0.0, "holding": 0.0, "receitas": 0.0})})
        m = eomonth(m, 1)
    return todos


def gasto_por_setor(base: Base, setores: list[dict], projecoes: list[dict]) -> dict:
    """Projetado e incorrido (pago / a pagar) por setor e mês.

    Cada rubrica conta para um único setor (o primeiro, pela ordem) para não somar o mesmo
    custo duas vezes.
    """
    setor_da_rubrica = {}
    for s in setores:
        for l in s["linhas"]:
            setor_da_rubrica.setdefault(chave_texto(l["rubrica"]), s["codigo"])
    linha_setor = {l["id"]: s["codigo"] for s in setores for l in s["linhas"]}
    dados = defaultdict(lambda: defaultdict(lambda: {"projetado": 0.0, "pago": 0.0, "a_pagar": 0.0}))
    for p in projecoes:
        codigo = linha_setor.get(p["linha_id"])
        if codigo:
            dados[codigo][date.fromisoformat(p["mes"])]["projetado"] += p["valor"]
    for fonte in ("custos_spe", "custos_nn"):
        for d in getattr(base, fonte):
            codigo = setor_da_rubrica.get(chave_texto(d.classificacao))
            if codigo:
                campo = "pago" if texto_igual(d.status, "Pago") else "a_pagar"
                dados[codigo][d.fim_mes][campo] += d.valor
    meses = sorted({m for por_mes in dados.values() for m in por_mes})
    return {
        "setores": [{"codigo": s["codigo"], "nome": s["nome"]} for s in setores],
        "meses": meses,
        "valores": {s["codigo"]: [{"mes": m, **dados[s["codigo"]][m],
                                   "incorrido": dados[s["codigo"]][m]["pago"] + dados[s["codigo"]][m]["a_pagar"]}
                                  for m in meses] for s in setores},
        "inicio_projecao": min((date.fromisoformat(p["mes"]) for p in projecoes), default=None),
    }


def custos_por_rubrica(resumo: dict) -> list[dict]:
    return [{"rubrica": l["rubrica"], "grupo": l["grupo"], "viabilidade": l.get("viabilidade", 0),
             "pago": _n(l.get("pago_ate")) + _n(l.get("pago_mes")), "a_pagar": _n(l.get("a_pagar"))}
            for l in resumo["linhas"] if l["grupo"] in ("despesa", "custo")]

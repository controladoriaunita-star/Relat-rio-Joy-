"""Converte as tabelas brutas (cabeçalho + linhas) nos registros do motor.

Reproduz as colunas calculadas da planilha: Fim mês (EOMONTH), Concat e a
Classificação buscada no DePara pelo Concat (macro Atualizar_DePara).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..excel_funcoes import como_data, como_numero, eomonth, texto_concat
from ..motor.base import Desembolso, Movimento, Recebimento, Transferencia
from .definicoes import FONTES_POR_CODIGO, Fonte


@dataclass
class ResultadoFonte:
    registros: list = field(default_factory=list)
    pendentes: list[dict] = field(default_factory=list)    # linhas sem classificação
    colunas_ausentes: list[str] = field(default_factory=list)
    linhas_lidas: int = 0


def tabela_para_dicts(valores: list[list]) -> list[dict]:
    """[[cabeçalho...], [linha...], ...] → lista de dicts; ignora linhas totalmente vazias."""
    if not valores:
        return []
    cabecalho = [str(c).strip() if c is not None else "" for c in valores[0]]
    linhas = []
    for linha in valores[1:]:
        if all(v is None or v == "" for v in linha):
            continue
        linhas.append(dict(zip(cabecalho, linha)))
    return linhas


def chave_concat(fonte: Fonte, linha: dict) -> str:
    return " - ".join(texto_concat(linha.get(c)) for c in fonte.chave)


def montar_depara(pares) -> dict[str, str]:
    """(concat, classificação) → dict de busca. Como o MATCH do Excel: ignora caixa
    e vale a primeira ocorrência."""
    depara: dict[str, str] = {}
    for concat, classificacao in pares:
        if concat is None or classificacao in (None, ""):
            continue
        depara.setdefault(texto_concat(concat).casefold(), str(classificacao))
    return depara


def _inteiro(valor) -> int | None:
    if valor is None or valor == "":
        return None
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None


def _texto(valor) -> str | None:
    return None if valor is None else str(valor)


def normalizar(codigo: str, linhas: list[dict], depara: dict[str, str]) -> ResultadoFonte:
    fonte = FONTES_POR_CODIGO[codigo]
    resultado = ResultadoFonte(linhas_lidas=len(linhas))
    if linhas:
        resultado.colunas_ausentes = [c for c in fonte.colunas if c not in linhas[0]]
    if resultado.colunas_ausentes:
        return resultado

    for linha in linhas:
        classificacao = None
        if fonte.chave:
            concat = chave_concat(fonte, linha)
            classificacao = depara.get(concat.casefold()) or _texto(linha.get("Classificação")) or None
            if classificacao is None:
                resultado.pendentes.append({"concat": concat, **{c: linha.get(c) for c in fonte.colunas}})
                continue          # na planilha a linha daria #N/A; aqui fica pendente

        if codigo in ("custos_spe", "custos_nn"):
            data = como_data(linha["DataPagamento"])
            registro = Desembolso(classificacao, _texto(linha["Status"]), data, eomonth(data),
                                  como_numero(linha["TotalLiquido"]))
        elif codigo in ("saidas", "entradas"):
            data = como_data(linha["Data_es"])
            registro = Movimento(classificacao, data, eomonth(data), como_numero(linha["Valor_es"]),
                                 _texto(linha.get("HistLanc_es")))
        elif codigo == "transferencias":
            registro = Transferencia(_inteiro(linha["Empresa_tb"]), _inteiro(linha["EmpresaCred_tb"]),
                                     eomonth(como_data(linha["Data_tb"])), como_numero(linha["Valor_tb"]))
        else:
            registro = Recebimento(_inteiro(linha["CódigoCliente"]),
                                   eomonth(como_data(linha["Data_Recebimento"])),
                                   como_numero(linha["Valor_Líquido"]))
        resultado.registros.append(registro)
    return resultado

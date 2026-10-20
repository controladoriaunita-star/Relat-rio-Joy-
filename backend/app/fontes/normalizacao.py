"""Converte as tabelas brutas (cabeçalho + linhas) nos registros do motor.

Reproduz as colunas calculadas da planilha: Fim mês (EOMONTH), Concat e a
Classificação buscada no DePara pelo Concat (macro Atualizar_DePara).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..excel_funcoes import como_data, como_numero, eomonth, texto_concat
from ..motor.base import Desembolso, Movimento, Recebimento, SaldoConta, Transferencia
from .definicoes import FONTES_POR_CODIGO, Fonte


@dataclass
class ResultadoFonte:
    registros: list = field(default_factory=list)
    pendentes: list[dict] = field(default_factory=list)    # linhas sem classificação
    ignoradas: int = 0                                      # linhas fora da tabela (totais, notas)
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


COLUNAS_DE_VALOR = {"TotalLiquido", "Valor_es", "Valor_tb", "Valor_Líquido", "Saldo"}


def _vazio(valor) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def fora_da_tabela(fonte: Fonte, linha: dict) -> bool:
    """O usedRange do SharePoint traz o que estiver abaixo da tabela (linha de total, notas).
    Linha sem nenhum identificador (empresa, número, data...) não é lançamento."""
    return all(_vazio(linha.get(c)) for c in fonte.colunas if c not in COLUNAS_DE_VALOR)


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
        if fora_da_tabela(fonte, linha):
            resultado.ignoradas += 1
            continue
        classificacao = concat = None
        if fonte.chave:
            concat = chave_concat(fonte, linha)
            classificacao = depara.get(concat.casefold()) or _texto(linha.get("Classificação")) or None
            if classificacao is None:
                resultado.pendentes.append({"concat": concat, **{c: linha.get(c) for c in fonte.colunas}})
                continue          # na planilha a linha daria #N/A; aqui fica pendente

        if codigo in ("custos_spe", "custos_nn"):
            data = como_data(linha["DataPagamento"])
            registro = Desembolso(classificacao, _texto(linha["Status"]), data, eomonth(data),
                                  como_numero(linha["TotalLiquido"]), _texto(linha.get("Fornecedor")),
                                  _texto(linha.get("Insumo")), concat)
        elif codigo in ("saidas", "entradas"):
            data = como_data(linha["Data_es"])
            registro = Movimento(classificacao, data, eomonth(data), como_numero(linha["Valor_es"]),
                                 _texto(linha.get("HistLanc_es")))
        elif codigo == "transferencias":
            registro = Transferencia(_inteiro(linha["Empresa_tb"]), _inteiro(linha["EmpresaCred_tb"]),
                                     eomonth(como_data(linha["Data_tb"])), como_numero(linha["Valor_tb"]))
        elif codigo == "saldos":
            registro = SaldoConta(_inteiro(linha["Empresa"]), _texto(linha["Conta"]),
                                  como_data(linha["Data"]), como_numero(linha["Saldo"]))
        else:
            registro = Recebimento(_inteiro(linha["CódigoCliente"]),
                                   eomonth(como_data(linha["Data_Recebimento"])),
                                   como_numero(linha["Valor_Líquido"]))
        resultado.registros.append(registro)
    return resultado

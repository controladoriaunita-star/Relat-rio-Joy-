"""As sete tabelas de origem (APIs do Graph) e como cada uma chega ao motor."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fonte:
    codigo: str
    titulo: str
    aba_graph: str               # nome da planilha na pasta de trabalho do SharePoint
    aba_excel: str               # nome da aba no Controle - Joy+ Evans.xlsm
    tabela_excel: str            # nome da tabela (ListObject) no .xlsm
    colunas: tuple[str, ...]     # colunas obrigatórias para o cálculo
    chave: tuple[str, ...] = ()  # colunas do Concat usado pelo DePara (vazio = sem classificação)
    tabela_depara: str | None = None


FONTES = [
    Fonte("custos_spe", "Custos SPE", "Custos SPE", "Custos SPE", "Custos_SPE",
          ("Empresa", "Obra", "NProcesso", "DataPagamento", "TotalLiquido", "Status"),
          ("Empresa", "Obra", "NProcesso"), "Tabela10"),
    Fonte("custos_nn", "Custos NN's", "Custos NN", "Custos_NN's", "BD_NN_s",
          ("Empresa", "Obra", "NProcesso", "DocFiscal", "DataPagamento", "TotalLiquido", "Status"),
          ("Empresa", "Obra", "NProcesso", "DocFiscal"), "Tabela11"),
    Fonte("saidas", "Controle Saídas", "Controle Saídas", "Controle Saídas", "Controle_Saídas",
          ("Empresa_es", "Num_es", "Data_es", "Valor_es"), ("Empresa_es", "Num_es"), "Tabela12"),
    Fonte("entradas", "Controle Entradas", "Controle Entradas", "Controle Entradas",
          "Controle_Entradas", ("Empresa_es", "Num_es", "Data_es", "Valor_es", "HistLanc_es"),
          ("Empresa_es", "Num_es"), "Tabela13"),
    Fonte("transferencias", "Transferências Bancárias", "Transferências Bancarias",
          "Transferência Bancária", "bd_transferênciaBancária",
          ("Empresa_tb", "EmpresaCred_tb", "Data_tb", "Valor_tb")),
    Fonte("recebidas", "Recebidas", "Recebidas", "Recebidos", "Recebidas",
          ("CódigoCliente", "Data_Recebimento", "Valor_Líquido")),
    Fonte("saldos", "Saldos bancários", "Saldo", "Saldo", "Consulta2",
          ("Empresa", "Data", "Conta", "Saldo")),
]
FONTES_POR_CODIGO = {f.codigo: f for f in FONTES}

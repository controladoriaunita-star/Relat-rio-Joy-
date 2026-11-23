"""Obras (empreendimentos): o que muda de uma obra para outra.

As fórmulas, as telas e o login são os mesmos para todas as obras. Cada obra tem
o próprio arquivo de dados no SharePoint (mesmas abas, mesmo fluxo de API), a
identificação da SPE usada pelas fórmulas e os próprios dados no banco
(parâmetros, DePara, cargas, setores e projeções, todos com a coluna `obra`).
Uma obra nova é cadastrada pela tela (API's › Obras), sem mudar código.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .config import RAIZ_PROJETO


@dataclass(frozen=True)
class Obra:
    codigo: str                                   # identificador na URL e no banco (ex.: "evans")
    nome: str                                     # nome exibido (ex.: "Evans")
    empresa_spe: int | None = None                # código da SPE no UAU (Evans 73, Berrini 67)
    cliente_investidor: int | None = None         # Recebidas[CódigoCliente] que é aporte do investidor
    historico_aporte_investidor: str | None = None   # Controle Entradas[HistLanc_es] do aporte
    graph_item_id: str | None = None              # arquivo "BD´s_JOY_<OBRA>" na pasta 06 - API
    arquivo_excel: str | None = None              # planilha de controle local (carga inicial e regressão)
    # Nome da aba no arquivo do SharePoint, só quando difere do padrão do arquivo da Evans
    # (fonte → aba). Ex.: {"recebidas": "Recebidos"}.
    abas: dict[str, str] = field(default_factory=dict, hash=False, compare=False)
    ordem: int = 0
    ativo: bool = True

    def aba(self, fonte) -> str:
        """Aba do SharePoint de uma fonte nesta obra."""
        return self.abas.get(fonte.codigo) or fonte.aba_graph

    @property
    def caminho_excel(self) -> Path | None:
        return RAIZ_PROJETO / self.arquivo_excel if self.arquivo_excel else None

    def como_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, dados: dict) -> "Obra":
        validos = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in dados.items() if k in validos})


CODIGO_VALIDO = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")

# Carga inicial. Os valores ficam no banco e são editados pela tela.
OBRAS_PADRAO = [
    Obra("evans", "Evans", empresa_spe=73, cliente_investidor=8213,
         historico_aporte_investidor="APORTE Bapema Kalil Evans I Spe Ltda",
         graph_item_id="01UQIHIUUULNCLXTBFYFBJU2OHULC6J4JV",
         arquivo_excel="Controle - Joy+ Evans.xlsm", ordem=0),
    # Cliente investidor e histórico do aporte da Berrini ainda não foram definidos
    # (a planilha dela ainda traz os da Evans nas fórmulas). O arquivo do SharePoint dela
    # usa os nomes de aba da planilha de controle em três fontes.
    Obra("berrini", "Berrini", empresa_spe=67,
         graph_item_id="01UQIHIUS2VNXRZMM4HRAIZUPOG3JFPH7A",
         arquivo_excel="Controle - Joy+ Berrini.xlsm",
         abas={"custos_nn": "Custos_NN's", "transferencias": "Transferência Bancária", "recebidas": "Recebidos"},
         ordem=1),
]
OBRA_PADRAO = OBRAS_PADRAO[0].codigo

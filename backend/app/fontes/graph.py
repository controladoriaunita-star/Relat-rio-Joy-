"""Leitura das planilhas de origem no SharePoint via Microsoft Graph (client credentials).

Um cliente atende todas as obras: o token é do app; o arquivo (item id) vem da obra.
"""
from __future__ import annotations

import base64
import json
import time
from urllib.parse import quote

import requests

from .. import config

URL_TOKEN = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
URL_ITEM = "https://graph.microsoft.com/v1.0/drives/{drive}/items/{item}"


class ErroGraph(Exception):
    """Erro com mensagem pronta para o usuário."""


class ClienteGraph:
    def __init__(self, sessao: requests.Session | None = None):
        self._sessao = sessao or requests.Session()
        self._token: str | None = None
        self._expira = 0.0

    @staticmethod
    def configurado() -> bool:
        return all([config.GRAPH_TENANT_ID, config.GRAPH_CLIENT_ID, config.GRAPH_CLIENT_SECRET,
                    config.GRAPH_DRIVE_ID])

    def _obter_token(self) -> str:
        if self._token and time.time() < self._expira - 60:
            return self._token
        if not self.configurado():
            raise ErroGraph("Credenciais do Graph ausentes no arquivo .env.")
        resposta = self._sessao.post(URL_TOKEN.format(tenant=config.GRAPH_TENANT_ID), data={
            "client_id": config.GRAPH_CLIENT_ID, "client_secret": config.GRAPH_CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials",
        }, timeout=30)
        corpo = resposta.json()
        if resposta.status_code != 200:
            raise ErroGraph(f"Falha na autenticação do Entra ID: {corpo.get('error_description', corpo)}"[:400])
        self._token = corpo["access_token"]
        self._expira = time.time() + int(corpo.get("expires_in", 3600))
        return self._token

    def permissoes_do_token(self) -> list[str]:
        carga = self._obter_token().split(".")[1]
        carga += "=" * (-len(carga) % 4)
        return json.loads(base64.urlsafe_b64decode(carga)).get("roles") or []

    def _get(self, item: str, caminho: str, timeout: int = 120) -> requests.Response:
        if not item:
            raise ErroGraph("A obra não tem arquivo do SharePoint configurado (API's › Obras).")
        url = URL_ITEM.format(drive=config.GRAPH_DRIVE_ID, item=item) + caminho
        return self._sessao.get(url, headers={"Authorization": f"Bearer {self._obter_token()}"}, timeout=timeout)

    def _diagnostico_404(self, item: str, aba: str) -> str:
        """Diz se o problema é o arquivo (GRAPH_ITEM_ID) ou a aba, para o erro não ficar genérico."""
        arquivo = self._get(item, "?$select=name", timeout=30)
        if arquivo.status_code != 200:
            return "Arquivo não encontrado no SharePoint: confira o arquivo da obra (API's › Obras)."
        abas = self._get(item, "/workbook/worksheets?$select=name", timeout=60)
        nomes = [w["name"] for w in abas.json().get("value", [])] if abas.status_code == 200 else []
        return (f"A aba '{aba}' não existe no arquivo configurado ({arquivo.json().get('name')}). "
                + (f"Abas do arquivo: {', '.join(nomes)}. " if nomes else "")
                + "Confira o arquivo da obra (API's › Obras).")

    def ler_aba(self, item: str, aba: str) -> list[list]:
        """Valores do usedRange da aba do arquivo `item` (primeira linha = cabeçalho)."""
        literal = quote(aba.replace("'", "''"))            # OData: apóstrofo dobrado (ex.: Custos_NN's)
        resposta = self._get(item, f"/workbook/worksheets('{literal}')/usedRange(valuesOnly=true)?$select=values")
        if resposta.status_code == 200:
            return resposta.json().get("values", [])
        if resposta.status_code in (401, 403):
            sem_permissao = not self.permissoes_do_token()
            raise ErroGraph("Acesso negado pelo SharePoint. "
                            + ("O aplicativo não tem permissões de aplicativo concedidas "
                               "(Files.Read.All ou Sites.Read.All com consentimento de administrador)."
                               if sem_permissao else "Verifique o acesso do aplicativo ao site."))
        if resposta.status_code == 404:
            raise ErroGraph(self._diagnostico_404(item, aba)[:400])
        raise ErroGraph(f"Graph respondeu {resposta.status_code}: {resposta.text[:300]}")

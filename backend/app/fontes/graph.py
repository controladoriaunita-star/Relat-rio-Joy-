"""Leitura das planilhas de origem no SharePoint via Microsoft Graph (client credentials)."""
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
                    config.GRAPH_DRIVE_ID, config.GRAPH_ITEM_ID])

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

    def ler_aba(self, aba: str) -> list[list]:
        """Valores do usedRange da aba (primeira linha = cabeçalho)."""
        url = (URL_ITEM.format(drive=config.GRAPH_DRIVE_ID, item=config.GRAPH_ITEM_ID)
               + f"/workbook/worksheets('{quote(aba)}')/usedRange(valuesOnly=true)?$select=values")
        resposta = self._sessao.get(url, headers={"Authorization": f"Bearer {self._obter_token()}"},
                                    timeout=120)
        if resposta.status_code == 200:
            return resposta.json().get("values", [])
        if resposta.status_code in (401, 403):
            sem_permissao = not self.permissoes_do_token()
            raise ErroGraph("Acesso negado pelo SharePoint. "
                            + ("O aplicativo não tem permissões de aplicativo concedidas "
                               "(Files.Read.All ou Sites.Read.All com consentimento de administrador)."
                               if sem_permissao else "Verifique o acesso do aplicativo ao site."))
        if resposta.status_code == 404:
            raise ErroGraph(f"Aba '{aba}' ou arquivo não encontrado no SharePoint.")
        raise ErroGraph(f"Graph respondeu {resposta.status_code}: {resposta.text[:300]}")

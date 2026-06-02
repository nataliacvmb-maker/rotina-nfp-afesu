"""
Utilitários para ler e gravar na planilha Google Sheets de controle de campanhas.

A planilha tem a aba CAMPANHAS com colunas:
  A  Cliente | B Tipo | C Mês-Ano | D Data | E Campanha/Assunto
  F  Copy    | G Arte  | H Dados   | I Status Geral
  J  Link Drive (insumos) | K Link HTML (RD Station) | L Obs
"""

import io
import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_CAMPANHAS = "CAMPANHAS"

# Colunas (1-based → índice da API é 0-based)
COL_CLIENTE    = 1
COL_MES_ANO   = 3
COL_CAMPANHA   = 5
COL_STATUS     = 9
COL_LINK_DRIVE = 10
COL_LINK_HTML  = 11   # K — link do HTML no Drive para o RD Station

_sheets_service = None
_drive_service  = None


def _creds():
    token_path = os.environ["GOOGLE_TOKEN_PATH"]
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def _sheets():
    global _sheets_service
    if not _sheets_service:
        _sheets_service = build("sheets", "v4", credentials=_creds())
    return _sheets_service


def _drive():
    global _drive_service
    if not _drive_service:
        _drive_service = build("drive", "v3", credentials=_creds())
    return _drive_service


def encontrar_linha_campanha(spreadsheet_id: str, cliente: str, campanha_id: str) -> int | None:
    """
    Procura na aba CAMPANHAS a linha que corresponde ao cliente + mês/disparo.
    campanha_id tem formato "Jun-2026/Disparo-1".
    Retorna o número da linha (1-based) ou None.
    """
    mes_disparo = campanha_id  # ex: "Jun-2026/Disparo-1"
    mes_ano = mes_disparo.split("/")[0] if "/" in mes_disparo else mes_disparo
    disparo_nome = mes_disparo.split("/")[1] if "/" in mes_disparo else ""

    resultado = _sheets().spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET_CAMPANHAS}!A:E",
    ).execute()

    values = resultado.get("values", [])
    for i, row in enumerate(values):
        if i == 0:
            continue  # pula cabeçalho
        row_cliente   = row[0].strip().lower() if len(row) > 0 else ""
        row_mes_ano   = row[2].strip()         if len(row) > 2 else ""
        row_campanha  = row[4].strip()         if len(row) > 4 else ""

        if (row_cliente == cliente.strip().lower() and
                row_mes_ano == mes_ano and
                disparo_nome.lower() in row_campanha.lower()):
            return i + 1  # 1-based

    return None


def gravar_link_html(spreadsheet_id: str, linha: int, link_html: str):
    """Grava o link do HTML gerado na coluna K (Link HTML RD Station)."""
    _sheets().spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET_CAMPANHAS}!K{linha}",
        valueInputOption="USER_ENTERED",
        body={"values": [[f'=HYPERLINK("{link_html}","📄 Abrir HTML")']]},
    ).execute()


def gravar_link_drive(spreadsheet_id: str, linha: int, link_drive: str):
    """Grava o link da pasta Drive na coluna J (Link Drive insumos)."""
    _sheets().spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET_CAMPANHAS}!J{linha}",
        valueInputOption="USER_ENTERED",
        body={"values": [[f'=HYPERLINK("{link_drive}","📁 Pasta Drive")']]},
    ).execute()


def upload_html_para_drive(html_path: str, nome_arquivo: str, pasta_id: str) -> str:
    """
    Faz upload do arquivo HTML para a pasta do cliente no Drive.
    Retorna a URL de visualização do arquivo.
    """
    from googleapiclient.http import MediaFileUpload

    # Remove versão antiga se existir
    resultado = _drive().files().list(
        q=f"name='{nome_arquivo}' and '{pasta_id}' in parents and trashed=false",
        fields="files(id)",
    ).execute()
    for f in resultado.get("files", []):
        _drive().files().delete(fileId=f["id"]).execute()

    media = MediaFileUpload(html_path, mimetype="text/html", resumable=False)
    metadata = {"name": nome_arquivo, "parents": [pasta_id]}
    arquivo = _drive().files().create(
        body=metadata, media_body=media, fields="id,webViewLink"
    ).execute()

    return arquivo.get("webViewLink", "")


def atualizar_planilha_apos_disparo(
    spreadsheet_id: str,
    cliente_slug: str,
    campanha_id: str,
    html_path: str,
    pasta_drive_id: str,
    pasta_drive_link: str,
):
    """
    Chamado pelo email_flow.py após gerar o HTML.
    Faz upload do HTML para o Drive e grava ambos os links na planilha.
    """
    if not spreadsheet_id:
        return

    linha = encontrar_linha_campanha(spreadsheet_id, cliente_slug, campanha_id)
    if not linha:
        print(f"[sheets] ⚠ Linha não encontrada para {cliente_slug} / {campanha_id}")
        return

    # Upload do HTML para Drive
    nome_arquivo = Path(html_path).name
    try:
        link_html = upload_html_para_drive(html_path, nome_arquivo, pasta_drive_id)
        gravar_link_html(spreadsheet_id, linha, link_html)
        print(f"[sheets] ✓ HTML enviado ao Drive e link gravado na linha {linha}")
    except Exception as e:
        print(f"[sheets] ⚠ Erro no upload do HTML: {e}")

    # Grava link da pasta de insumos
    try:
        if pasta_drive_link:
            gravar_link_drive(spreadsheet_id, linha, pasta_drive_link)
    except Exception as e:
        print(f"[sheets] ⚠ Erro ao gravar link Drive: {e}")

"""
Utilitários para interação com o Google Drive.

Estrutura esperada por cliente:
  [drive_folder_id]/
    Disparos Emails/
      [Mês-Ano]/
        base/      ← planilha .xlsx ou .csv com emails
        banner/    ← imagem do banner (.jpg, .jpeg, .png)
        copy/
          roteiro.yaml

Arquivo de estado: estado_disparos.json na raiz da pasta do cliente.
"""

import io
import json
import os

import yaml
import pandas as pd
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload


SCOPES = [
    "https://www.googleapis.com/auth/drive",
]

_drive_service = None


def _service():
    global _drive_service
    if _drive_service:
        return _drive_service
    token_path = os.environ["GOOGLE_TOKEN_PATH"]
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    _drive_service = build("drive", "v3", credentials=creds)
    return _drive_service


def _listar_filhos(folder_id: str, nome_filtro: str | None = None) -> list[dict]:
    q = f"'{folder_id}' in parents and trashed = false"
    if nome_filtro:
        q += f" and name = '{nome_filtro}'"
    resp = _service().files().list(
        q=q,
        fields="files(id, name, mimeType, modifiedTime)",
        pageSize=50,
    ).execute()
    return resp.get("files", [])


def _encontrar_subpasta(folder_id: str, nome: str) -> str | None:
    filhos = _listar_filhos(folder_id, nome)
    for f in filhos:
        if f["mimeType"] == "application/vnd.google-apps.folder":
            return f["id"]
    return None


def _mes_atual() -> str:
    from datetime import datetime
    meses = {
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
    }
    hoje = datetime.today()
    return f"{meses[hoje.month]}-{hoje.year}"


def verificar_insumos(drive_folder_id: str) -> dict | None:
    """
    Verifica se base + banner + roteiro.yaml estão presentes no Drive
    para o mês atual. Retorna dict com IDs e nomes, ou None se incompleto.
    """
    mes = _mes_atual()

    disparos = _encontrar_subpasta(drive_folder_id, "Disparos Emails")
    if not disparos:
        return None

    pasta_mes = _encontrar_subpasta(disparos, mes)
    if not pasta_mes:
        return None

    pasta_base = _encontrar_subpasta(pasta_mes, "base")
    pasta_banner = _encontrar_subpasta(pasta_mes, "banner")
    pasta_copy = _encontrar_subpasta(pasta_mes, "copy")

    if not pasta_base or not pasta_banner or not pasta_copy:
        return None

    arquivos_base = [
        f for f in _listar_filhos(pasta_base)
        if any(f["name"].lower().endswith(ext) for ext in (".xlsx", ".xls", ".csv"))
    ]
    arquivos_banner = [
        f for f in _listar_filhos(pasta_banner)
        if any(f["name"].lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png"))
    ]
    arquivos_roteiro = [f for f in _listar_filhos(pasta_copy) if f["name"] == "roteiro.yaml"]

    if not arquivos_base or not arquivos_banner or not arquivos_roteiro:
        return None

    return {
        "base_id": arquivos_base[0]["id"],
        "base_nome": arquivos_base[0]["name"],
        "base_modificado": arquivos_base[0]["modifiedTime"],
        "banner_id": arquivos_banner[0]["id"],
        "banner_nome": arquivos_banner[0]["name"],
        "roteiro_id": arquivos_roteiro[0]["id"],
        "roteiro_nome": arquivos_roteiro[0]["name"],
    }


def _baixar_arquivo(file_id: str) -> bytes:
    req = _service().files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def baixar_base_emails(file_id: str) -> list[dict]:
    """Baixa planilha de emails e retorna lista de {email, name}."""
    meta = _service().files().get(fileId=file_id, fields="name").execute()
    nome = meta["name"].lower()
    conteudo = _baixar_arquivo(file_id)

    if nome.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(conteudo))
    else:
        df = pd.read_excel(io.BytesIO(conteudo))

    df.columns = [c.strip().lower() for c in df.columns]

    col_email = next((c for c in df.columns if "email" in c), None)
    col_nome = next((c for c in df.columns if c in ("nome", "name", "contato")), None)

    if not col_email:
        raise ValueError(f"Planilha sem coluna de email. Colunas encontradas: {list(df.columns)}")

    contatos = []
    for _, row in df.iterrows():
        email = str(row[col_email]).strip() if pd.notna(row[col_email]) else ""
        nome_contato = str(row[col_nome]).strip() if col_nome and pd.notna(row[col_nome]) else ""
        if "@" in email:
            contatos.append({"email": email, "name": nome_contato})

    return contatos


def baixar_banner(file_id: str) -> str:
    """Baixa imagem do banner para /tmp e retorna o caminho."""
    meta = _service().files().get(fileId=file_id, fields="name").execute()
    ext = meta["name"].rsplit(".", 1)[-1].lower()
    path = f"/tmp/banner.{ext}"
    with open(path, "wb") as f:
        f.write(_baixar_arquivo(file_id))
    return path


def baixar_roteiro(file_id: str) -> dict:
    """Baixa roteiro.yaml e retorna como dict."""
    conteudo = _baixar_arquivo(file_id)
    return yaml.safe_load(conteudo.decode("utf-8")) or {}


def ler_estado(drive_folder_id: str) -> dict:
    """Lê estado_disparos.json da pasta raiz do cliente no Drive."""
    arquivos = _listar_filhos(drive_folder_id, "estado_disparos.json")
    if not arquivos:
        return {}
    conteudo = _baixar_arquivo(arquivos[0]["id"])
    return json.loads(conteudo.decode("utf-8"))


def salvar_estado(drive_folder_id: str, estado: dict):
    """Salva/atualiza estado_disparos.json na pasta raiz do cliente."""
    conteudo = json.dumps(estado, ensure_ascii=False, indent=2).encode("utf-8")
    buf = io.BytesIO(conteudo)

    arquivos = _listar_filhos(drive_folder_id, "estado_disparos.json")
    media = MediaIoBaseUpload(buf, mimetype="application/json")

    if arquivos:
        _service().files().update(fileId=arquivos[0]["id"], media_body=media).execute()
    else:
        metadata = {"name": "estado_disparos.json", "parents": [drive_folder_id]}
        _service().files().create(body=metadata, media_body=media).execute()

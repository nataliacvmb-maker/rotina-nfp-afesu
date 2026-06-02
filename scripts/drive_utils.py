"""
Utilitários para interação com o Google Drive.

Estrutura de pastas por cliente:
  [drive_folder_id]/
    Disparos Emails/
      [Mês-Ano]/
        Disparo-1/
          base/    ← planilha .xlsx ou .csv com emails
          banner/  ← imagem do banner (.jpg, .jpeg, .png)
          copy/
            roteiro.yaml
        Disparo-2/
          base/ banner/ copy/   ← segundo email do mês

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


SCOPES = ["https://www.googleapis.com/auth/drive"]

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
    for f in _listar_filhos(folder_id, nome):
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


def _classificar_imagens_banner(arquivos: list[dict]) -> dict:
    """
    Classifica imagens da pasta banner por nome.
    Padrão esperado: logo, header, campanha/link, final.
    Retorna dict com chaves: logo, header, campanha, final — cada uma pode ser None.
    """
    imgs = [f for f in arquivos if any(f["name"].lower().endswith(e) for e in (".jpg", ".jpeg", ".png"))]

    def _match(nome: str, *palavras) -> bool:
        n = nome.lower()
        return any(p in n for p in palavras)

    resultado = {"logo": None, "header": None, "campanha": None, "final": None}
    for img in imgs:
        n = img["name"]
        if _match(n, "logo"):
            resultado["logo"] = img
        elif _match(n, "campanha", "link"):
            resultado["campanha"] = img
        elif _match(n, "final"):
            resultado["final"] = img
        elif _match(n, "header", "banner", "capa"):
            resultado["header"] = img

    return resultado


def verificar_insumos(drive_folder_id: str) -> list[dict]:
    """
    Retorna lista de disparos prontos para o mês atual.
    Estrutura de cada item inclui IDs das imagens classificadas por nome:
    logo_id, header_id, campanha_id_img, final_id — além de base e roteiro.
    """
    mes = _mes_atual()

    pasta_disparos = _encontrar_subpasta(drive_folder_id, "Disparos Emails")
    if not pasta_disparos:
        return []

    pasta_mes = _encontrar_subpasta(pasta_disparos, mes)
    if not pasta_mes:
        return []

    subpastas = [
        f for f in _listar_filhos(pasta_mes)
        if f["mimeType"] == "application/vnd.google-apps.folder"
    ]

    prontos = []
    for subpasta in sorted(subpastas, key=lambda x: x["name"]):
        disparo_id = subpasta["id"]
        disparo_nome = subpasta["name"]

        pasta_base = _encontrar_subpasta(disparo_id, "base")
        pasta_banner = _encontrar_subpasta(disparo_id, "banner")
        pasta_copy = _encontrar_subpasta(disparo_id, "copy")

        if not pasta_base or not pasta_banner or not pasta_copy:
            continue

        arquivos_base = [
            f for f in _listar_filhos(pasta_base)
            if any(f["name"].lower().endswith(ext) for ext in (".xlsx", ".xls", ".csv"))
        ]
        imagens = _classificar_imagens_banner(_listar_filhos(pasta_banner))
        arquivos_roteiro = [
            f for f in _listar_filhos(pasta_copy)
            if f["name"] == "roteiro.yaml"
        ]

        # Exige ao menos header (ou qualquer imagem principal) e roteiro
        if not arquivos_base or not arquivos_roteiro:
            continue
        if not any(imagens.values()):
            continue

        prontos.append({
            "disparo_nome": disparo_nome,
            "campanha_id": f"{mes}/{disparo_nome}",
            "base_id": arquivos_base[0]["id"],
            "base_nome": arquivos_base[0]["name"],
            # Imagens classificadas por papel
            "logo_id": imagens["logo"]["id"] if imagens["logo"] else None,
            "header_id": imagens["header"]["id"] if imagens["header"] else None,
            "campanha_img_id": imagens["campanha"]["id"] if imagens["campanha"] else None,
            "final_id": imagens["final"]["id"] if imagens["final"] else None,
            # Mantém banner_id apontando para header (retrocompatibilidade)
            "banner_id": (imagens["header"] or imagens["campanha"] or next(v for v in imagens.values() if v))["id"],
            "banner_nome": (imagens["header"] or imagens["campanha"] or next(v for v in imagens.values() if v))["name"],
            "roteiro_id": arquivos_roteiro[0]["id"],
            "roteiro_nome": arquivos_roteiro[0]["name"],
            "pasta_base_link": f"https://drive.google.com/drive/folders/{pasta_base}",
            "pasta_banner_link": f"https://drive.google.com/drive/folders/{pasta_banner}",
            "pasta_copy_link": f"https://drive.google.com/drive/folders/{pasta_copy}",
        })

    return prontos


def _baixar_arquivo(file_id: str) -> bytes:
    req = _service().files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def baixar_base_emails(file_id: str) -> list[dict]:
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
        raise ValueError(f"Planilha sem coluna de email. Colunas: {list(df.columns)}")

    contatos = []
    for _, row in df.iterrows():
        email = str(row[col_email]).strip() if pd.notna(row[col_email]) else ""
        nome_contato = str(row[col_nome]).strip() if col_nome and pd.notna(row[col_nome]) else ""
        if "@" in email:
            contatos.append({"email": email, "name": nome_contato})
    return contatos


def baixar_imagem(file_id: str, prefixo: str = "img") -> str:
    meta = _service().files().get(fileId=file_id, fields="name").execute()
    ext = meta["name"].rsplit(".", 1)[-1].lower()
    path = f"/tmp/{prefixo}.{ext}"
    with open(path, "wb") as f:
        f.write(_baixar_arquivo(file_id))
    return path


def baixar_banner(file_id: str) -> str:
    return baixar_imagem(file_id, "banner")


def baixar_imagem_opcional(file_id: str | None, prefixo: str) -> str | None:
    if not file_id:
        return None
    return baixar_imagem(file_id, prefixo)


def baixar_roteiro(file_id: str) -> dict:
    conteudo = _baixar_arquivo(file_id)
    return yaml.safe_load(conteudo.decode("utf-8")) or {}


def ler_estado(drive_folder_id: str) -> dict:
    arquivos = _listar_filhos(drive_folder_id, "estado_disparos.json")
    if not arquivos:
        return {}
    conteudo = _baixar_arquivo(arquivos[0]["id"])
    return json.loads(conteudo.decode("utf-8"))


def salvar_estado(drive_folder_id: str, estado: dict):
    conteudo = json.dumps(estado, ensure_ascii=False, indent=2).encode("utf-8")
    buf = io.BytesIO(conteudo)
    arquivos = _listar_filhos(drive_folder_id, "estado_disparos.json")
    media = MediaIoBaseUpload(buf, mimetype="application/json")
    if arquivos:
        _service().files().update(fileId=arquivos[0]["id"], media_body=media).execute()
    else:
        metadata = {"name": "estado_disparos.json", "parents": [drive_folder_id]}
        _service().files().create(body=metadata, media_body=media).execute()

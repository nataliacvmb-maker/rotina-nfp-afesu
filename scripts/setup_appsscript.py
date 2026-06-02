"""
Cria um projeto Apps Script vinculado à planilha e faz upload de todos os arquivos .gs e .html.

O projeto fica vinculado ao spreadsheet via "parentId", o que permite que o Apps Script
acesse SpreadsheetApp.getActiveSpreadsheet() e publique como webapp.

Após este script:
  1. Acesse a planilha → Extensões → Apps Script para ver o projeto criado
  2. Execute manualmente `configurarPlanilha()` no editor (primeira vez)
  3. Publique como webapp: Implantar → Nova implantação → Aplicativo da Web

Uso:
    GOOGLE_TOKEN_PATH=/tmp/google_token.json \
    SPREADSHEET_ID=1icbio-EAFvZggaQEuVvth_GCAINGLyD5WpNuGSRGaXo \
    python scripts/setup_appsscript.py
"""

import json
import os
from pathlib import Path

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import requests as http_requests


SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/script.deployments",
]

SCRIPT_API = "https://script.googleapis.com/v1"


def _creds():
    token_path = os.environ["GOOGLE_TOKEN_PATH"]
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def _auth_header(creds) -> dict:
    creds.refresh(google.auth.transport.requests.Request())
    return {"Authorization": f"Bearer {creds.token}"}


def _gs_files(apps_script_dir: Path) -> list:
    """
    Lê os arquivos .gs e .html da pasta apps_script/ e retorna a lista de objetos
    para a API de projetos do Apps Script.
    """
    order = ["Codigo", "Email", "Calendario", "Setup"]
    files = []

    for name in order:
        path = apps_script_dir / f"{name}.gs"
        if path.exists():
            files.append({
                "name": name,
                "type": "SERVER_JS",
                "source": path.read_text(encoding="utf-8"),
            })

    # Arquivo HTML do calendário
    html_path = apps_script_dir / "Calendario.html"
    if html_path.exists():
        files.append({
            "name": "Calendario",
            "type": "HTML",
            "source": html_path.read_text(encoding="utf-8"),
        })

    return files


def get_or_create_project(creds, spreadsheet_id: str) -> str:
    """
    Retorna o script_id do projeto vinculado ao spreadsheet.
    Cria um novo projeto caso não exista.
    """
    headers = _auth_header(creds)

    # Tenta buscar projeto existente vinculado ao container (não há listagem direta; tenta criar)
    resp = http_requests.post(
        f"{SCRIPT_API}/projects",
        headers={**headers, "Content-Type": "application/json"},
        json={"title": "Calendário NFP — Comunicação", "parentId": spreadsheet_id},
    )

    if resp.status_code == 200:
        script_id = resp.json()["scriptId"]
        print(f"  ✓ Projeto Apps Script criado: {script_id}")
        return script_id

    # 409 = já existe projeto vinculado
    if resp.status_code == 409:
        data = resp.json()
        # A mensagem de erro geralmente contém o scriptId existente
        print(f"  ℹ Projeto já existe. Resposta: {data}")
        # Tenta extrair scriptId da mensagem
        msg = str(data)
        if "scriptId" in msg:
            import re
            m = re.search(r'"scriptId"\s*:\s*"([^"]+)"', msg)
            if m:
                return m.group(1)

    print(f"  ⚠ Resposta inesperada ao criar projeto: {resp.status_code} — {resp.text}")
    raise RuntimeError(f"Não foi possível criar/encontrar o projeto Apps Script: {resp.text}")


def upload_files(creds, script_id: str, files: list):
    """Faz upload (PUT) de todos os arquivos no projeto."""
    headers = _auth_header(creds)

    resp = http_requests.put(
        f"{SCRIPT_API}/projects/{script_id}/content",
        headers={**headers, "Content-Type": "application/json"},
        json={"files": files},
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Erro ao fazer upload dos arquivos: {resp.status_code} — {resp.text}")

    nomes = [f["name"] for f in files]
    print(f"  ✓ {len(files)} arquivos enviados: {', '.join(nomes)}")


def main():
    spreadsheet_id = os.environ.get(
        "SPREADSHEET_ID",
        "1icbio-EAFvZggaQEuVvth_GCAINGLyD5WpNuGSRGaXo",
    )

    apps_script_dir = Path(__file__).parent / "apps_script"

    print(f"Configurando Apps Script para planilha {spreadsheet_id}...")

    creds = _creds()
    files = _gs_files(apps_script_dir)

    if not files:
        print("⚠ Nenhum arquivo .gs encontrado em scripts/apps_script/")
        return

    print(f"  Arquivos a enviar: {[f['name'] for f in files]}")

    script_id = get_or_create_project(creds, spreadsheet_id)
    upload_files(creds, script_id, files)

    print(f"\n✅ Apps Script configurado!")
    print(f"   Acesse: https://script.google.com/d/{script_id}/edit")
    print()
    print("Próximos passos:")
    print("  1. Abra o link acima e execute 'configurarPlanilha()' (uma vez)")
    print("  2. Publique como webapp: Implantar → Nova implantação → Aplicativo da Web")
    print("     Executar como: Eu  |  Acesso: Qualquer pessoa")
    print("  3. Cole a URL do webapp em config/clients.yaml (campo webapp_url) ou na aba LINKS CALENDÁRIOS")


if __name__ == "__main__":
    main()

"""
Cria um projeto Apps Script vinculado à planilha, faz upload de todos os arquivos
.gs/.html e publica automaticamente como webapp.

Uso:
    GOOGLE_TOKEN_PATH=/tmp/google_token.json \
    SPREADSHEET_ID=1icbio-EAFvZggaQEuVvth_GCAINGLyD5WpNuGSRGaXo \
    python scripts/setup_appsscript.py
"""

import json
import os
import re
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
    for html_file in sorted((apps_script_dir).glob("*.html")):
        files.append({
            "name": html_file.stem,
            "type": "HTML",
            "source": html_file.read_text(encoding="utf-8"),
        })
    return files


def get_or_create_project(creds, spreadsheet_id: str) -> str:
    headers = _auth_header(creds)

    resp = http_requests.post(
        f"{SCRIPT_API}/projects",
        headers={**headers, "Content-Type": "application/json"},
        json={"title": "Calendário NFP — Comunicação", "parentId": spreadsheet_id},
    )

    if resp.status_code == 200:
        script_id = resp.json()["scriptId"]
        print(f"  ✓ Projeto Apps Script criado: {script_id}")
        return script_id

    if resp.status_code == 409:
        data = resp.json()
        msg = json.dumps(data)
        m = re.search(r'"scriptId"\s*:\s*"([^"]+)"', msg)
        if m:
            script_id = m.group(1)
            print(f"  ℹ Projeto já existia: {script_id}")
            return script_id
        print(f"  ⚠ 409 mas não encontrei scriptId: {data}")

    raise RuntimeError(f"Não foi possível criar/encontrar o projeto Apps Script: {resp.status_code} — {resp.text}")


def upload_files(creds, script_id: str, files: list):
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


def create_or_get_deployment(creds, script_id: str) -> str:
    """
    Cria (ou reutiliza) a implantação HEAD como webapp público.
    Retorna a URL do webapp.
    """
    headers = _auth_header(creds)

    # Lista implantações existentes
    resp = http_requests.get(
        f"{SCRIPT_API}/projects/{script_id}/deployments",
        headers=headers,
    )

    if resp.status_code == 200:
        deployments = resp.json().get("deployments", [])
        for d in deployments:
            cfg = d.get("deploymentConfig", {})
            # Reutiliza implantação HEAD se já existir
            if cfg.get("versionNumber") is None:
                url = _webapp_url(d)
                if url:
                    print(f"  ℹ Implantação HEAD existente: {url}")
                    return url

    # Cria nova implantação
    body = {
        "deploymentConfig": {
            "scriptId": script_id,
            "manifestFileName": "appsscript",
            "description": "Webapp calendário NFP",
            "access": "ANYONE_ANONYMOUS",
        }
    }

    resp = http_requests.post(
        f"{SCRIPT_API}/projects/{script_id}/deployments",
        headers={**headers, "Content-Type": "application/json"},
        json=body,
    )

    if resp.status_code == 200:
        d = resp.json()
        url = _webapp_url(d)
        if url:
            print(f"  ✓ Webapp publicado: {url}")
            return url
        deployment_id = d.get("deploymentId", "")
        print(f"  ✓ Implantação criada (ID {deployment_id}) — veja detalhes no Apps Script")
        return f"https://script.google.com/macros/s/{deployment_id}/exec"

    print(f"  ⚠ Erro ao criar implantação: {resp.status_code} — {resp.text}")
    print("  → Publique manualmente: Apps Script → Implantar → Nova implantação → Aplicativo da Web")
    return ""


def _webapp_url(deployment: dict) -> str:
    for ep in deployment.get("entryPoints", []):
        if ep.get("entryPointType") == "WEB_APP":
            return ep.get("webAppEntryPoint", {}).get("url", "")
    return ""


def atualizar_links_calendario(spreadsheet_id: str, creds, clientes: list, webapp_url: str):
    """
    Preenche a coluna 'Link Calendário HTML' na aba LINKS CALENDÁRIOS para cada cliente.
    """
    if not webapp_url:
        return

    from googleapiclient.discovery import build
    svc = build("sheets", "v4", credentials=creds)

    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_id = None
    for sh in meta.get("sheets", []):
        if sh["properties"]["title"] == "LINKS CALENDÁRIOS":
            sheet_id = sh["properties"]["sheetId"]
            break
    if sheet_id is None:
        print("  ⚠ Aba 'LINKS CALENDÁRIOS' não encontrada")
        return

    # Lê slugs e linhas existentes
    result = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="LINKS CALENDÁRIOS!A:C",
    ).execute()
    rows = result.get("values", [])

    updates = []
    for i, row in enumerate(rows):
        if i == 0:
            continue
        if not row:
            continue
        slug = row[0].strip() if row else ""
        if not slug:
            continue
        url = f"{webapp_url}?cliente={slug}"
        updates.append({
            "range": f"LINKS CALENDÁRIOS!C{i + 1}",
            "values": [[url]],
        })

    if updates:
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": updates},
        ).execute()
        print(f"  ✓ {len(updates)} URLs de calendário gravadas na aba LINKS CALENDÁRIOS")
    else:
        print("  ⚠ Nenhuma linha encontrada em LINKS CALENDÁRIOS para preencher")


def main():
    import yaml

    spreadsheet_id = os.environ.get(
        "SPREADSHEET_ID",
        "1icbio-EAFvZggaQEuVvth_GCAINGLyD5WpNuGSRGaXo",
    )

    apps_script_dir = Path(__file__).parent / "apps_script"
    config_path = Path(__file__).parent.parent / "config" / "clients.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    clientes = config.get("clients", [])

    print(f"Configurando Apps Script para planilha {spreadsheet_id}...")

    creds = _creds()
    files = _gs_files(apps_script_dir)

    if not files:
        print("⚠ Nenhum arquivo .gs encontrado em scripts/apps_script/")
        return

    print(f"  Arquivos a enviar: {[f['name'] for f in files]}")

    script_id = get_or_create_project(creds, spreadsheet_id)
    upload_files(creds, script_id, files)

    print("\nPublicando webapp...")
    webapp_url = create_or_get_deployment(creds, script_id)

    if webapp_url:
        print(f"\nPreenchendo aba LINKS CALENDÁRIOS...")
        atualizar_links_calendario(spreadsheet_id, creds, clientes, webapp_url)

    print(f"\n✅ Apps Script configurado!")
    print(f"   Editor: https://script.google.com/d/{script_id}/edit")
    if webapp_url:
        print(f"   Webapp: {webapp_url}")
        print(f"   Calendário Afesu: {webapp_url}?cliente=afesu")
    else:
        print("   ⚠ Publique o webapp manualmente no editor acima")

    print()
    print("Passo final: abra o editor do Apps Script e execute 'configurarPlanilha()' uma vez")


if __name__ == "__main__":
    main()

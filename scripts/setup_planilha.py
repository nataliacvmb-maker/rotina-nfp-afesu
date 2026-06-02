"""
Configura a planilha Google Sheets "Calendário NFP — Comunicação".

Cria e formata as 3 abas (CAMPANHAS, CLIENTES, LINKS CALENDÁRIOS),
preenche cabeçalhos, larguras, validações e dados iniciais dos clientes.

Uso:
    GOOGLE_TOKEN_PATH=/tmp/google_token.json \
    SPREADSHEET_ID=1icbio-EAFvZggaQEuVvth_GCAINGLyD5WpNuGSRGaXo \
    python scripts/setup_planilha.py
"""

import os
import yaml
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _creds():
    token_path = os.environ["GOOGLE_TOKEN_PATH"]
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def _sheets(creds):
    return build("sheets", "v4", credentials=creds)


def _hex_to_rgb(hex_color: str) -> dict:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return {"red": r / 255, "green": g / 255, "blue": b / 255}


def _header_format(hex_bg: str = "#2C3E50") -> dict:
    return {
        "backgroundColor": _hex_to_rgb(hex_bg),
        "textFormat": {
            "foregroundColor": {"red": 1, "green": 1, "blue": 1},
            "bold": True,
            "fontSize": 11,
        },
        "verticalAlignment": "MIDDLE",
        "horizontalAlignment": "CENTER",
        "wrapStrategy": "CLIP",
    }


def ensure_sheet(svc, spreadsheet_id: str, title: str) -> int:
    """Returns sheetId for the given title, creating it if needed."""
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sh in meta.get("sheets", []):
        if sh["properties"]["title"] == title:
            return sh["properties"]["sheetId"]

    resp = svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
    ).execute()
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def delete_default_sheet(svc, spreadsheet_id: str):
    """Removes 'Plan1' / 'Sheet1' if it still exists."""
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sh in meta.get("sheets", []):
        t = sh["properties"]["title"]
        if t in ("Plan1", "Sheet1", "Página1"):
            svc.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"deleteSheet": {"sheetId": sh["properties"]["sheetId"]}}]},
            ).execute()
            print(f"  ✓ Aba padrão '{t}' removida")
            return


def setup_campanhas(svc, spreadsheet_id: str, sheet_id: int):
    headers = [
        "Cliente", "Tipo", "Mês-Ano", "Data Planejada",
        "Campanha / Assunto",
        "Copy", "Arte", "Dados", "Status Geral",
        "Link Drive (insumos)", "Link HTML (RD Station)", "Observações",
    ]
    widths = [100, 110, 90, 120, 260, 60, 60, 60, 180, 200, 200, 200]

    col_widths_req = [
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": w},
            "fields": "pixelSize",
        }}
        for i, w in enumerate(widths)
    ]

    requests = [
        # Freeze row 1 + col 1
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 1}},
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }},
        # Row 1 height = 36px
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 36},
            "fields": "pixelSize",
        }},
        # Write header values
        {"updateCells": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": len(headers)},
            "rows": [{"values": [
                {"userEnteredValue": {"stringValue": h}, "userEnteredFormat": _header_format()}
                for h in headers
            ]}],
            "fields": "userEnteredValue,userEnteredFormat",
        }},
        # Tipo dropdown (col B = index 1), rows 2–500
        {"setDataValidation": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 500,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": v} for v in ["email", "instagram", "whatsapp", "sms", "outros"]],
                },
                "showCustomUi": True,
                "strict": True,
            },
        }},
        # Center align: Copy/Arte/Dados/Status (cols F-I = 5-8)
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 500,
                      "startColumnIndex": 5, "endColumnIndex": 9},
            "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
            "fields": "userEnteredFormat.horizontalAlignment",
        }},
        # Date format for col D (index 3)
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 500,
                      "startColumnIndex": 3, "endColumnIndex": 4},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "dd/MM/yyyy"}}},
            "fields": "userEnteredFormat.numberFormat",
        }},
        # Conditional format: Status "Pronto" → green (col I = index 8)
        {"addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 500,
                            "startColumnIndex": 8, "endColumnIndex": 9}],
                "booleanRule": {
                    "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "Pronto"}]},
                    "format": {
                        "backgroundColor": _hex_to_rgb("#D1FAE5"),
                        "textFormat": {"foregroundColor": _hex_to_rgb("#065F46"), "bold": True},
                    },
                },
            },
            "index": 0,
        }},
        # Conditional format: Status "Bloqueado" → red
        {"addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 500,
                            "startColumnIndex": 8, "endColumnIndex": 9}],
                "booleanRule": {
                    "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "Bloqueado"}]},
                    "format": {
                        "backgroundColor": _hex_to_rgb("#FEE2E2"),
                        "textFormat": {"foregroundColor": _hex_to_rgb("#991B1B"), "bold": True},
                    },
                },
            },
            "index": 1,
        }},
        # Conditional format: Status "andamento" → yellow
        {"addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 500,
                            "startColumnIndex": 8, "endColumnIndex": 9}],
                "booleanRule": {
                    "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "andamento"}]},
                    "format": {
                        "backgroundColor": _hex_to_rgb("#FEF3C7"),
                        "textFormat": {"foregroundColor": _hex_to_rgb("#92400E")},
                    },
                },
            },
            "index": 2,
        }},
    ] + col_widths_req

    svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()
    print("  ✓ Aba CAMPANHAS configurada")


def setup_clientes(svc, spreadsheet_id: str, sheet_id: int, clientes: list):
    headers = ["Slug", "Nome Completo", "Email Operador", "Email Copy", "Email Arte", "Email Dados", "Email Aprovador"]
    widths = [110, 200, 240, 230, 230, 230, 230]

    rows_data = []
    for c in clientes:
        rows_data.append([
            c.get("slug", ""),
            c.get("name", ""),
            c.get("operador_email", ""),
            c.get("copy_email", ""),
            c.get("criacao_email", ""),
            "",  # email_dados — não mapeado no clients.yaml
            c.get("approver_email", ""),
        ])

    col_widths_req = [
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": w},
            "fields": "pixelSize",
        }}
        for i, w in enumerate(widths)
    ]

    data_rows = [
        {"values": [{"userEnteredValue": {"stringValue": str(v)}} for v in row]}
        for row in rows_data
    ]

    requests = [
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }},
        {"updateCells": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": len(headers)},
            "rows": [{"values": [
                {"userEnteredValue": {"stringValue": h}, "userEnteredFormat": _header_format()}
                for h in headers
            ]}],
            "fields": "userEnteredValue,userEnteredFormat",
        }},
        {"updateCells": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1 + len(data_rows),
                      "startColumnIndex": 0, "endColumnIndex": len(headers)},
            "rows": data_rows,
            "fields": "userEnteredValue",
        }},
    ] + col_widths_req

    svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()
    print(f"  ✓ Aba CLIENTES configurada com {len(rows_data)} clientes")


def setup_links(svc, spreadsheet_id: str, sheet_id: int, clientes: list):
    headers = ["Cliente (slug)", "Nome Completo", "Link Calendário HTML", "Link Pasta Drive", "Observações"]
    widths = [120, 200, 380, 300, 200]

    rows_data = []
    for c in clientes:
        rows_data.append([c.get("slug", ""), c.get("name", ""), "", "", ""])

    col_widths_req = [
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": w},
            "fields": "pixelSize",
        }}
        for i, w in enumerate(widths)
    ]

    requests = [
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }},
        {"updateCells": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": len(headers)},
            "rows": [{"values": [
                {"userEnteredValue": {"stringValue": h}, "userEnteredFormat": _header_format()}
                for h in headers
            ]}],
            "fields": "userEnteredValue,userEnteredFormat",
        }},
        {"updateCells": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1 + len(rows_data),
                      "startColumnIndex": 0, "endColumnIndex": len(headers)},
            "rows": [
                {"values": [{"userEnteredValue": {"stringValue": str(v)}} for v in row]}
                for row in rows_data
            ],
            "fields": "userEnteredValue",
        }},
        # Italic + grey for Link Calendário column placeholder text
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1 + len(rows_data),
                      "startColumnIndex": 2, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {
                "textFormat": {
                    "italic": True,
                    "foregroundColor": {"red": 0.67, "green": 0.67, "blue": 0.67},
                },
            }},
            "fields": "userEnteredFormat.textFormat",
        }},
    ] + col_widths_req

    svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()
    print(f"  ✓ Aba LINKS CALENDÁRIOS configurada com {len(rows_data)} entradas")


def main():
    spreadsheet_id = os.environ.get(
        "SPREADSHEET_ID",
        "1icbio-EAFvZggaQEuVvth_GCAINGLyD5WpNuGSRGaXo",
    )

    config_path = Path(__file__).parent.parent / "config" / "clients.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    clientes = config.get("clients", [])

    print(f"Configurando planilha {spreadsheet_id} com {len(clientes)} clientes...")

    creds = _creds()
    svc = _sheets(creds)

    # Remove aba padrão vazia se existir
    delete_default_sheet(svc, spreadsheet_id)

    # Cria/garante abas
    id_campanhas = ensure_sheet(svc, spreadsheet_id, "CAMPANHAS")
    id_clientes  = ensure_sheet(svc, spreadsheet_id, "CLIENTES")
    id_links     = ensure_sheet(svc, spreadsheet_id, "LINKS CALENDÁRIOS")

    setup_campanhas(svc, spreadsheet_id, id_campanhas)
    setup_clientes(svc, spreadsheet_id, id_clientes, clientes)
    setup_links(svc, spreadsheet_id, id_links, clientes)

    print(f"\n✅ Planilha configurada com sucesso!")
    print(f"   https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")


if __name__ == "__main__":
    main()

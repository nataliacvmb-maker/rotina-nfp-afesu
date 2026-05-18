"""
Executa no dia 20 de cada mês.
1. Roda a análise completa (baixa CSVs, faz o join, calcula métricas)
2. Sobe o relatório HTML para o Drive com o nome correto
3. Gera PDF e sobe para a pasta Histórico NFP
4. Envia email para a equipe com o link
"""
import datetime
import io
import os
import subprocess
import sys
import warnings
warnings.filterwarnings("ignore")

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

TOKEN_PATH       = "/Users/lucasbarros/rotina-nfp/token.json"
RELATORIO_LOCAL  = "/Users/lucasbarros/rotina-nfp/relatorio_atual.html"
RELATORIO_PASTA  = "1DaZee1KevxWcrC3hvwokpxgUKJQwla9s"
HISTORICO_PASTA  = "1_LEXZPzLHoYlArvsZgpeQlI9abj1inoW"

MESES_PT = {
    1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
    7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro",
}

# Defasagem de 4 meses: os arquivos disponíveis no SEFAZ são do mês M-4
hoje    = datetime.date.today()
mes_ref = hoje.month - 4
if mes_ref <= 0:
    mes_ref += 12
    ano_ref = hoje.year - 1
else:
    ano_ref = hoje.year

nome_arquivo = f"{mes_ref:02d}.{ano_ref}_Estudo NFP - AFESU"
pdf_local    = f"/Users/lucasbarros/rotina-nfp/{nome_arquivo}.pdf"


def _get_creds():
    SCOPES = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/gmail.send",
    ]
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return creds


def gerar_pdf(html_path: str, pdf_path: str) -> bool:
    """Converte HTML para PDF usando playwright (preferido) ou Chrome headless."""
    # Tenta playwright — melhor qualidade, renderiza gráficos Chart.js corretamente
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(f"file://{html_path}")
            page.wait_for_timeout(3000)  # aguarda Chart.js renderizar os gráficos
            # Expande todos os slides para o PDF (o layout usa scroll horizontal)
            page.add_style_tag(content="""
                html, body { overflow: visible !important; height: auto !important; }
                #slider { display: block !important; overflow: visible !important; width: auto !important; height: auto !important; }
                .slide { width: 100% !important; height: auto !important; min-height: 100vh !important; overflow: visible !important; page-break-after: always !important; break-after: page !important; }
                #nav { display: none !important; }
            """)
            # Força Chart.js a redesenhar todos os gráficos após o layout mudar
            page.evaluate("window.dispatchEvent(new Event('resize'))")
            page.wait_for_timeout(3000)
            page.pdf(path=pdf_path, landscape=True, format="A4", print_background=True)
            browser.close()
        print("  ✓ PDF gerado com playwright.")
        return True
    except ImportError:
        print("  [INFO] playwright não instalado, tentando Chrome headless...")
    except Exception as e:
        print(f"  [AVISO] playwright falhou: {e}")

    # Fallback: Chrome headless do sistema
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    chrome = next((c for c in chrome_paths if os.path.exists(c)), None)
    if not chrome:
        print("  [AVISO] PDF não gerado. Para ativar, instale playwright:")
        print("          pip3 install playwright && python3 -m playwright install chromium")
        return False
    try:
        subprocess.run([
            chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=5000",
            f"--print-to-pdf={pdf_path}",
            f"file://{html_path}",
        ], check=True, capture_output=True, timeout=60)
        print("  ✓ PDF gerado com Chrome headless.")
        return True
    except Exception as e:
        print(f"  [AVISO] Chrome headless falhou: {e}")
        return False


def upload_to_drive(drive, local_path: str, nome: str, pasta_id: str, mime: str) -> str:
    """Faz upload de arquivo para o Drive, removendo versão anterior se existir."""
    existing = drive.files().list(
        q=f"name='{nome}' and '{pasta_id}' in parents and trashed=false",
        fields="files(id,name)"
    ).execute().get("files", [])
    for old in existing:
        drive.files().delete(fileId=old["id"]).execute()
        print(f"  Removida versão anterior: {old['name']}")

    with open(local_path, "rb") as fh:
        content = fh.read()

    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime, resumable=False)
    uploaded = drive.files().create(
        body={"name": nome, "parents": [pasta_id]},
        media_body=media,
        fields="id, webViewLink"
    ).execute()
    return uploaded.get("webViewLink", f"https://drive.google.com/file/d/{uploaded['id']}/view")


print("=" * 60)
print(f"  Rotina Dia 20 – {mes_ref:02d}/{ano_ref}")
print("=" * 60)

# ── 1. Rodar análise ──────────────────────────────────────────────────
print("\n[1/4] Rodando análise e gerando relatório HTML ...")
result = subprocess.run(
    [sys.executable, "/Users/lucasbarros/rotina-nfp/analisar.py"],
    capture_output=True, text=True
)
if result.returncode != 0:
    print("  [ERRO] Análise falhou:")
    print(result.stderr[-2000:])
    sys.exit(1)
print(result.stdout[-500:])
print("  ✓ Relatório HTML gerado.")

# ── 2. Gerar PDF ──────────────────────────────────────────────────────
print(f"\n[2/4] Gerando PDF '{nome_arquivo}.pdf' ...")
pdf_ok = gerar_pdf(RELATORIO_LOCAL, pdf_local)

# ── 3. Subir para Drive (HTML na pasta de relatórios, PDF no Histórico) ───
print(f"\n[3/4] Salvando no Drive ...")
creds = _get_creds()
drive = build("drive", "v3", credentials=creds)

drive_link = upload_to_drive(drive, RELATORIO_LOCAL, nome_arquivo, RELATORIO_PASTA, "text/html")
print(f"  ✓ HTML salvo: {drive_link}")

if pdf_ok and os.path.exists(pdf_local):
    pdf_nome = f"{nome_arquivo}.pdf"
    upload_to_drive(drive, pdf_local, pdf_nome, HISTORICO_PASTA, "application/pdf")
    print(f"  ✓ PDF arquivado no Histórico NFP.")

# ── 4. Enviar email ───────────────────────────────────────────────────
print(f"\n[4/4] Enviando email de notificação para a equipe ...")
from emails import enviar_email_relatorio
enviar_email_relatorio(mes_ref, ano_ref, drive_link)

print("\n" + "=" * 60)
print("  Rotina Dia 20 concluída com sucesso!")
print(f"  Relatório: {drive_link}")
print("=" * 60)

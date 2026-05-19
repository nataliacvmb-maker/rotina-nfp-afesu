"""
Funções para envio de emails via Gmail API.
"""
import base64
import datetime
import os
from email.message import EmailMessage
from email import policy as email_policy

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TOKEN_PATH       = os.environ.get("GOOGLE_TOKEN_PATH", "/Users/lucasbarros/rotina-nfp/token.json")
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "/Users/lucasbarros/rotina-nfp/credentials.json")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive",
]

REMETENTE = "natalia.valverde@timecaptacao.com.br"
BARBARA = "barbara.aquino@timecaptacao.com.br"
EQUIPE  = [
    "barbara.aquino@timecaptacao.com.br",
    "ione.machado@timecaptacao.com.br",
    "keven.martineli@timecaptacao.com.br",
    "lucas.monteiro@timecaptacao.com.br",
    "natalia.valverde@timecaptacao.com.br",
]

MESES_PT = {
    1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
    7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro",
}

CONSULTA_DRIVE_URL  = "https://drive.google.com/drive/folders/1v5SUZUJo7CaR3XHhsLd3pAx2fpGt2fYF"
PEDIDO_DRIVE_URL    = "https://drive.google.com/drive/folders/1PBja7WtquTEIIaQntesCdDgnSbWOOkoI"
RELATORIO_PASTA_URL = "https://drive.google.com/drive/u/2/folders/1_LEXZPzLHoYlArvsZgpeQlI9abj1inoW"
GITHUB_PAGES_URL    = "https://nataliacvmb-maker.github.io/rotina-nfp-afesu/"


def _get_gmail_service():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _send(service, to_list, subject, html_body):
    msg = EmailMessage(policy=email_policy.SMTP)
    msg["Subject"] = subject
    msg["From"]    = REMETENTE
    msg["To"]      = ", ".join(to_list)
    msg.set_content(html_body, subtype="html", charset="utf-8")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"  ✓ Email enviado para: {', '.join(to_list)}")


def enviar_email_barbara(mes_ref: int, ano_ref: int):
    """
    Dia 18: avisa Barbara para baixar os arquivos do mês na SEFAZ.
    mes_ref/ano_ref = mês/ano que ela deve baixar.
    """
    service = _get_gmail_service()
    mes_nome = MESES_PT[mes_ref]
    pasta_consulta = f"{ano_ref}-{mes_ref:02d}"
    pasta_pedido   = f"{ano_ref}-{mes_ref:02d}"
    prazo          = "20 de " + MESES_PT[datetime.date.today().month]

    subject = f"NFP AFESU · Baixar arquivos {mes_nome}/{ano_ref} — prazo {prazo}"

    body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1a1a1a;line-height:1.6;max-width:600px;margin:0 auto;padding:20px">
    <p style="color:#888;font-size:12px;text-transform:uppercase;letter-spacing:1px">TIME CAPTAÇÃO · Rotina NFP AFESU</p>
    <h2 style="color:#F0A020;margin-top:0">Olá, Bárbara!</h2>
    <p>É hora de baixar os arquivos do mês de <strong>{mes_nome} de {ano_ref}</strong> no portal da SEFAZ.</p>

    <div style="background:#F7F7F7;border-left:4px solid #F0A020;padding:16px 20px;margin:20px 0;border-radius:4px">
      <p style="margin:0 0 8px 0"><strong>O que baixar:</strong></p>
      <ul style="margin:0;padding-left:20px">
        <li><strong>Consulta NFP</strong> — arquivos ConsultaNFP_*.csv</li>
        <li><strong>Pedidos</strong> — arquivos Pedidos_*.csv</li>
      </ul>
    </div>

    <div style="background:#F7F7F7;border-left:4px solid #F0A020;padding:16px 20px;margin:20px 0;border-radius:4px">
      <p style="margin:0 0 8px 0"><strong>Onde salvar no Drive:</strong></p>
      <ul style="margin:0;padding-left:20px">
        <li>Consulta → crie a pasta <code style="background:#fff;padding:2px 6px;border-radius:3px">{pasta_consulta}</code> dentro de
          <a href="{CONSULTA_DRIVE_URL}" style="color:#F0A020">Consulta</a>
        </li>
        <li>Pedidos → crie a pasta <code style="background:#fff;padding:2px 6px;border-radius:3px">{pasta_pedido}</code> dentro de
          <a href="{PEDIDO_DRIVE_URL}" style="color:#F0A020">Pedido</a>
        </li>
      </ul>
    </div>

    <p><strong>Prazo:</strong> dia <strong>20 deste mês</strong>.</p>
    <p>Qualquer dúvida, é só responder este email. Obrigado! 🙏</p>

    <hr style="border:none;border-top:1px solid #E8E8E8;margin:30px 0">
    <p style="color:#aaa;font-size:11px">TIME Captação · Rotina automatizada NFP/AFESU</p>
    </body></html>
    """
    _send(service, [BARBARA], subject, body)


def enviar_email_relatorio(mes_ref: int, ano_ref: int, drive_link: str):
    """
    Dia 20: notifica toda a equipe que o relatório está pronto no Drive.
    """
    service = _get_gmail_service()
    mes_nome = MESES_PT[mes_ref]
    nome_arquivo = f"{mes_ref:02d}.{ano_ref}_Estudo NFP - AFESU"
    subject = f"{mes_ref:02d}.{ano_ref}_Estudo NFP - AFESU · Relatório disponível"

    body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1a1a1a;line-height:1.6;max-width:600px;margin:0 auto;padding:20px">
    <p style="color:#888;font-size:12px;text-transform:uppercase;letter-spacing:1px">TIME CAPTAÇÃO · Rotina NFP AFESU</p>
    <h2 style="color:#F0A020;margin-top:0">Relatório do mês disponível</h2>
    <p>O relatório <strong>{nome_arquivo}</strong> foi gerado e salvo no Drive.</p>

    <div style="text-align:center;margin:30px 0">
      <a href="{GITHUB_PAGES_URL}" style="background:#F0A020;color:#fff;padding:14px 32px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:15px">
        Abrir Relatório Online
      </a>
    </div>

    <div style="background:#F7F7F7;padding:16px 20px;border-radius:4px;margin:20px 0">
      <p style="margin:0 0 6px 0;color:#666;font-size:13px"><strong>Período coberto:</strong> acumulado até {mes_nome} de {ano_ref}</p>
      <p style="margin:0;color:#666;font-size:13px"><strong>Local:</strong> <a href="{RELATORIO_PASTA_URL}" style="color:#F0A020">Pasta Relatórios NFP no Drive</a></p>
    </div>

    <p>O arquivo está pronto para ser apresentado ao cliente. ✅</p>

    <hr style="border:none;border-top:1px solid #E8E8E8;margin:30px 0">
    <p style="color:#aaa;font-size:11px">TIME Captação · Rotina automatizada NFP/AFESU</p>
    </body></html>
    """
    _send(service, EQUIPE, subject, body)

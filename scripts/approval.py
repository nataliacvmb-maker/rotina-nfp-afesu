"""
Notificações por Gmail no fluxo semi-automatizado.

Responsabilidades:
  - Notificar o OPERADOR quando os insumos estão prontos, com HTML em anexo
    e checklist do que fazer no RD Station
  - Notificar os times de COPY e CRIAÇÃO quando houver pedido de revisão
    (caso o operador repasse o feedback do aprovador para o sistema)
"""

import base64
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
]


def _gmail_service():
    token_path = os.environ["GOOGLE_TOKEN_PATH"]
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def notificar_operador(
    operador_email: str,
    operador_nome: str,
    cliente_nome: str,
    mes: str,
    total_contatos: int,
    roteiro: dict,
    html_path: str,
    approver_email: str,
    approver_nome: str,
    de_email: str,
):
    """
    Envia ao operador tudo que ele precisa para criar a campanha no RD Station:
    - Checklist de passos
    - Dados do email (assunto, título, CTA)
    - HTML completo como arquivo em anexo
    """
    service = _gmail_service()

    assunto_email = roteiro.get("assunto", "")
    titulo = roteiro.get("titulo", "—")
    cta_texto = roteiro.get("cta_texto", "Doe agora")
    cta_url = roteiro.get("cta_url", "")

    assunto = f"[PRONTO PARA CAMPANHA] {cliente_nome} — {mes}"
    corpo = f"""Olá, {operador_nome}!

Os insumos de {cliente_nome} para {mes} estão prontos e a base foi importada automaticamente no RD Station.

✅ {total_contatos:,} contatos importados na lista "{cliente_nome}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHECKLIST — O QUE FAZER NO RD STATION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[ ] 1. Criar nova campanha de email marketing

[ ] 2. Configurar a campanha:
        Assunto:     {assunto_email}
        De (nome):   TIME Captação
        Lista:       {cliente_nome}

[ ] 3. Colar o conteúdo:
        → Abra o arquivo "{cliente_nome}_{mes}.html" em anexo
        → Copie o HTML completo
        → No RD Station, escolha "Editor HTML" e cole

[ ] 4. Enviar email TESTE para:
        {approver_nome} — {approver_email}

[ ] 5. Após aprovação do teste, disparar para a lista "{cliente_nome}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESUMO DO CONTEÚDO DO EMAIL:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Assunto:   {assunto_email}
Título:    {titulo}
Botão:     [{cta_texto}] → {cta_url}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TIME Captação (sistema automático)
"""

    msg = MIMEMultipart()
    msg["To"] = operador_email
    msg["From"] = de_email
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    nome_arquivo = f"{cliente_nome.replace(' ', '_')}_{mes}.html"
    with open(html_path, "rb") as f:
        html_part = MIMEApplication(f.read(), Name=nome_arquivo)
        html_part["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
        msg.attach(html_part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"  Notificação enviada para {operador_nome} ({operador_email}) com HTML em anexo")


def notificar_revisao(
    copy_email: str,
    copy_nome: str,
    criacao_email: str,
    criacao_nome: str,
    cliente_nome: str,
    mes: str,
    feedback: str,
    de_email: str,
    versao: int = 1,
    criacao_email_2: str = "",
    criacao_nome_2: str = "",
):
    """
    Encaminha feedback de revisão para os times de copy e criação.
    Chamado manualmente pelo operador quando o aprovador solicita ajustes.
    """
    service = _gmail_service()
    assunto = f"[REVISÃO NECESSÁRIA] Email {cliente_nome} — {mes}"

    destinatarios_criacao = [(criacao_email, criacao_nome)]
    if criacao_email_2:
        destinatarios_criacao.append((criacao_email_2, criacao_nome_2))

    for para_email, para_nome, instrucao in [
        (copy_email, copy_nome,
         f"revise o arquivo copy/roteiro.yaml na pasta do cliente no Drive:\n"
         f"  {cliente_nome} > Disparos Emails > {mes} > copy > roteiro.yaml"),
        *[(e, n, f"atualize o banner na pasta do cliente no Drive:\n"
           f"  {cliente_nome} > Disparos Emails > {mes} > banner > [arquivo]")
          for e, n in destinatarios_criacao],
    ]:
        if not para_email:
            continue

        corpo = f"""Olá, {para_nome}!

O email de {mes} para {cliente_nome} precisa de ajuste (versão {versao}).

Feedback:
─────────────────────────────────────
{feedback}
─────────────────────────────────────

Por favor, {instrucao}

Após salvar, avise o operador para gerar uma nova versão.

TIME Captação
"""
        msg = MIMEText(corpo, "plain", "utf-8")
        msg["To"] = para_email
        msg["From"] = de_email
        msg["Subject"] = assunto
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"  Feedback encaminhado para {para_nome} ({para_email})")

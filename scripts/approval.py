"""
Notificações por Gmail no fluxo semi-automatizado.
"""

import base64
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


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
    disparo_nome: str,
    total_contatos: int,
    roteiro: dict,
    html_path: str,
    approver_email: str,
    approver_nome: str,
    de_email: str,
):
    """Envia ao operador o HTML pronto + checklist para criar a campanha no RD Station."""
    service = _gmail_service()

    assunto_email = roteiro.get("assunto", "")
    titulo = roteiro.get("titulo", "—")
    cta_texto = roteiro.get("cta_texto", "Doe agora")
    cta_url = roteiro.get("cta_url", "")

    assunto = f"[PRONTO PARA CAMPANHA] {cliente_nome} — {disparo_nome} — {mes}"
    corpo = f"""Olá, {operador_nome}!

Os insumos de {cliente_nome} ({disparo_nome}) para {mes} estão prontos.
A base foi importada automaticamente no RD Station com a tag "{cliente_nome}".

✅ {total_contatos:,} contatos importados

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHECKLIST — O QUE FAZER NO RD STATION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[ ] 1. Criar nova campanha de email marketing

[ ] 2. Configurar a campanha:
        Assunto:     {assunto_email}
        De (nome):   TIME Captação
        Segmentação: tag "{cliente_nome}"

[ ] 3. Colar o conteúdo:
        → Abra o arquivo em anexo: {cliente_nome}_{disparo_nome}_{mes}.html
        → Copie o HTML completo (Ctrl+A, Ctrl+C)
        → No RD Station: Editor HTML → cole o conteúdo

[ ] 4. Enviar email TESTE para:
        {approver_nome} — {approver_email}

[ ] 5. Aguardar aprovação e então disparar para a tag "{cliente_nome}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESUMO DO CONTEÚDO:
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

    nome_arquivo = f"{cliente_nome.replace(' ', '_')}_{disparo_nome}_{mes}.html"
    with open(html_path, "rb") as f:
        html_part = MIMEApplication(f.read(), Name=nome_arquivo)
        html_part["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
        msg.attach(html_part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"  Email enviado para {operador_nome} ({operador_email})")


def notificar_revisao(
    copy_email: str,
    copy_nome: str,
    criacao_email: str,
    criacao_nome: str,
    cliente_nome: str,
    mes: str,
    disparo_nome: str,
    feedback: str,
    de_email: str,
    pasta_copy_link: str = "",
    pasta_banner_link: str = "",
    versao: int = 1,
    criacao_email_2: str = "",
    criacao_nome_2: str = "",
):
    """Encaminha feedback de revisão para copy e criação com instruções detalhadas."""
    service = _gmail_service()
    assunto = f"[REVISÃO v{versao}] {cliente_nome} — {disparo_nome} — {mes}"

    # Notificação para COPY
    if copy_email:
        corpo_copy = f"""Olá, {copy_nome}!

O email "{disparo_nome}" de {mes} para {cliente_nome} precisa de ajuste no texto (versão {versao}).

FEEDBACK:
─────────────────────────────────────
{feedback}
─────────────────────────────────────

PASTA NO DRIVE:
→ {pasta_copy_link or '(ver pasta copy do cliente no Drive)'}

COMO ATUALIZAR O ROTEIRO:
1. Abra a pasta no link acima
2. Baixe o arquivo roteiro.yaml
3. Edite com qualquer editor de texto (Bloco de Notas, TextEdit, VS Code)
4. Salve com o nome exato: roteiro.yaml (minúsculo, sem espaços)
5. Delete o arquivo antigo da pasta no Drive
6. Faça upload do novo: clique em (+) Novo → Upload de arquivo

CAMPOS QUE VOCÊ PODE EDITAR:
  assunto:    linha de assunto (aparece na caixa de entrada do destinatário)
  preheader:  texto de pré-visualização (opcional)
  titulo:     título em destaque dentro do email (opcional)
  corpo:      corpo do email — use linha em branco para separar parágrafos
  cta_url:    link do botão de doação (obrigatório)
  cta_texto:  texto do botão (padrão: "Doe agora")

Após salvar, avise o operador para gerar nova versão.

TIME Captação
"""
        _enviar_email(service, copy_email, de_email, assunto, corpo_copy)
        print(f"  Feedback de copy enviado para {copy_nome} ({copy_email})")

    # Notificação para CRIAÇÃO (Vinicius + João)
    destinatarios_criacao = [(criacao_email, criacao_nome)]
    if criacao_email_2:
        destinatarios_criacao.append((criacao_email_2, criacao_nome_2))

    for para_email, para_nome in destinatarios_criacao:
        if not para_email:
            continue
        corpo_criacao = f"""Olá, {para_nome}!

O banner do email "{disparo_nome}" de {mes} para {cliente_nome} precisa de ajuste (versão {versao}).

FEEDBACK:
─────────────────────────────────────
{feedback}
─────────────────────────────────────

PASTA NO DRIVE:
→ {pasta_banner_link or '(ver pasta banner do cliente no Drive)'}

COMO ATUALIZAR O BANNER:
1. Exporte o banner final como .png ou .jpg
   → Largura: 600px (padrão para email)
   → Nome do arquivo: banner_{cliente_nome.lower().replace(' ', '_')}_{mes}.png
2. Abra a pasta no link acima
3. Delete o arquivo de banner antigo
4. Faça upload do novo: clique em (+) Novo → Upload de arquivo

Após salvar, avise o operador para gerar nova versão.

TIME Captação
"""
        _enviar_email(service, para_email, de_email, assunto, corpo_criacao)
        print(f"  Feedback de criação enviado para {para_nome} ({para_email})")


def _enviar_email(service, para: str, de: str, assunto: str, corpo: str):
    msg = MIMEText(corpo, "plain", "utf-8")
    msg["To"] = para
    msg["From"] = de
    msg["Subject"] = assunto
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()

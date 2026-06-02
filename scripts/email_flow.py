"""
Orquestrador do fluxo semi-automatizado de email marketing.

O que o sistema faz automaticamente:
  1. Detecta todos os disparos prontos no Drive (Disparo-1, Disparo-2, etc.)
  2. Importa os contatos no RD Station com a tag do cliente
  3. Gera o HTML completo do email (logo + header + texto + imagem CTA + final)
  4. Envia email ao operador com checklist + HTML em anexo

O que o operador faz manualmente no RD Station:
  - Criar a campanha e colar o HTML
  - Enviar email teste para o aprovador
  - Após aprovação, disparar para a lista
"""

import os
import traceback
import yaml
from datetime import datetime, timezone
from pathlib import Path

from rdstation_api import RDStationAPI
from drive_utils import (
    verificar_insumos, baixar_base_emails, baixar_imagem_opcional,
    baixar_roteiro, ler_estado, salvar_estado
)
from approval import notificar_operador
from sheets_utils import atualizar_planilha_apos_disparo


def carregar_config() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "clients.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def _mes_atual() -> str:
    meses = {
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
    }
    hoje = datetime.today()
    return f"{meses[hoje.month]}-{hoje.year}"


def processar_cliente(cliente: dict, config: dict):
    nome = cliente["name"]
    drive_id = cliente.get("drive_folder_id", "")
    list_id = cliente.get("rdstation_list_id", "")
    operador_email = cliente.get("operador_email", "")
    operador_nome = cliente.get("operador_nome", "")
    approver_email = cliente.get("approver_email", "")
    approver_nome = cliente.get("approver_name", "")
    de_email = config.get("notification_from_email", "")
    spreadsheet_id = cliente.get("spreadsheet_id", "")

    if not drive_id or not list_id or not operador_email:
        print(f"[{nome}] ⚠ Configuração incompleta — pulando")
        return

    mes = _mes_atual()
    estado = ler_estado(drive_id)

    disparos = verificar_insumos(drive_id)
    if not disparos:
        print(f"[{nome}] ⏳ Aguardando insumos no Drive")
        return

    for disparo in disparos:
        campanha_id = disparo["campanha_id"]
        disparo_nome = disparo["disparo_nome"]

        campanha_existente = next(
            (c for c in estado.get("campanhas", []) if c.get("campanha_id") == campanha_id),
            None
        )
        if campanha_existente and campanha_existente.get("status") == "notificado":
            print(f"[{nome}] ✓ {disparo_nome}: operador já notificado")
            continue

        print(f"[{nome}] {disparo_nome} ✓ Insumos prontos: {disparo['base_nome']} | {disparo['banner_nome']} | {disparo['roteiro_nome']}")

        rd = RDStationAPI()
        contatos = baixar_base_emails(disparo["base_id"])
        print(f"[{nome}] {disparo_nome}: importando {len(contatos)} contatos...")
        try:
            rd.importar_contatos(contatos, list_id)
            print(f"[{nome}] {disparo_nome}: ✓ {len(contatos)} contatos importados")
            importacao_ok = True
        except Exception as e:
            print(f"[{nome}] {disparo_nome}: ⚠ Erro na importação: {e} — continuando")
            importacao_ok = False

        roteiro = baixar_roteiro(disparo["roteiro_id"])

        if not roteiro.get("assunto"):
            print(f"[{nome}] {disparo_nome}: ⚠ roteiro.yaml sem 'assunto' — abortando")
            continue
        if not roteiro.get("cta_url"):
            print(f"[{nome}] {disparo_nome}: ⚠ roteiro.yaml sem 'cta_url' — abortando")
            continue

        # Baixa cada imagem pelo seu papel
        logo_path     = baixar_imagem_opcional(disparo.get("logo_id"),        "logo")
        header_path   = baixar_imagem_opcional(disparo.get("header_id"),       "header")
        campanha_path = baixar_imagem_opcional(disparo.get("campanha_img_id"), "campanha")
        final_path    = baixar_imagem_opcional(disparo.get("final_id"),        "final")

        html = _montar_html(
            cliente_nome=nome,
            roteiro=roteiro,
            logo_path=logo_path,
            header_path=header_path,
            campanha_path=campanha_path,
            final_path=final_path,
        )
        html_path = f"/tmp/{cliente['slug']}_{disparo_nome}_{mes}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        notificar_operador(
            operador_email=operador_email,
            operador_nome=operador_nome,
            cliente_nome=nome,
            mes=mes,
            disparo_nome=disparo_nome,
            total_contatos=len(contatos),
            roteiro=roteiro,
            html_path=html_path,
            approver_email=approver_email,
            approver_nome=approver_nome,
            de_email=de_email,
        )

        # Grava links na planilha de controle (Drive + HTML)
        try:
            atualizar_planilha_apos_disparo(
                spreadsheet_id=spreadsheet_id,
                cliente_slug=cliente["slug"],
                campanha_id=campanha_id,
                html_path=html_path,
                pasta_drive_id=drive_id,
                pasta_drive_link=disparo.get("pasta_base_link", "").rsplit("/", 1)[0] if disparo.get("pasta_base_link") else "",
            )
        except Exception as e:
            print(f"[{nome}] {disparo_nome}: ⚠ Erro ao atualizar planilha: {e}")

        dados_campanha = {
            "campanha_id": campanha_id,
            "mes": mes,
            "disparo": disparo_nome,
            "status": "notificado",
            "total_contatos": len(contatos),
            "importacao_ok": importacao_ok,
            "notificado_em": datetime.now(timezone.utc).isoformat(),
            "assunto": roteiro.get("assunto", ""),
            "metricas": None,
        }
        estado.setdefault("campanhas", []).append(dados_campanha)
        salvar_estado(drive_id, estado)
        print(f"[{nome}] {disparo_nome}: ✓ Operador notificado")


def _img_b64(path: str) -> str:
    """Converte imagem local para data URL base64."""
    import base64
    ext = path.rsplit(".", 1)[-1].lower()
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def _montar_html(
    cliente_nome: str,
    roteiro: dict,
    logo_path: str | None,
    header_path: str | None,
    campanha_path: str | None,
    final_path: str | None,
) -> str:
    """
    Monta HTML do email com estrutura:
      [logo] → [header] → [texto] → [imagem campanha clicável] → [imagem final] → [footer]
    Cada bloco é omitido se o arquivo não existir.
    """
    cta_url = roteiro.get("cta_url", "")

    logo_html = ""
    if logo_path:
        logo_html = f'<div class="logo"><img src="{_img_b64(logo_path)}" alt="{cliente_nome} logo"></div>'

    header_html = ""
    if header_path:
        header_html = f'<div class="header-img"><img src="{_img_b64(header_path)}" alt=""></div>'

    corpo_html = ""
    if roteiro.get("corpo"):
        linhas = roteiro["corpo"].strip().replace("\n\n", "</p><p>").replace("\n", "<br>")
        corpo_html = f'<div class="corpo"><p>{linhas}</p></div>'

    campanha_html = ""
    if campanha_path and cta_url:
        campanha_html = (
            f'<div class="campanha">'
            f'<a href="{cta_url}" target="_blank">'
            f'<img src="{_img_b64(campanha_path)}" alt="Doe agora" style="width:100%;height:auto;display:block">'
            f'</a></div>'
        )
    elif campanha_path:
        campanha_html = f'<div class="campanha"><img src="{_img_b64(campanha_path)}" alt="" style="width:100%;height:auto;display:block"></div>'

    final_html = ""
    if final_path:
        final_html = f'<div class="final-img"><img src="{_img_b64(final_path)}" alt=""></div>'

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>{roteiro.get("assunto", cliente_nome)}</title>
  <style>
    body{{margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif}}
    .wrapper{{max-width:600px;margin:0 auto;background:#fff}}
    .logo{{padding:20px 24px;text-align:center;background:#fff}}
    .logo img{{max-height:70px;width:auto}}
    .header-img img{{width:100%;height:auto;display:block}}
    .corpo{{padding:24px 28px;color:#444;font-size:15px;line-height:1.8}}
    .corpo p{{margin:0 0 14px}}
    .campanha{{margin:0}}
    .final-img img{{width:100%;height:auto;display:block}}
    .footer{{padding:16px 24px;text-align:center;font-size:11px;color:#aaa;border-top:1px solid #eee}}
    .footer a{{color:#aaa}}
  </style>
</head>
<body>
  <div class="wrapper">
    {logo_html}
    {header_html}
    {corpo_html}
    {campanha_html}
    {final_html}
    <div class="footer">
      Você está recebendo este email porque está cadastrado na base da <strong>{cliente_nome}</strong>.<br>
      Para se descadastrar, <a href="[unsubscribe]">clique aqui</a>.
    </div>
  </div>
</body>
</html>"""


def main():
    config = carregar_config()
    clientes = config.get("clients", [])
    print(f"Iniciando processamento — {len(clientes)} clientes — {_mes_atual()}")
    for cliente in clientes:
        try:
            processar_cliente(cliente, config)
        except Exception as e:
            print(f"[{cliente['name']}] ERRO: {e}")
            traceback.print_exc()
    print("Processamento concluído")


if __name__ == "__main__":
    main()

"""
Gera um novo token OAuth com todos os escopos necessários.

Execute UMA VEZ localmente quando precisar adicionar novos escopos.
Depois atualize o secret GOOGLE_REFRESH_TOKEN no GitHub com o valor impresso.

Pré-requisito: crie um arquivo client_secret.json com as credenciais OAuth2
do Google Cloud Console (tipo: Aplicativo de desktop / Desktop app).

Uso:
    python scripts/auth_google.py --client-secret /caminho/client_secret.json

O script abre o navegador para autorização e salva o token em google_token.json.
"""

import argparse
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/script.deployments",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--client-secret",
        default="client_secret.json",
        help="Caminho para o arquivo client_secret.json (padrão: ./client_secret.json)",
    )
    parser.add_argument(
        "--output",
        default="google_token.json",
        help="Onde salvar o token (padrão: ./google_token.json)",
    )
    args = parser.parse_args()

    client_secret_path = Path(args.client_secret)
    if not client_secret_path.exists():
        print(f"❌ Arquivo não encontrado: {client_secret_path}")
        print()
        print("Como criar:")
        print("  1. Acesse https://console.cloud.google.com/apis/credentials")
        print("  2. Crie credencial → ID do cliente OAuth 2.0 → Aplicativo de desktop")
        print("  3. Baixe o JSON e salve como client_secret.json")
        return

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = json.loads(creds.to_json())
    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\n✅ Token salvo em: {output_path}")
    print()
    print("Atualize o secret GOOGLE_REFRESH_TOKEN no GitHub com este valor:")
    print(f"\n  {token_data.get('refresh_token', '(não encontrado)')}\n")
    print("GitHub → Settings → Secrets and variables → Actions → GOOGLE_REFRESH_TOKEN")

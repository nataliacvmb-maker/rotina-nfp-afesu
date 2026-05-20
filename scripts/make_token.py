"""
Reconstrói o google_token.json a partir de variáveis de ambiente.
Chamado pelo GitHub Actions antes de rodar email_flow.py.
"""

import json
import os

token = {
    "token": None,
    "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"],
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": os.environ["GOOGLE_CLIENT_ID"],
    "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
    "scopes": [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/drive",
    ],
}

output_path = os.environ.get("GOOGLE_TOKEN_PATH", "/tmp/google_token.json")
with open(output_path, "w") as f:
    json.dump(token, f)

print(f"Credenciais restauradas em {output_path}")

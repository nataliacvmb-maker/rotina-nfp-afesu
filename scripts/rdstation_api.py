"""
Cliente para a API do RD Station Marketing (token privado — API legada v1.3).

Usa app.rdstation.com.br/api/1.3 com auth_token — compatível com plano sem OAuth2.
Contatos são importados via /conversions; a tag funciona como segmentação de lista.
"""

import os
import requests


class RDStationAPI:
    BASE_URL = "https://app.rdstation.com.br/api/1.3"

    def __init__(self):
        self.token = os.environ["RDSTATION_PRIVATE_TOKEN"]

    def _params(self) -> dict:
        return {"auth_token": self.token}

    def importar_contatos(self, contatos: list[dict], tag: str) -> dict:
        resultados = {"sucesso": 0, "erro": 0}
        for c in contatos:
            if not c.get("email"):
                continue
            payload = {
                "event_type": "CONVERSION",
                "event_family": "CDP",
                "payload": {
                    "email": c["email"],
                    "name": c.get("name", ""),
                    "tags": [tag],
                },
            }
            try:
                resp = requests.post(
                    f"{self.BASE_URL}/conversions",
                    params=self._params(),
                    json=payload,
                    timeout=30,
                )
                resp.raise_for_status()
                resultados["sucesso"] += 1
            except Exception:
                resultados["erro"] += 1
        return resultados

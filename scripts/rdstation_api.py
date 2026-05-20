"""
Cliente para a API do RD Station Marketing (token privado — API legada v1.3).

Na API v1.3, contatos são importados via /conversions com tags.
As "listas" do RD Station são representadas por tags no plano atual.
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
        """
        Importa contatos via conversions, adicionando a tag da lista/cliente.
        """
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

    def listar_tags(self) -> list:
        """Retorna todas as tags da conta."""
        resp = requests.get(
            f"{self.BASE_URL}/tags",
            params=self._params(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

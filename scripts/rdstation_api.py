"""
Cliente para a API do RD Station Marketing (token privado — API legada v1.3).
"""

import os
import requests


class RDStationAPI:
    BASE_URL = "https://app.rdstation.com.br/api/1.3"

    def __init__(self):
        self.token = os.environ["RDSTATION_PRIVATE_TOKEN"]

    def _params(self, extra: dict | None = None) -> dict:
        p = {"auth_token": self.token}
        if extra:
            p.update(extra)
        return p

    def importar_contatos(self, contatos: list[dict], list_id: str) -> dict:
        """
        Importa contatos via conversions (upsert individual).
        A API legada não tem endpoint de importação em lote — fazemos um por vez.
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
                    "tags": [list_id],
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

    def listar_segmentacoes(self) -> dict:
        """Retorna todas as segmentações/listas da conta."""
        resp = requests.get(
            f"{self.BASE_URL}/segmentations",
            params=self._params(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

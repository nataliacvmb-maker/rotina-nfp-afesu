"""
Cliente para a API do RD Station Marketing (autenticação por token privado).
"""

import os
import requests


class RDStationAPI:
    BASE_URL = "https://api.rd.services"

    def __init__(self):
        self.token = os.environ["RDSTATION_PRIVATE_TOKEN"]

    def _headers(self) -> dict:
        return {
            "Authorization": f"Token token={self.token}",
            "Content-Type": "application/json",
        }

    def importar_contatos(self, contatos: list[dict], list_id: str) -> dict:
        """
        Importa lista de contatos [{email, name}, ...] em uma segmentação do RD Station.
        Usa o endpoint de importação em lote.
        """
        payload = {
            "contacts": [
                {"email": c["email"], "name": c.get("name", "")}
                for c in contatos
                if c.get("email")
            ],
            "tags": [],
            "segmentation_ids": [list_id],
        }
        resp = requests.post(
            f"{self.BASE_URL}/platform/contacts/import",
            headers=self._headers(),
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def listar_segmentacoes(self) -> dict:
        """Retorna todas as segmentações/listas da conta."""
        resp = requests.get(
            f"{self.BASE_URL}/platform/segmentations",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

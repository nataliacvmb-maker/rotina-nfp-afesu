"""
Utilitário para listar as segmentações (listas) do RD Station e obter os IDs.
Rodar uma vez localmente para preencher o rdstation_list_id no clients.yaml.

Uso:
  RDSTATION_PRIVATE_TOKEN=seu_token_privado python listar_segmentacoes.py
"""

import os
from rdstation_api import RDStationAPI


def main():
    rd = RDStationAPI()
    resultado = rd.listar_segmentacoes()

    segmentacoes = resultado.get("segmentations", resultado.get("data", [resultado] if isinstance(resultado, dict) else resultado))

    print("\nSegmentações disponíveis no RD Station:\n")
    print(f"{'ID':<40} {'Nome'}")
    print("─" * 70)

    if isinstance(segmentacoes, list):
        for seg in segmentacoes:
            seg_id = seg.get("id", seg.get("uuid", "—"))
            seg_nome = seg.get("name", seg.get("title", "—"))
            print(f"{str(seg_id):<40} {seg_nome}")
    else:
        print("Resposta inesperada da API:")
        import json
        print(json.dumps(resultado, indent=2, ensure_ascii=False))

    print("\nCopie o ID correspondente a cada cliente no config/clients.yaml")


if __name__ == "__main__":
    main()

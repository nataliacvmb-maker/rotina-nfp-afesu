"""
Utilitário para listar as tags do RD Station.

Na API legada v1.3, as "listas" são tags. Este script mostra todas as tags
existentes na conta para preencher o rdstation_tag no clients.yaml.

Uso:
  RDSTATION_PRIVATE_TOKEN=seu_token python3 listar_segmentacoes.py
"""

import os
from rdstation_api import RDStationAPI


def main():
    rd = RDStationAPI()
    tags = rd.listar_tags()

    print("\nTags disponíveis no RD Station:\n")

    if isinstance(tags, list) and tags:
        for tag in tags:
            if isinstance(tag, dict):
                print(f"  - {tag.get('name', tag)}")
            else:
                print(f"  - {tag}")
    elif isinstance(tags, dict):
        import json
        print(json.dumps(tags, indent=2, ensure_ascii=False))
    else:
        print("  (nenhuma tag encontrada)")

    print("\nDica: use o nome da tag no campo rdstation_tag do clients.yaml")
    print("Se não tiver tags ainda, defina um nome por cliente (ex: 'Afesu', 'Amparo')")
    print("O sistema criará a tag automaticamente na primeira importação.\n")


if __name__ == "__main__":
    main()

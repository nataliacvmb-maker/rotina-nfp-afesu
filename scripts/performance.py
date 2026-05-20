"""
Coleta métricas de campanhas enviadas e registra no estado de cada cliente.

Limitação atual: o plano RD Station não expõe métricas por campanha via API.
Este script salva um placeholder para preenchimento manual futuro
e está preparado para integrar quando o plano for atualizado.

Métricas registradas (quando disponíveis):
  - taxa_abertura: % de emails abertos
  - taxa_clique:   % de cliques no CTA
  - descadastros:  quantidade de opt-outs
  - novos_doadores (ROI de Lead): doadores novos gerados pela campanha
  - receita_gerada (ROI Financeiro): aumento em R$ de doações atribuído
"""

import yaml
from datetime import datetime
from pathlib import Path

from drive_utils import ler_estado, salvar_estado


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


def coletar_metricas_cliente(cliente: dict):
    nome = cliente["name"]
    drive_id = cliente.get("drive_folder_id", "")
    if not drive_id:
        return

    mes = _mes_atual()
    estado = ler_estado(drive_id)
    campanha = next(
        (c for c in estado.get("campanhas", []) if c["mes"] == mes), None
    )

    if not campanha:
        print(f"[{nome}] Nenhuma campanha registrada para {mes}")
        return

    if campanha.get("metricas"):
        print(f"[{nome}] Métricas já registradas para {mes}")
        return

    # Placeholder — preencher manualmente ou via API quando disponível
    campanha["metricas"] = {
        "coletado_em": datetime.utcnow().isoformat(),
        "taxa_abertura": None,
        "taxa_clique": None,
        "descadastros": None,
        "novos_doadores": None,
        "receita_gerada_brl": None,
        "nota": "Preencher manualmente ou aguardar integração API",
    }
    salvar_estado(drive_id, estado)
    print(f"[{nome}] Placeholder de métricas salvo para {mes}")


def main():
    config = carregar_config()
    clientes = config.get("clients", [])
    print(f"Coletando métricas — {len(clientes)} clientes — {_mes_atual()}")
    for cliente in clientes:
        try:
            coletar_metricas_cliente(cliente)
        except Exception as e:
            print(f"[{cliente['name']}] ERRO ao coletar métricas: {e}")
    print("Coleta de métricas concluída")


if __name__ == "__main__":
    main()

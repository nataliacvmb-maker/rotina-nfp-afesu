#!/usr/bin/env python3
"""
Rotina mensal de análise de dados NFP (Nota Fiscal Paulista) - AFESU
JOIN entre CSVs de Consulta (créditos) e CSVs de Pedido (doadores/CPFs)
Gera relatório HTML completo em 8 slides com tema clean TIME Captação.

CORREÇÕES (Mai/2026):
  - Lag de 4 meses: relatório sempre usa MES_REF = hoje - 4 meses
  - Deduplicação por Série (CNPJ + Nº + Valor + Mês) antes do JOIN
  - JOIN usa chave Série completa (4 campos) em vez de apenas Nº+CNPJ
  - notas_aceitas aceita "Calculado" (2026) e "Liberado" (2025)
  - Seleção de pasta automática por ANO_REF
"""

import io
import json
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import pandas as pd
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ─── Constants ─────────────────────────────────────────────────────────────────

CONSULTA_2025_FOLDER_ID = "1KZqhdp6hqOKwd1He8nRCLhyTSP_JUGp8"
CONSULTA_2026_FOLDER_ID = "1v5SUZUJo7CaR3XHhsLd3pAx2fpGt2fYF"

PEDIDO_2025_FOLDER_ID = "1PBja7WtquTEIIaQntesCdDgnSbWOOkoI"
PEDIDO_2026_FOLDER_ID = "1PBja7WtquTEIIaQntesCdDgnSbWOOkoI"  # atualizar quando pasta 2026 for separada

CREDENTIALS_PATH = "/Users/lucasbarros/rotina-nfp/credentials.json"
TOKEN_PATH       = "/Users/lucasbarros/rotina-nfp/token.json"
OUTPUT_PATH      = "/Users/lucasbarros/rotina-nfp/relatorio_atual.html"

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.send",
]

MONTH_ABBR_MAP = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

MONTH_FULL_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio",
    6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro",
    11: "Novembro", 12: "Dezembro",
}

# ─── Mês/Ano de referência (lag de 4 meses) ────────────────────────────────
_hoje_calc = datetime.date.today()
_lag = _hoje_calc.month - 4
if _lag <= 0:
    MES_REF = _lag + 12
    ANO_REF = _hoje_calc.year - 1
else:
    MES_REF = _lag
    ANO_REF = _hoje_calc.year

# Projeção 2026 estática
PROJ_2026 = [
    ("Jan/2026",  0,  199, 0,   0.00),
    ("Fev/2026",  0,  199, 0,   0.00),
    ("Mar/2026",  0,  199, 0,   0.00),
    ("Abr/2026",  0,  199, 0,   0.00),
    ("Mai/2026", 38,  237, 199, 14726.00),
    ("Jun/2026", 38,  275, 237, 17538.00),
    ("Jul/2026", 38,  313, 275, 20350.00),
    ("Ago/2026", 38,  351, 313, 23162.00),
    ("Set/2026", 38,  389, 351, 25974.00),
    ("Out/2026", 38,  427, 389, 28786.00),
    ("Nov/2026", 38,  465, 427, 31598.00),
    ("Dez/2026", 38,  503, 465, 34410.00),
]

# ─── Google Drive helpers ───────────────────────────────────────────────────────

def build_drive_service():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    return build("drive", "v3", credentials=creds)


def _list_folder_items(drive, folder_id: str) -> List[dict]:
    items, page_token = [], None
    while True:
        params = dict(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=200,
        )
        if page_token:
            params["pageToken"] = page_token
        resp = drive.files().list(**params).execute()
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


def _download_file_bytes(drive, file_id: str) -> bytes:
    request = drive.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buf.seek(0)
    return buf.read()


def _read_consulta_csv(raw: bytes, filename: str) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(
            io.BytesIO(raw), sep="\t", encoding="utf-16",
            decimal=",", thousands=".", quotechar='"', on_bad_lines="skip",
        )
        df.columns = [c.strip() for c in df.columns]
        return df
    except Exception as e:
        print(f"    [AVISO] Não foi possível ler Consulta CSV '{filename}': {e}")
        return None


def _read_pedido_csv(raw: bytes, filename: str) -> Optional[pd.DataFrame]:
    for enc in ("latin-1", "utf-8", "cp1252"):
        try:
            df = pd.read_csv(
                io.BytesIO(raw), sep=";", encoding=enc,
                decimal=",", on_bad_lines="skip",
            )
            df.columns = [c.strip() for c in df.columns]
            return df
        except Exception:
            continue
    print(f"    [AVISO] Não foi possível ler Pedido CSV '{filename}'")
    return None


def load_consulta_csvs(drive, folder_id: str, year_filter: Optional[int] = None) -> pd.DataFrame:
    """Carrega todos os CSVs de Consulta, deduplicando por Série após concat."""
    print(f"  Listando pasta de Consulta ({folder_id}) ...")
    items = _list_folder_items(drive, folder_id)
    dfs = []

    subfolders = [i for i in items if i["mimeType"] == "application/vnd.google-apps.folder"]
    root_files = [i for i in items if i["mimeType"] != "application/vnd.google-apps.folder"]

    for f in root_files:
        if not f["name"].lower().endswith(".csv"):
            continue
        # Ignora arquivos de Pedido que possam ter sido salvos na pasta errada
        if f["name"].lower().startswith("pedido"):
            print(f"    [AVISO] Ignorando '{f['name']}' (parece ser arquivo de Pedido na pasta de Consulta).")
            continue
        print(f"    Baixando (raiz) {f['name']} ...")
        raw = _download_file_bytes(drive, f["id"])
        df = _read_consulta_csv(raw, f["name"])
        if df is not None:
            df["_source_file"] = f["name"]
            df["_folder"] = "(raiz)"
            dfs.append(df)

    for folder in subfolders:
        folder_name = folder["name"]
        # Filtra subpasta pelo ano se especificado (ex: só "2025-XX")
        if year_filter and not folder_name.startswith(str(year_filter)):
            print(f"    Ignorando pasta '{folder_name}' (não é do ano {year_filter}).")
            continue
        print(f"    Pasta: {folder_name}")
        sub_items = _list_folder_items(drive, folder["id"])
        for f in sub_items:
            if f["mimeType"] == "application/vnd.google-apps.folder":
                continue
            if not f["name"].lower().endswith(".csv"):
                continue
            if f["name"].lower().startswith("pedido"):
                print(f"      [AVISO] Ignorando '{f['name']}' (arquivo de Pedido na pasta errada).")
                continue
            print(f"      Baixando {f['name']} ...")
            raw = _download_file_bytes(drive, f["id"])
            df = _read_consulta_csv(raw, f["name"])
            if df is not None:
                df["_source_file"] = f["name"]
                df["_folder"] = folder_name
                dfs.append(df)

    if not dfs:
        print("    [AVISO] Nenhum CSV de Consulta encontrado.")
        return pd.DataFrame()

    result = pd.concat(dfs, ignore_index=True)
    print(f"    Total Consulta (antes dedup): {len(result):,} linhas de {len(dfs)} arquivo(s).")

    # Deduplicação por Série — elimina sobreposição dos downloads cumulativos da SEFAZ
    result = _clean_consulta(result)
    if "_serie" in result.columns:
        before = len(result)
        result = result.drop_duplicates(subset=["_serie"])
        removed = before - len(result)
        print(f"    Após deduplicação por Série: {len(result):,} linhas ({removed:,} duplicatas removidas).")

    return result


def load_pedido_csvs(drive, folder_id: str, year_filter: Optional[int] = None) -> pd.DataFrame:
    """Carrega todos os CSVs de Pedido recursivamente."""
    print(f"  Listando pasta de Pedido ({folder_id}) ...")
    items = _list_folder_items(drive, folder_id)
    dfs = []

    subfolders = [i for i in items if i["mimeType"] == "application/vnd.google-apps.folder"]
    root_files = [i for i in items if i["mimeType"] != "application/vnd.google-apps.folder"]

    for f in root_files:
        if not f["name"].lower().endswith(".csv"):
            continue
        print(f"    Baixando (raiz) {f['name']} ...")
        raw = _download_file_bytes(drive, f["id"])
        df = _read_pedido_csv(raw, f["name"])
        if df is not None:
            df["_source_file"] = f["name"]
            dfs.append(df)

    for folder in subfolders:
        # Filtra subpasta pelo ano se especificado (ex: só "2025-XX")
        if year_filter and not folder["name"].startswith(str(year_filter)):
            print(f"    Ignorando pasta '{folder['name']}' (não é do ano {year_filter}).")
            continue
        print(f"    Subpasta Pedido: {folder['name']}")
        sub_items = _list_folder_items(drive, folder["id"])
        for f in sub_items:
            if f["mimeType"] == "application/vnd.google-apps.folder":
                continue
            if not f["name"].lower().endswith(".csv"):
                continue
            print(f"      Baixando {f['name']} ...")
            raw = _download_file_bytes(drive, f["id"])
            df = _read_pedido_csv(raw, f["name"])
            if df is not None:
                df["_source_file"] = f["name"]
                dfs.append(df)

    if not dfs:
        print("    [AVISO] Nenhum CSV de Pedido encontrado.")
        return pd.DataFrame()

    result = pd.concat(dfs, ignore_index=True)
    print(f"    Total Pedido: {len(result):,} linhas de {len(dfs)} arquivo(s).")
    return result


# ─── Data cleaning ─────────────────────────────────────────────────────────────

def _clean_consulta(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    if "No." in df.columns:
        df["_nota_key"] = (
            df["No."].astype(str).str.strip().str.replace(r"\D", "", regex=True)
        )
        df["_nota_key"] = pd.to_numeric(df["_nota_key"], errors="coerce")

    if "Créditos" in df.columns and df["Créditos"].dtype == object:
        df["Créditos"] = (
            df["Créditos"].astype(str)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip()
        )
        df["Créditos"] = pd.to_numeric(df["Créditos"], errors="coerce").fillna(0.0)

    if "Valor NF" in df.columns and df["Valor NF"].dtype == object:
        df["Valor NF"] = (
            df["Valor NF"].astype(str)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip()
        )
        df["Valor NF"] = pd.to_numeric(df["Valor NF"], errors="coerce").fillna(0.0)

    if "CNPJ emit." in df.columns:
        df["_cnpj_key"] = (
            df["CNPJ emit."].astype(str).str.replace(r"\D", "", regex=True).str.strip()
        )

    # ── Série: CNPJ + Nº + Valor (2 dec) + Mês(DataEmissão) ────────────────
    if "Data Emissão" in df.columns:
        _de = pd.to_datetime(df["Data Emissão"], dayfirst=True, errors="coerce")
        df["_mes_emissao"] = _de.dt.month.astype("Int64")
    else:
        df["_mes_emissao"] = pd.NA

    if "_nota_key" in df.columns and "_cnpj_key" in df.columns and "Valor NF" in df.columns:
        _vr = pd.to_numeric(df["Valor NF"], errors="coerce").round(2)
        df["_serie"] = (
            df["_cnpj_key"].astype(str) + "_" +
            df["_nota_key"].astype(str) + "_" +
            _vr.astype(str) + "_" +
            df["_mes_emissao"].astype(str)
        )

    return df


def _clean_pedido(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]

    if "Número da Nota" in df.columns:
        df["_nota_key"] = (
            df["Número da Nota"].astype(str).str.strip().str.replace(r"\D", "", regex=True)
        )
        df["_nota_key"] = pd.to_numeric(df["_nota_key"], errors="coerce")

    if "Valor da Nota" in df.columns:
        df["Valor da Nota"] = (
            df["Valor da Nota"].astype(str)
            .str.replace("R$", "", regex=False)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip()
        )
        df["Valor da Nota"] = pd.to_numeric(df["Valor da Nota"], errors="coerce").fillna(0.0)

    if "CNPJ Estabelecimento" in df.columns:
        df["_cnpj_key"] = (
            df["CNPJ Estabelecimento"].astype(str).str.replace(r"\D", "", regex=True).str.strip()
        )

    if "Data da Nota" in df.columns:
        df["_data_nota"] = pd.to_datetime(df["Data da Nota"], dayfirst=True, errors="coerce")

    # ── Série: CNPJ_estab + Nº + Valor (2 dec) + Mês(DataNota) ─────────────
    if "_data_nota" in df.columns and "_nota_key" in df.columns and "_cnpj_key" in df.columns and "Valor da Nota" in df.columns:
        df["_mes_nota"] = df["_data_nota"].dt.month.astype("Int64")
        _vp = pd.to_numeric(df["Valor da Nota"], errors="coerce").round(2)
        df["_serie"] = (
            df["_cnpj_key"].astype(str) + "_" +
            df["_nota_key"].astype(str) + "_" +
            _vp.astype(str) + "_" +
            df["_mes_nota"].astype(str)
        )

    return df


def _mask_cpf(cpf: str) -> str:
    cpf = str(cpf).strip()
    if len(cpf) == 14 and cpf[3] == "." and cpf[7] == "." and cpf[11] == "-":
        return cpf[:4] + "***." + "***" + cpf[10:]
    digits = cpf.replace(".", "").replace("-", "")
    if len(digits) == 11:
        return f"{digits[:3]}.***.*{digits[9:]}"
    return cpf[:3] + "***" + cpf[-3:] if len(cpf) >= 6 else cpf


def _month_sort_key(month_label: str) -> Tuple[int, int]:
    abbr_to_num = {v: k for k, v in MONTH_ABBR_MAP.items()}
    parts = month_label.split()
    if len(parts) == 2:
        abbr, year_str = parts
        try:
            return (int(year_str), abbr_to_num.get(abbr, 0))
        except ValueError:
            pass
    return (0, 0)


# ─── Join & Analysis ───────────────────────────────────────────────────────────

def join_and_analyze(df_consulta: pd.DataFrame, df_pedido: pd.DataFrame) -> dict:
    print("\nLimpando dados...")
    df_c = _clean_consulta(df_consulta) if "_serie" not in df_consulta.columns else df_consulta
    df_p = _clean_pedido(df_pedido) if not df_pedido.empty else df_pedido

    total_notas_consulta = len(df_c)
    total_notas_pedido = len(df_p)
    print(f"  Consulta: {total_notas_consulta:,} linhas")
    print(f"  Pedido  : {total_notas_pedido:,} linhas")

    # ── JOIN ──────────────────────────────────────────────────────────────────
    print("Realizando JOIN por Série (CNPJ + Nº + Valor + Mês)...")
    has_key_c = "_nota_key" in df_c.columns and not df_c["_nota_key"].isna().all()
    has_key_p = "_nota_key" in df_p.columns and not df_p["_nota_key"].isna().all() if not df_p.empty else False

    if has_key_c and has_key_p:
        has_serie = "_serie" in df_c.columns and "_serie" in df_p.columns
        if has_serie:
            join_keys = ["_serie"]
            dedup_key = ["_serie"]
            print("  Usando chave Série (CNPJ + Nº + Valor + Mês).")
        else:
            has_cnpj = "_cnpj_key" in df_c.columns and "_cnpj_key" in df_p.columns
            join_keys = ["_nota_key", "_cnpj_key"] if has_cnpj else ["_nota_key"]
            dedup_key = join_keys
            print("  [AVISO] _serie ausente – usando chave parcial.")

        df_joined = pd.merge(df_c, df_p, on=join_keys, how="left", suffixes=("_c", "_p"))
        df_joined = df_joined.drop_duplicates(subset=dedup_key)

        cpf_col_check = "CPF Doador/Cadastrador"
        notas_matched = int(df_joined[cpf_col_check].notna().sum()) if cpf_col_check in df_joined.columns else int(df_joined["_nota_key"].notna().sum())
    else:
        print("  [AVISO] Chave de join ausente. Usando apenas Consulta.")
        df_joined = df_c.copy()
        notas_matched = 0

    taxa_match = (notas_matched / total_notas_consulta * 100) if total_notas_consulta else 0.0
    print(f"  Matches: {notas_matched:,} / {total_notas_consulta:,} ({taxa_match:.1f}%)")

    # ── Créditos ──────────────────────────────────────────────────────────────
    creditos_col = "Créditos" if "Créditos" in df_joined.columns else None
    total_creditos = float(df_joined[creditos_col].sum()) if creditos_col else 0.0

    # Aceita "Calculado" (2026) e "Liberado" (2025) — ambos representam crédito válido
    situacao_col = "Situação do Crédito" if "Situação do Crédito" in df_joined.columns else None
    if situacao_col:
        mask_aceita = df_joined[situacao_col].isin(["Calculado", "Liberado"])
        notas_aceitas = int(mask_aceita.sum())
        creditos_aceitos = float(df_joined.loc[mask_aceita, creditos_col].sum()) if creditos_col else 0.0
    else:
        mask_aceita = pd.Series([True] * len(df_joined))
        notas_aceitas = len(df_joined)
        creditos_aceitos = total_creditos

    creditos_rejeitados = total_creditos - creditos_aceitos
    taxa_aceitacao = (notas_aceitas / total_notas_consulta * 100) if total_notas_consulta else 0.0

    # ── CPFs únicos ───────────────────────────────────────────────────────────
    cpf_col = "CPF Doador/Cadastrador" if "CPF Doador/Cadastrador" in df_joined.columns else None
    cpfs_series = df_joined[cpf_col].dropna() if cpf_col else pd.Series([], dtype=str)
    cpfs_unicos = int(cpfs_series.nunique())

    # ── Tipo de doação ────────────────────────────────────────────────────────
    tipo_col = "Tipo da Doação" if "Tipo da Doação" in df_joined.columns else None
    if tipo_col and creditos_col:
        mask_auto = df_joined[tipo_col] == "DOACAO_AUTOMATICA"
        creditos_automaticos = float(df_joined.loc[mask_auto, creditos_col].sum())
        creditos_digitados = float(df_joined.loc[~mask_auto, creditos_col].sum())
        notas_automaticas = int(mask_auto.sum())
        notas_digitadas = int((~mask_auto).sum())
    else:
        creditos_automaticos = 0.0
        creditos_digitados = total_creditos
        notas_automaticas = 0
        notas_digitadas = total_notas_consulta

    ticket_automatico = (creditos_automaticos / notas_automaticas) if notas_automaticas else 0.0
    ticket_digitado = (creditos_digitados / notas_digitadas) if notas_digitadas else 0.0
    ticket_geral = total_creditos / total_notas_consulta if total_notas_consulta else 0.0

    # ── Meses ─────────────────────────────────────────────────────────────────
    data_col = "_data_nota"
    if data_col in df_joined.columns and not df_joined[data_col].isna().all():
        df_joined["_month_label"] = df_joined[data_col].apply(
            lambda d: f"{MONTH_ABBR_MAP.get(d.month, '?')} {d.year}" if pd.notna(d) else None
        )
    elif "Data Emissão" in df_joined.columns:
        _parsed = pd.to_datetime(df_joined["Data Emissão"], dayfirst=True, errors="coerce")
        df_joined["_month_label"] = _parsed.apply(
            lambda d: f"{MONTH_ABBR_MAP.get(d.month, '?')} {d.year}" if pd.notna(d) else None
        )
    else:
        today = datetime.date.today()
        df_joined["_month_label"] = f"{MONTH_ABBR_MAP[today.month]} {today.year}"

    months_present = sorted(
        [m for m in df_joined["_month_label"].dropna().unique()],
        key=_month_sort_key,
    )
    n_meses = len(months_present) if months_present else 1
    media_mensal_creditos = total_creditos / n_meses

    creditos_por_mes: Dict[str, float] = {}
    cpfs_por_mes: Dict[str, int] = {}
    creditos_auto_por_mes: Dict[str, float] = {}
    creditos_dig_por_mes: Dict[str, float] = {}
    for mo in months_present:
        sub = df_joined[df_joined["_month_label"] == mo]
        creditos_por_mes[mo] = float(sub[creditos_col].sum()) if creditos_col else 0.0
        cpfs_por_mes[mo] = int(sub[cpf_col].nunique()) if cpf_col else 0
        if tipo_col and creditos_col:
            creditos_auto_por_mes[mo] = float(sub.loc[sub[tipo_col] == "DOACAO_AUTOMATICA", creditos_col].sum())
            creditos_dig_por_mes[mo] = float(sub.loc[sub[tipo_col] != "DOACAO_AUTOMATICA", creditos_col].sum())

    if months_present:
        periodo = f"{months_present[0]} – {months_present[-1]}"
    else:
        today = datetime.date.today()
        periodo = f"{MONTH_FULL_PT[today.month]} {today.year}"

    # ── Top emitentes ─────────────────────────────────────────────────────────
    top_emitentes: List[dict] = []
    emitente_col = "Emitente" if "Emitente" in df_joined.columns else None
    cnpj_col_c = "CNPJ emit." if "CNPJ emit." in df_joined.columns else None
    if emitente_col and creditos_col:
        grp_cols = [emitente_col]
        if cnpj_col_c:
            grp_cols.append(cnpj_col_c)
        agg = df_joined.groupby(grp_cols).agg(
            n_notas=(creditos_col, "count"),
            creditos=(creditos_col, "sum"),
        ).reset_index()
        agg["ticket_medio"] = agg["creditos"] / agg["n_notas"]
        agg = agg.sort_values("creditos", ascending=False)
        for _, row in agg.head(15).iterrows():
            top_emitentes.append({
                "emitente": str(row[emitente_col]),
                "cnpj": str(row[cnpj_col_c]) if cnpj_col_c else "",
                "n_notas": int(row["n_notas"]),
                "creditos": float(row["creditos"]),
                "ticket_medio": float(row["ticket_medio"]),
            })

    # ── Top CPFs ──────────────────────────────────────────────────────────────
    top_cpfs: List[dict] = []
    if cpf_col and creditos_col:
        cpf_grp = df_joined.groupby(cpf_col).agg(
            n_notas=(creditos_col, "count"),
            creditos=(creditos_col, "sum"),
        ).reset_index()
        cpf_grp = cpf_grp.sort_values("creditos", ascending=False)
        for _, row in cpf_grp.head(10).iterrows():
            top_cpfs.append({
                "cpf_masked": _mask_cpf(str(row[cpf_col])),
                "n_notas": int(row["n_notas"]),
                "creditos": float(row["creditos"]),
            })

    cpfs_ultimo_mes = 0
    if months_present and cpf_col:
        ultimo_mes = months_present[-1]
        cpfs_ultimo_mes = int(df_joined[df_joined["_month_label"] == ultimo_mes][cpf_col].nunique())

    razao_ticket = (ticket_automatico / ticket_digitado) if ticket_digitado else 0.0

    return {
        "total_notas_consulta": total_notas_consulta,
        "total_notas_pedido": total_notas_pedido,
        "notas_matched": notas_matched,
        "notas_nao_matched": total_notas_consulta - notas_matched,
        "taxa_match": round(taxa_match, 1),
        "total_creditos": total_creditos,
        "creditos_aceitos": creditos_aceitos,
        "creditos_rejeitados": creditos_rejeitados,
        "notas_aceitas": notas_aceitas,
        "notas_rejeitadas": total_notas_consulta - notas_aceitas,
        "taxa_aceitacao": round(taxa_aceitacao, 1),
        "cpfs_unicos": cpfs_unicos,
        "cpfs_ultimo_mes": cpfs_ultimo_mes,
        "creditos_automaticos": creditos_automaticos,
        "creditos_digitados": creditos_digitados,
        "notas_automaticas": notas_automaticas,
        "notas_digitadas": notas_digitadas,
        "ticket_automatico": ticket_automatico,
        "ticket_digitado": ticket_digitado,
        "ticket_geral": ticket_geral,
        "razao_ticket": razao_ticket,
        "media_mensal_creditos": media_mensal_creditos,
        "n_meses": n_meses,
        "periodo": periodo,
        "months_present": months_present,
        "creditos_por_mes": creditos_por_mes,
        "cpfs_por_mes": cpfs_por_mes,
        "creditos_auto_por_mes": creditos_auto_por_mes,
        "creditos_dig_por_mes": creditos_dig_por_mes,
        "top_emitentes": top_emitentes,
        "top_cpfs": top_cpfs,
    }


# ─── Formatação ────────────────────────────────────────────────────────────────

def _fmt_brl(value: float) -> str:
    formatted = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    prefix = "-R$ " if value < 0 else "R$ "
    return prefix + formatted


def _fmt_short(value: float) -> str:
    if value >= 1_000_000:
        return f"R${value/1_000_000:.1f}Mi".replace(".", ",")
    if value >= 1_000:
        return f"R${value/1_000:.1f}K".replace(".", ",")
    return f"R${value:.0f}"


# ─── HTML Report ───────────────────────────────────────────────────────────────

def generate_html_report(metrics: dict, output_path: str) -> None:
    def _fmt_brl(val: float) -> str:
        if val >= 1_000_000:
            return f"R${val/1_000_000:.2f}Mi".replace(".", ",")
        if val >= 1_000:
            return f"R${val/1_000:.1f}K".replace(".", ",")
        return f"R${val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _fmt_num(val: float) -> str:
        if val >= 1_000_000:
            return f"{val/1_000_000:.1f}Mi".replace(".", ",")
        if val >= 1_000:
            return f"{val/1_000:.0f}K"
        return str(int(val))

    if not metrics:
        print("[ERRO] Sem dados para gerar relatório.")
        return

    m = metrics
    periodo              = m.get("periodo", "N/A")
    n_meses              = m.get("n_meses", 1)
    months_present       = m.get("months_present", [])
    total_creditos       = m.get("total_creditos", 0.0)
    total_notas_consulta = m.get("total_notas_consulta", 0)
    total_notas_pedido   = m.get("total_notas_pedido", 0)
    notas_matched        = m.get("notas_matched", 0)
    notas_nao_matched    = m.get("notas_nao_matched", total_notas_consulta - notas_matched)
    taxa_match           = m.get("taxa_match", 0.0)
    notas_aceitas        = m.get("notas_aceitas", 0)
    notas_rejeitadas     = m.get("notas_rejeitadas", 0)
    taxa_aceitacao       = m.get("taxa_aceitacao", 0.0)
    creditos_rejeitados  = m.get("creditos_rejeitados", 0.0)
    cpfs_unicos          = m.get("cpfs_unicos", 0)
    cpfs_ultimo_mes      = m.get("cpfs_ultimo_mes", 0)
    media_mensal         = m.get("media_mensal_creditos", 0.0)
    creditos_automaticos = m.get("creditos_automaticos", 0.0)
    creditos_digitados   = m.get("creditos_digitados", 0.0)
    notas_automaticas    = m.get("notas_automaticas", 0)
    notas_digitadas      = m.get("notas_digitadas", 0)
    ticket_automatico    = m.get("ticket_automatico", 0.0)
    ticket_digitado      = m.get("ticket_digitado", 0.0)
    razao_ticket         = m.get("razao_ticket", 0.0)
    creditos_por_mes     = m.get("creditos_por_mes", {})
    cpfs_por_mes         = m.get("cpfs_por_mes", {})
    creditos_auto_por_mes = m.get("creditos_auto_por_mes", {})
    creditos_dig_por_mes  = m.get("creditos_dig_por_mes", {})
    top_emitentes        = m.get("top_emitentes", [])
    top_cpfs             = m.get("top_cpfs", [])

    hoje      = datetime.date.today()
    ano_atual = hoje.year

    taxa_rejeicao   = round(100.0 - taxa_aceitacao, 1)
    pct_nao_matched = round(100.0 - taxa_match, 1)

    cpf_values = [cpfs_por_mes.get(mo, 0) for mo in months_present]
    crescimento_cpfs = (cpf_values[-1] - cpf_values[-2]) if len(cpf_values) >= 2 else 0

    chart_labels_js   = json.dumps(months_present)
    chart_creditos_js = json.dumps([round(creditos_por_mes.get(mo, 0.0), 2) for mo in months_present])
    chart_cpfs_js     = json.dumps([cpfs_por_mes.get(mo, 0) for mo in months_present])
    chart_auto_js     = json.dumps([round(creditos_auto_por_mes.get(mo, 0.0), 2) for mo in months_present])
    chart_dig_js      = json.dumps([round(creditos_dig_por_mes.get(mo, 0.0), 2) for mo in months_present])
    top15_labels      = json.dumps([e["emitente"][:30] for e in top_emitentes])
    top15_creditos_js = json.dumps([round(e["creditos"], 2) for e in top_emitentes])

    top_emitentes_rows = ""
    for idx, e in enumerate(top_emitentes):
        row_bg = "background:#F7F7F7;" if idx % 2 == 1 else ""
        top_emitentes_rows += (
            f"<tr style='{row_bg}'>"
            f"<td>{e['emitente'][:40]}</td>"
            f"<td style='text-align:center'>{e['n_notas']:,}</td>"
            f"<td>{_fmt_brl(e['creditos'])}</td>"
            f"<td>{_fmt_brl(e['ticket_medio'])}</td>"
            f"</tr>\n"
        )

    top_cpfs_rows = ""
    for i, c in enumerate(top_cpfs):
        row_bg = "background:#F7F7F7;" if i % 2 == 1 else ""
        pct = c["creditos"] / total_creditos * 100 if total_creditos else 0
        top_cpfs_rows += (
            f"<tr style='{row_bg}'>"
            f"<td style='text-align:center;color:#666666'>{i+1}</td>"
            f"<td style='font-family:monospace'>{c['cpf_masked']}</td>"
            f"<td style='text-align:center'>{c['n_notas']:,}</td>"
            f"<td>{_fmt_brl(c['creditos'])}</td>"
            f"<td style='text-align:center;color:#666666'>{pct:.1f}%</td>"
            f"</tr>\n"
        )

    proj_acumulado = 0.0
    proj_rows = ""
    proj_labels_list = []
    proj_receita_list = []
    for row in PROJ_2026:
        mes_lbl, cpfs_add, total_cpfs_p, cpfs_ger, rec_est = row
        proj_acumulado += rec_est
        proj_labels_list.append(mes_lbl)
        proj_receita_list.append(round(rec_est, 2))
        highlight = ""
        if mes_lbl == "Set/2026":
            highlight = "background:#FFF8EC;font-weight:600;"
        elif mes_lbl == "Dez/2026":
            highlight = "background:#FFF3E0;font-weight:700;"
        proj_rows += (
            f"<tr style='{highlight}'>"
            f"<td>{mes_lbl}</td>"
            f"<td style='text-align:center;color:#666666'>{'+'+str(cpfs_add) if cpfs_add else '–'}</td>"
            f"<td style='text-align:center'>{total_cpfs_p}</td>"
            f"<td style='text-align:center'>{cpfs_ger if cpfs_ger else '–'}</td>"
            f"<td>{_fmt_brl(rec_est) if rec_est else '–'}</td>"
            f"<td>{_fmt_brl(proj_acumulado) if proj_acumulado else '–'}</td>"
            f"</tr>\n"
        )
    proj_labels_js  = json.dumps(proj_labels_list)
    proj_receita_js = json.dumps(proj_receita_list)

    pct_auto = (creditos_automaticos / total_creditos * 100) if total_creditos else 0.0
    pct_dig  = (creditos_digitados  / total_creditos * 100) if total_creditos else 0.0

    donut_labels = json.dumps([c["cpf_masked"] for c in top_cpfs[:5]])
    donut_data   = json.dumps([round(c["creditos"], 2) for c in top_cpfs[:5]])

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Relatório NFP · AFESU · {periodo}</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;0,900;1,400&display=swap" rel="stylesheet" />
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --white: #FFFFFF; --bg-panel: #F7F7F7; --border: #E8E8E8;
  --text: #1A1A1A; --muted: #666666; --orange: #F0A020;
  --orange-lt: #FFF8EC; --black: #000000;
}}
html, body {{ font-family: 'Inter', sans-serif; background: var(--white); color: var(--text); overflow: hidden; height: 100%; margin: 0; }}
#slider {{ display: flex; flex-direction: row; width: 100vw; height: 100vh; overflow-x: scroll; overflow-y: hidden; scroll-snap-type: x mandatory; scroll-behavior: smooth; -webkit-overflow-scrolling: touch; }}
.slide {{ flex: none; width: 100vw; height: 100vh; overflow-y: auto; padding: 56px 60px 44px; display: flex; flex-direction: column; justify-content: center; scroll-snap-align: start; position: relative; background: var(--white); box-sizing: border-box; }}
.slide-label {{ font-size: 10px; font-weight: 700; letter-spacing: 3px; color: var(--orange); text-transform: uppercase; margin-bottom: 10px; }}
h1 {{ font-size: clamp(2.4rem,5vw,4rem); font-weight: 900; line-height: 1.08; color: var(--black); letter-spacing: -1.5px; }}
h2 {{ font-size: clamp(1.4rem,2.5vw,2rem); font-weight: 800; color: var(--black); letter-spacing: -0.5px; margin-bottom: 4px; }}
.subtitle {{ color: var(--muted); font-size: 13px; margin-bottom: 28px; font-weight: 400; }}
.orange {{ color: var(--orange); }} .muted {{ color: var(--muted); }} .black {{ color: var(--black); }}
.divider {{ height: 1px; background: var(--border); margin: 20px 0; }}
.pill-row {{ display: flex; gap: 14px; flex-wrap: wrap; }}
.pill {{ flex: 1; min-width: 160px; background: var(--white); border: 1.5px solid var(--orange); border-radius: 12px; padding: 18px 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.pill-val {{ font-size: clamp(1rem,1.8vw,1.6rem); font-weight: 900; color: var(--orange); line-height: 1; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.pill-lbl {{ font-size: 10px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; color: var(--muted); }}
.kpi-row {{ display: grid; gap: 16px; }}
.k4 {{ grid-template-columns: repeat(4,1fr); }} .k3 {{ grid-template-columns: repeat(3,1fr); }} .k2 {{ grid-template-columns: repeat(2,1fr); }}
.kcard {{ background: var(--white); border: 1px solid var(--border); border-radius: 12px; padding: 20px 18px; position: relative; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.kcard-dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--orange); margin-bottom: 12px; }}
.kcard-dot.gray {{ background: var(--muted); }}
.kcard-lbl {{ font-size: 10px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; color: var(--muted); margin-bottom: 8px; }}
.kcard-val {{ font-size: clamp(1.4rem,2.2vw,2rem); font-weight: 900; color: var(--black); line-height: 1; }}
.kcard-val.orange {{ color: var(--orange); }}
.kcard-sub {{ font-size: 11px; color: var(--muted); margin-top: 6px; }}
.kbadge {{ position: absolute; top: 14px; right: 14px; font-size: 10px; font-weight: 700; padding: 3px 9px; border-radius: 20px; }}
.kbadge.green {{ background: rgba(0,180,80,.1); color: #00a84f; }} .kbadge.gray {{ background: var(--bg-panel); color: var(--muted); }} .kbadge.warn {{ background: rgba(240,100,0,.1); color: #e06000; }}
.chart-area {{ background: var(--bg-panel); border-radius: 12px; padding: 20px 20px 16px; margin-top: 18px; }}
.chart-area canvas {{ max-height: 260px; }}
.two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
.three-col {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
.modal-card {{ background: var(--white); border: 1px solid var(--border); border-left: 4px solid var(--orange); border-radius: 12px; padding: 24px 22px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.modal-card.gray-accent {{ border-left-color: var(--muted); }}
.modal-card-tag {{ font-size: 10px; font-weight: 800; letter-spacing: 2px; text-transform: uppercase; color: var(--muted); margin-bottom: 10px; }}
.modal-val {{ font-size: clamp(1.6rem,2.6vw,2.2rem); font-weight: 900; color: var(--black); line-height: 1; margin-bottom: 14px; }}
.modal-val.orange {{ color: var(--orange); }}
.modal-row {{ display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); padding: 7px 0; border-top: 1px solid var(--border); }}
.modal-row span:last-child {{ color: var(--text); font-weight: 600; }}
.ticket-hl {{ text-align: center; padding: 14px 0; }}
.ticket-hl .big-x {{ font-size: clamp(2rem,4vw,3.2rem); font-weight: 900; color: var(--orange); line-height: 1; }}
.ticket-hl p {{ font-size: 11px; color: var(--muted); margin-top: 4px; }}
.tbl {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
.tbl th {{ background: var(--bg-panel); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; padding: 11px 14px; text-align: left; color: var(--muted); border-bottom: 1px solid var(--border); }}
.tbl td {{ padding: 10px 14px; color: var(--text); }}
.tbl tr:not(:last-child) td {{ border-bottom: 1px solid var(--border); }}
.tbl-wrap {{ background: var(--white); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; overflow-y: auto; max-height: 360px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.match-big {{ font-size: clamp(3rem,6vw,5rem); font-weight: 900; color: var(--black); line-height: 1; letter-spacing: -2px; }}
.match-big span {{ color: var(--orange); }}
.info-box {{ background: var(--bg-panel); border: 1px solid var(--border); border-left: 3px solid var(--orange); border-radius: 10px; padding: 14px 18px; font-size: 12px; color: var(--muted); line-height: 1.7; }}
.info-box strong {{ color: var(--text); }}
.metric-row {{ display: flex; gap: 14px; flex-wrap: wrap; margin: 14px 0; }}
.metric-pill {{ flex: 1; min-width: 110px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; text-align: center; }}
.metric-pill .mpv {{ font-size: 1.5rem; font-weight: 900; color: var(--black); line-height: 1; }}
.metric-pill .mpl {{ font-size: 10px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: var(--muted); margin-top: 4px; }}
.capa-inner {{ max-width: 900px; }}
.capa-tagline {{ font-size: 10px; font-weight: 700; letter-spacing: 3px; text-transform: uppercase; color: var(--orange); margin-bottom: 18px; }}
.logo-text {{ font-size: 1.1rem; font-weight: 900; color: var(--black); letter-spacing: -0.5px; }}
.slide-foot {{ margin-top: auto; padding-top: 20px; font-size: 10px; color: var(--muted); letter-spacing: 2px; text-transform: uppercase; display: flex; justify-content: space-between; align-items: center; }}
.slide-foot .logo-text {{ font-size: 14px; }}
#nav {{ position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; flex-direction: row; gap: 10px; z-index: 200; background: rgba(255,255,255,0.7); padding: 8px 14px; border-radius: 20px; backdrop-filter: blur(4px); }}
.dot-btn {{ width: 10px; height: 10px; border-radius: 50%; background: var(--border); border: none; cursor: pointer; transition: all .25s; padding: 0; }}
.dot-btn.on {{ background: var(--orange); transform: scale(1.3); }}
.slide-close {{ align-items: center; text-align: center; }}
@media (max-width: 960px) {{
  .slide {{ padding: 40px 24px 32px; }}
  .k4,.k3 {{ grid-template-columns: repeat(2,1fr); }}
  .two-col,.three-col {{ grid-template-columns: 1fr; }}
  #nav {{ display: none; }}
}}
</style>
</head>
<body>

<div id="nav">
  <button class="dot-btn on" onclick="go(0)" title="Capa"></button>
  <button class="dot-btn"   onclick="go(1)" title="Visão Geral"></button>
  <button class="dot-btn"   onclick="go(2)" title="Modalidades"></button>
  <button class="dot-btn"   onclick="go(3)" title="Contribuintes"></button>
  <button class="dot-btn"   onclick="go(4)" title="Estabelecimentos"></button>
  <button class="dot-btn"   onclick="go(5)" title="Qualidade"></button>
  <button class="dot-btn"   onclick="go(6)" title="Projeção 2026"></button>
  <button class="dot-btn"   onclick="go(7)" title="Encerramento"></button>
</div>

<div id="slider">

<!-- SLIDE 1 · CAPA -->
<section class="slide" id="s0">
  <div class="capa-inner">
    <p class="capa-tagline">TIME CAPTAÇÃO</p>
    <h1>Programa<br>Nota Fiscal Paulista<br><span class="orange" style="font-size:1.15em;">AFESU</span></h1>
    <p style="color:var(--muted);font-size:13px;margin:12px 0 36px;line-height:1.8;">
      Análise consolidada &middot; Elaborado pelo Time de Captação<br>
      <span style="color:var(--muted);">{periodo}</span>
    </p>
    <div class="pill-row">
      <div class="pill"><div class="pill-val">{_fmt_brl(total_creditos)}</div><div class="pill-lbl">Créditos gerados</div></div>
      <div class="pill"><div class="pill-val">{_fmt_num(total_notas_pedido)}</div><div class="pill-lbl">Pedidos processados</div></div>
      <div class="pill"><div class="pill-val">{cpfs_unicos}</div><div class="pill-lbl">CPFs ativos</div></div>
      <div class="pill"><div class="pill-val">{n_meses}</div><div class="pill-lbl">Meses analisados</div></div>
    </div>
  </div>
  <div class="slide-foot">
    <span>AFESU &middot; Nota Fiscal Paulista &middot; {periodo}</span>
    <span class="logo-text">TIME</span>
  </div>
</section>

<!-- SLIDE 2 · VISÃO GERAL -->
<section class="slide" id="s1">
  <p class="slide-label">01 &middot; VISÃO GERAL</p>
  <h2>Resultados Consolidados do Programa NFP</h2>
  <p class="subtitle">{periodo}</p>
  <div class="kpi-row k4">
    <div class="kcard">
      <div class="kcard-dot"></div>
      <p class="kcard-lbl">Créditos Totais</p>
      <p class="kcard-val orange">{_fmt_brl(total_creditos)}</p>
      <p class="kcard-sub">Acumulado no período</p>
    </div>
    <div class="kcard">
      <div class="kcard-dot"></div>
      <p class="kcard-lbl">Notas Aceitas (Consulta)</p>
      <p class="kcard-val">{notas_aceitas:,}</p>
      <p class="kcard-sub">de {total_notas_pedido:,} pedidos</p>
      <span class="kbadge green">{taxa_aceitacao:.1f}% aprovação</span>
    </div>
    <div class="kcard">
      <div class="kcard-dot gray"></div>
      <p class="kcard-lbl">CPFs Ativos</p>
      <p class="kcard-val">{cpfs_unicos}</p>
      <p class="kcard-sub">+{total_notas_pedido:,} total pedidos</p>
    </div>
    <div class="kcard">
      <div class="kcard-dot gray"></div>
      <p class="kcard-lbl">Média Mensal</p>
      <p class="kcard-val">{_fmt_brl(media_mensal)}</p>
      <p class="kcard-sub">em créditos</p>
    </div>
  </div>
  <div class="chart-area">
    <canvas id="chartOverview"></canvas>
  </div>
  <div class="slide-foot"><span>AFESU &middot; NFP</span><span class="logo-text">TIME</span></div>
</section>

<!-- SLIDE 3 · MODALIDADES -->
<section class="slide" id="s2">
  <p class="slide-label">02 &middot; MODALIDADES</p>
  <h2>Análise por Tipo de Doação</h2>
  <p class="subtitle">Comparativo entre doação automática e notas digitadas</p>
  <div class="two-col" style="margin-bottom:14px;align-items:start;">
    <div class="modal-card">
      <p class="modal-card-tag">Doação Automática</p>
      <div class="modal-val orange">{_fmt_brl(creditos_automaticos)}</div>
      <div class="modal-row"><span>Notas</span><span>{notas_automaticas:,}</span></div>
      <div class="modal-row"><span>Ticket médio / nota</span><span>{_fmt_brl(ticket_automatico)}</span></div>
      <div class="modal-row"><span>% dos créditos</span><span>{pct_auto:.1f}%</span></div>
    </div>
    <div class="modal-card gray-accent">
      <p class="modal-card-tag">Notas Digitadas</p>
      <div class="modal-val">{_fmt_brl(creditos_digitados)}</div>
      <div class="modal-row"><span>Notas</span><span>{notas_digitadas:,}</span></div>
      <div class="modal-row"><span>Ticket médio / nota</span><span>{_fmt_brl(ticket_digitado)}</span></div>
      <div class="modal-row"><span>% dos créditos</span><span>{pct_dig:.1f}%</span></div>
    </div>
  </div>
  <div class="ticket-hl">
    <div class="big-x">{razao_ticket:.1f}&times; maior ticket</div>
    <p>Ticket automático versus ticket de notas digitadas</p>
  </div>
  <div class="chart-area"><canvas id="chartModalidade"></canvas></div>
  <div class="slide-foot"><span>AFESU &middot; NFP</span><span class="logo-text">TIME</span></div>
</section>

<!-- SLIDE 4 · CONTRIBUINTES -->
<section class="slide" id="s3">
  <p class="slide-label">03 &middot; CONTRIBUINTES</p>
  <h2>Base de Contribuintes Ativos</h2>
  <p class="subtitle">Análise dos doadores identificados via cruzamento de dados</p>
  <div class="kpi-row k3" style="margin-bottom:18px;">
    <div class="kcard">
      <div class="kcard-dot"></div>
      <p class="kcard-lbl">CPFs únicos</p>
      <p class="kcard-val orange">{cpfs_unicos}</p>
      <p class="kcard-sub">Total no período</p>
    </div>
    <div class="kcard">
      <div class="kcard-dot gray"></div>
      <p class="kcard-lbl">CPFs ativos — último mês</p>
      <p class="kcard-val">{cpfs_ultimo_mes}</p>
      <p class="kcard-sub">{months_present[-1] if months_present else 'N/A'}</p>
      <span class="kbadge {'green' if crescimento_cpfs >= 0 else 'warn'}">{'+'if crescimento_cpfs >= 0 else ''}{crescimento_cpfs}</span>
    </div>
    <div class="kcard">
      <div class="kcard-dot gray"></div>
      <p class="kcard-lbl">Crédito médio / CPF</p>
      <p class="kcard-val">{_fmt_brl(total_creditos/cpfs_unicos if cpfs_unicos else 0)}</p>
      <p class="kcard-sub">No período completo</p>
    </div>
  </div>
  <div class="two-col" style="align-items:start;">
    <div class="tbl-wrap">
      <table class="tbl">
        <thead><tr><th>#</th><th>CPF</th><th>Notas</th><th>Crédito Total</th><th>% do total</th></tr></thead>
        <tbody>{top_cpfs_rows}</tbody>
      </table>
    </div>
    <div style="display:flex;flex-direction:column;gap:0;">
      <p style="font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:12px;">Top 5 por crédito</p>
      <div style="position:relative;height:220px;"><canvas id="chartDonut"></canvas></div>
    </div>
  </div>
  <div class="slide-foot"><span>AFESU &middot; CPF mascarado para privacidade</span><span class="logo-text">TIME</span></div>
</section>

<!-- SLIDE 5 · ESTABELECIMENTOS -->
<section class="slide" id="s4">
  <p class="slide-label">04 &middot; ESTABELECIMENTOS</p>
  <h2>Análise por Estabelecimento</h2>
  <p class="subtitle">Top 15 emitentes por crédito gerado para a AFESU</p>
  <div style="background:var(--white);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:18px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
    <canvas id="chartEmitentes" style="max-height:240px;"></canvas>
  </div>
  <div class="tbl-wrap">
    <table class="tbl">
      <thead><tr><th>Emitente</th><th>Nº Notas</th><th>Crédito Total (R$)</th><th>Ticket Médio</th></tr></thead>
      <tbody>{top_emitentes_rows}</tbody>
    </table>
  </div>
  <div class="slide-foot"><span>AFESU &middot; NFP</span><span class="logo-text">TIME</span></div>
</section>

<!-- SLIDE 6 · QUALIDADE -->
<section class="slide" id="s5">
  <p class="slide-label">05 &middot; QUALIDADE</p>
  <h2>Integridade do Cruzamento de Dados</h2>
  <p class="subtitle">Cobertura do JOIN Consulta × Pedido e situação dos créditos</p>
  <div style="margin:10px 0 20px;">
    <div class="match-big">{taxa_match:.1f}<span>%</span></div>
    <p style="font-size:14px;color:var(--muted);margin-top:6px;">de cobertura no cruzamento das bases</p>
  </div>
  <div class="metric-row">
    <div class="metric-pill"><div class="mpv">{notas_aceitas:,}</div><div class="mpl">Notas Consulta</div></div>
    <div class="metric-pill"><div class="mpv">{total_notas_pedido:,}</div><div class="mpl">Notas Pedido</div></div>
    <div class="metric-pill"><div class="mpv" style="color:var(--orange);">{notas_matched:,}</div><div class="mpl">Matched</div></div>
    <div class="metric-pill"><div class="mpv" style="color:var(--muted);">{notas_nao_matched:,}</div><div class="mpl">Não matched</div></div>
  </div>
  <div class="two-col" style="align-items:start;margin-top:6px;">
    <div>
      <p style="font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:10px;">Situação dos créditos</p>
      <div class="kpi-row k2" style="gap:12px;">
        <div class="kcard">
          <p class="kcard-lbl">Aceitas</p>
          <p class="kcard-val orange">{notas_aceitas:,}</p>
          <p class="kcard-sub">créditos aprovados</p>
          <span class="kbadge green">{taxa_aceitacao:.1f}%</span>
        </div>
        <div class="kcard">
          <p class="kcard-lbl">Sem crédito</p>
          <p class="kcard-val">{notas_rejeitadas:,}</p>
          <p class="kcard-sub">{_fmt_brl(creditos_rejeitados)} não gerados</p>
          <span class="kbadge warn">{taxa_rejeicao:.1f}%</span>
        </div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:12px;">
      <div class="info-box">
        <strong>O que significa cada situação?</strong><br>
        <strong>Calculado/Liberado</strong> — crédito aprovado e disponível.<br>
        <strong>Aguardando</strong> — nota em análise pela SEFAZ.<br>
        <strong>Cancelado / Expirado</strong> — prazo perdido ou nota inválida.
      </div>
      <div class="info-box" style="border-left-color:var(--muted);">
        A diferença entre as bases decorre do lag da SEFAZ: notas emitidas nos
        últimos meses ainda não constam no arquivo de Pedido exportado.
      </div>
    </div>
  </div>
  <div class="slide-foot"><span>AFESU &middot; Margem: ±{pct_nao_matched:.1f}% (notas sem match)</span><span class="logo-text">TIME</span></div>
</section>

<!-- SLIDE 7 · PROJEÇÃO 2026 -->
<section class="slide" id="s6">
  <p class="slide-label">06 &middot; PROJEÇÃO</p>
  <h2>Meta: 500 CPFs &middot; Doação Automática</h2>
  <p class="subtitle">Base: 199 CPFs &middot; +38/mês a partir de Maio &middot; R$74/CPF/mês &middot; lag de 4 meses</p>
  <div class="two-col" style="align-items:start;gap:20px;">
    <div style="background:var(--white);border:1px solid var(--border);border-radius:12px;padding:20px;height:300px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
      <canvas id="chartProjecao" style="height:100%;"></canvas>
    </div>
    <div class="tbl-wrap" style="max-height:300px;">
      <table class="tbl">
        <thead><tr><th>Mês</th><th>+CPFs</th><th>Total</th><th>Gerando</th><th>Receita Est.</th><th>Acumulado</th></tr></thead>
        <tbody>{proj_rows}</tbody>
      </table>
    </div>
  </div>
  <div class="slide-foot"><span>AFESU &middot; Projeção 2026 &middot; Estimativa baseada na tendência atual</span><span class="logo-text">TIME</span></div>
</section>

<!-- SLIDE 8 · ENCERRAMENTO -->
<section class="slide slide-close" id="s7">
  <p style="font-size:clamp(2rem,4vw,3rem);font-weight:300;color:var(--muted);line-height:1;">Obrigado,</p>
  <h1 style="font-size:clamp(3rem,7vw,5.5rem);color:var(--orange);letter-spacing:-2px;margin-bottom:16px;">AFESU</h1>
  <p style="font-size:14px;color:var(--muted);margin-bottom:44px;">Uma parceria construída com propósito.</p>
  <div class="pill-row" style="justify-content:center;max-width:860px;margin:0 auto 36px;">
    <div class="pill"><div class="pill-val">{_fmt_brl(total_creditos)}</div><div class="pill-lbl">Créditos totais</div></div>
    <div class="pill"><div class="pill-val">{notas_aceitas:,}</div><div class="pill-lbl">Notas aceitas</div></div>
    <div class="pill"><div class="pill-val">{cpfs_unicos}</div><div class="pill-lbl">CPFs cadastrados</div></div>
    <div class="pill"><div class="pill-val">{n_meses}</div><div class="pill-lbl">Meses analisados</div></div>
  </div>
  <p style="font-size:11px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;">
    Time de Captação &middot; {periodo} &middot; Elaborado por Data
  </p>
  <div class="slide-foot" style="margin-top:40px;width:100%;"><span></span><span class="logo-text">TIME</span></div>
</section>

</div>

<script>
const slider = document.getElementById('slider');
const slides = document.querySelectorAll('.slide');
const dots   = document.querySelectorAll('.dot-btn');
function go(i) {{ slider.scrollTo({{ left: i * window.innerWidth, behavior: 'smooth' }}); }}
const obs = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      const i = [...slides].indexOf(e.target);
      dots.forEach(d => d.classList.remove('on'));
      if (dots[i]) dots[i].classList.add('on');
    }}
  }});
}}, {{ root: slider, threshold: 0.5 }});
slides.forEach(s => obs.observe(s));

Chart.defaults.color = '#666666';
Chart.defaults.borderColor = '#E8E8E8';
Chart.defaults.font.family = 'Inter';
const ORANGE = '#F0A020', GRAY = '#CCCCCC', BLUE = '#4A90D9', GRID = '#E8E8E8';
function fmtBRL(v) {{ return 'R$ ' + v.toLocaleString('pt-BR', {{minimumFractionDigits:2,maximumFractionDigits:2}}); }}

const labels       = {chart_labels_js};
const dataCreditos = {chart_creditos_js};
const dataCPFs     = {chart_cpfs_js};
const dataAuto     = {chart_auto_js};
const dataDig      = {chart_dig_js};

new Chart(document.getElementById('chartOverview'), {{
  data: {{ labels, datasets: [
    {{ type:'bar', label:'Créditos (R$)', data:dataCreditos, backgroundColor:'rgba(240,160,32,0.75)', borderColor:ORANGE, borderWidth:0, borderRadius:4, yAxisID:'y' }},
    {{ type:'line', label:'CPFs ativos', data:dataCPFs, borderColor:BLUE, backgroundColor:'rgba(74,144,217,0.08)', pointBackgroundColor:BLUE, pointRadius:4, tension:0.35, fill:false, yAxisID:'y2' }},
  ]}},
  options: {{ responsive:true, interaction:{{mode:'index',intersect:false}},
    plugins:{{ legend:{{ labels:{{color:'#666666',boxWidth:12,font:{{size:11}}}} }} }},
    scales: {{
      x: {{ grid:{{display:false}}, ticks:{{color:'#666666',font:{{size:10}}}} }},
      y: {{ position:'left', grid:{{color:GRID}}, ticks:{{callback:v=>fmtBRL(v),color:'#666666',font:{{size:10}}}} }},
      y2: {{ position:'right', grid:{{drawOnChartArea:false}}, ticks:{{callback:v=>v+' CPFs',color:'#666666',font:{{size:10}}}} }},
    }},
  }},
}});

new Chart(document.getElementById('chartModalidade'), {{
  type:'bar',
  data:{{ labels, datasets:[
    {{ label:'Automática', data:dataAuto, backgroundColor:'rgba(240,160,32,0.8)', borderColor:ORANGE, borderWidth:0, borderRadius:3, stack:'s' }},
    {{ label:'Digitada', data:dataDig, backgroundColor:'rgba(180,180,180,0.5)', borderColor:GRAY, borderWidth:0, borderRadius:3, stack:'s' }},
  ]}},
  options:{{ responsive:true,
    plugins:{{ legend:{{ labels:{{color:'#666666',boxWidth:12,font:{{size:11}}}} }} }},
    scales:{{
      x:{{ grid:{{display:false}}, stacked:true, ticks:{{color:'#666666',font:{{size:10}}}} }},
      y:{{ grid:{{color:GRID}}, stacked:true, ticks:{{callback:v=>fmtBRL(v),color:'#666666',font:{{size:10}}}} }},
    }},
  }},
}});

const donutLabels = {donut_labels};
const donutData   = {donut_data};
if (donutData.length > 0) {{
  new Chart(document.getElementById('chartDonut'), {{
    type:'doughnut',
    data:{{ labels:donutLabels, datasets:[{{ data:donutData,
      backgroundColor:['rgba(240,160,32,0.85)','rgba(240,160,32,0.6)','rgba(240,160,32,0.4)','rgba(200,200,200,0.6)','rgba(180,180,180,0.4)'],
      borderColor:'#FFFFFF', borderWidth:2
    }}]}},
    options:{{ responsive:true, maintainAspectRatio:false,
      plugins:{{ legend:{{ position:'bottom', labels:{{color:'#666666',font:{{size:10}},boxWidth:10}} }} }},
      cutout:'62%'
    }},
  }});
}}

const emLabels = {top15_labels};
const emCreds  = {top15_creditos_js};
new Chart(document.getElementById('chartEmitentes'), {{
  type:'bar',
  data:{{ labels:emLabels, datasets:[{{ label:'Créditos (R$)', data:emCreds,
    backgroundColor:'rgba(240,160,32,0.75)', borderColor:ORANGE, borderWidth:0, borderRadius:3
  }}]}},
  options:{{ indexAxis:'y', responsive:true, maintainAspectRatio:false,
    plugins:{{ legend:{{display:false}} }},
    scales:{{
      x:{{ grid:{{color:GRID}}, ticks:{{callback:v=>'R$'+(v/1000).toFixed(1)+'K',color:'#666666',font:{{size:10}}}} }},
      y:{{ grid:{{display:false}}, ticks:{{color:'#1A1A1A',font:{{size:10}}}} }},
    }},
  }},
}});

const projLabels  = {proj_labels_js};
const projReceita = {proj_receita_js};
new Chart(document.getElementById('chartProjecao'), {{
  type:'line',
  data:{{ labels:projLabels, datasets:[{{ label:'Receita Estimada (R$)', data:projReceita,
    borderColor:ORANGE, backgroundColor:'rgba(240,160,32,0.08)',
    pointBackgroundColor:projLabels.map((l,i)=>(l==='Set/2026'||l==='Dez/2026')?'#F0A020':'rgba(240,160,32,0.5)'),
    pointRadius:projLabels.map((l,i)=>(l==='Set/2026'||l==='Dez/2026')?7:4),
    tension:0.4, fill:true, borderWidth:2,
  }}]}},
  options:{{ responsive:true, maintainAspectRatio:false,
    plugins:{{ legend:{{ labels:{{color:'#666666',font:{{size:11}}}} }} }},
    scales:{{
      x:{{ grid:{{display:false}}, ticks:{{color:'#666666',font:{{size:10}}}} }},
      y:{{ grid:{{color:GRID}}, ticks:{{callback:v=>fmtBRL(v),color:'#666666',font:{{size:10}}}} }},
    }},
  }},
}});
</script>
</body>
</html>
"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"\nRelatório salvo em: {output_path}")


# ─── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--year", type=int, default=None,
                        help="Forçar ano (ex: --year 2025 para relatório anual completo)")
    args, _ = parser.parse_known_args()

    ano_ref_run = args.year if args.year else ANO_REF

    print("=" * 60)
    print("  Rotina NFP - AFESU  |  Análise Consulta + Pedido")
    print("=" * 60)
    print(f"  Data de execução : {datetime.date.today().isoformat()}")
    if args.year:
        print(f"  Referência       : Ano completo {ano_ref_run}  [MODO MANUAL]")
    else:
        print(f"  Referência       : {MES_REF:02d}/{ANO_REF}  (hoje - 4 meses)")
    print()

    # ── Seleciona pastas com base no ano de referência ────────────────
    if ano_ref_run >= 2026:
        consulta_folder = CONSULTA_2026_FOLDER_ID
        pedido_folder   = PEDIDO_2026_FOLDER_ID
        ano_label       = "2026"
    else:
        consulta_folder = CONSULTA_2025_FOLDER_ID
        pedido_folder   = PEDIDO_2025_FOLDER_ID
        ano_label       = "2025"

    print("[1/4] Conectando ao Google Drive ...")
    drive = build_drive_service()
    print("      Autenticado com sucesso.")

    print(f"\n[2/4] Carregando CSVs de Consulta {ano_label} ...")
    print(f"  Pasta: {consulta_folder}")
    df_consulta = load_consulta_csvs(drive, consulta_folder, year_filter=ano_ref_run)
    if df_consulta.empty:
        print("[ERRO] Nenhum dado de Consulta encontrado. Abortando.")
        return
    print(f"  Total Consulta final: {len(df_consulta):,} linhas.")

    print(f"\n[3/4] Carregando CSVs de Pedido {ano_label} ...")
    print(f"  Pasta: {pedido_folder}")
    df_pedido = load_pedido_csvs(drive, pedido_folder, year_filter=ano_ref_run)
    if df_pedido.empty:
        print("  [AVISO] Nenhum dado de Pedido encontrado. Gerando relatório só com Consulta.")
    else:
        print(f"  Total Pedido: {len(df_pedido):,} linhas.")

    print("\n[4/4] Realizando JOIN e computando métricas ...")
    metrics = join_and_analyze(df_consulta, df_pedido)

    print("\nMétricas principais:")
    print(f"  Créditos totais : {_fmt_brl(metrics.get('total_creditos', 0))}")
    print(f"  Notas aceitas   : {metrics.get('notas_aceitas', 0):,}  ({metrics.get('taxa_aceitacao', 0):.1f}%)")
    print(f"  CPFs únicos     : {metrics.get('cpfs_unicos', 0):,}")
    print(f"  Taxa de match   : {metrics.get('taxa_match', 0):.1f}%")
    print(f"  Período         : {metrics.get('periodo', 'N/A')}")

    print("\nGerando relatório HTML ...")
    generate_html_report(metrics, OUTPUT_PATH)
    print("\nConcluído!")
    print("=" * 60)


if __name__ == "__main__":
    main()

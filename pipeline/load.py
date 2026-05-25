"""
load.py – SCD-2 laadfuncties voor alle dimensie- en feit-tabellen.

Aanpak (identiek aan SSIS SCD-2 Wizard):
  1.  Haal huidig actieve rijen op uit de doeltabel (RowEndDate IS NULL).
  2.  Vergelijk met bron op business-key.
  3.  NIEUWE rijen  → INSERT (RowStartDate = now, RowEndDate = NULL).
  4.  GEWIJZIGDE rijen → UPDATE RowEndDate = now  +  INSERT nieuwe versie.
  5.  ONGEWIJZIGDE rijen → niets doen.

Voor feit-tabellen (FactRating, FactPrincipal) wordt een eenvoudige
truncate-and-reload gebruikt, want facts zijn afleidbaar en kennen
geen historiek.
"""

import logging
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from . import config as cfg

logger = logging.getLogger(__name__)

# Schema-prefix voor alle tabelnamen (configureerbaar via .env DB_SCHEMA)
_SCHEMA = cfg.DB_SCHEMA


# ── Verbinding ───────────────────────────────────────────────────────────────

def get_connection(db_config: dict) -> psycopg2.extensions.connection:
    """Maak een nieuwe psycopg2-verbinding aan."""
    return psycopg2.connect(**db_config)


# ── Hulpfuncties ─────────────────────────────────────────────────────────────

def _quoted(name: str) -> str:
    """Zet een kolomnaam tussen aanhalingstekens (PostgreSQL)."""
    return f'"{name}"'


def _to_python_value(value: Any) -> Any:
    """
    Zet pandas/numpy-waarden om naar native Python-types voor psycopg2.

    psycopg2 kent geen numpy.int64, pandas NA, enz.
    """
    if pd.isna(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return value


def _fetch_active(cur, table: str, columns: list[str]) -> pd.DataFrame:
    """Haal alle actief actieve rijen op (RowEndDate IS NULL)."""
    cols = ", ".join(_quoted(c) for c in columns)
    cur.execute(f'SELECT {cols} FROM "{_SCHEMA}"."{table}" WHERE "RowEndDate" IS NULL')
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=columns)


def _bulk_insert(cur, table: str, columns: list[str], df: pd.DataFrame) -> int:
    """
    Voeg rijen in via psycopg2 execute_values (veel sneller dan row-by-row).
    Geeft het aantal ingevoegde rijen terug.
    """
    if df.empty:
        return 0

    cols = ", ".join(_quoted(c) for c in columns)
    sql  = f'INSERT INTO "{_SCHEMA}"."{table}" ({cols}) VALUES %s'

    records = [
        tuple(_to_python_value(v) for v in row)
        for row in df[columns].itertuples(index=False, name=None)
    ]
    execute_values(cur, sql, records, page_size=1000)
    return len(records)


def _expire_rows(cur, table: str, sk_col: str, sk_values: list[Any], now: datetime) -> int:
    """
    Stel RowEndDate in op *now* voor de opgegeven surrogate keys.
    Geeft het aantal verlopen rijen terug.
    """
    if not sk_values:
        return 0
    sql = f"""
        UPDATE "{_SCHEMA}"."{table}"
        SET    "RowEndDate" = %s
        WHERE  "{sk_col}" = ANY(%s)
          AND  "RowEndDate" IS NULL
    """
    cur.execute(sql, (now, sk_values))
    return cur.rowcount


# ── Generieke SCD-2 dimensie-loader ─────────────────────────────────────────

def load_scd2(
    conn,
    table: str,
    sk_col: str,
    business_keys: list[str],
    tracked_cols: list[str],
    source_df: pd.DataFrame,
    now: datetime,
) -> dict:
    """
    Generieke SCD-2 laadfunctie voor dimensietabellen.

    Args:
        conn:          Open psycopg2-verbinding.
        table:         Naam van de doeltabel (bv. 'DimMovie').
        sk_col:        Naam van de surrogate key (bv. 'movie_sk').
        business_keys: Kolom(men) die een record uniek identificeren in de bron.
        tracked_cols:  Kolommen die een nieuwe versie triggeren bij wijziging.
        source_df:     Getransformeerde bron-DataFrame (zonder SK, met RowStartDate/RowEndDate).
        now:           Tijdstip dat als RowStartDate / nieuw RowEndDate wordt gebruikt.

    Returns:
        Dict met statistieken: {'new': int, 'changed': int, 'unchanged': int}
    """
    all_cols = business_keys + tracked_cols
    fetch_cols = [sk_col] + all_cols

    with conn.cursor() as cur:
        # ── Stap 1: Haal actieve rijen op ────────────────────────────────
        existing_df = _fetch_active(cur, table, fetch_cols)
        stats = {"new": 0, "changed": 0, "unchanged": 0}

        if existing_df.empty:
            # Initiële lading – alles is nieuw
            insert_cols = all_cols + ["RowStartDate", "RowEndDate"]
            stats["new"] = _bulk_insert(cur, table, insert_cols, source_df)
            conn.commit()
            logger.info(
                "%s – initiële lading: %d rijen ingevoegd", table, stats["new"]
            )
            return stats

        # ── Stap 2: Vergelijk bron met bestaande rijen ────────────────────
        # Alles naar string voor typeongevoelige vergelijking (Int64 vs int, None vs NaN)
        src = source_df[all_cols].copy().astype(str).fillna("")
        tgt = existing_df[all_cols].copy().astype(str).fillna("")

        # Left join: bronrijen zonder match in de doeltabel zijn nieuw
        merged = src.merge(
            existing_df[[sk_col] + business_keys],
            on=business_keys,
            how="left",
        )

        # Nieuwe rijen: geen match gevonden in doeltabel
        is_new = merged[sk_col].isna()
        new_records = source_df[is_new.values].copy()

        # Inner join op business keys: geeft alleen rijen die al bestaan.
        # existing_merged = huidige DB-waarden, src_matched = nieuwe bronwaarden,
        # beide op dezelfde volgorde zodat kolom-voor-kolom vergelijking klopt.
        existing_merged = tgt.merge(
            existing_df[[sk_col] + business_keys],
            on=business_keys,
            how="inner",
        )
        src_matched = src.merge(
            existing_df[[sk_col] + business_keys],
            on=business_keys,
            how="inner",
        )

        changed_mask = pd.Series([False] * len(existing_merged))
        for col in tracked_cols:
            if col in src_matched.columns and col in existing_merged.columns:
                changed_mask |= (
                    src_matched[col].fillna("").values
                    != existing_merged[col].fillna("").values
                )

        changed_sks  = existing_merged.loc[changed_mask.values, sk_col].tolist()
        changed_recs = source_df[
            source_df[business_keys].apply(tuple, axis=1).isin(
                src_matched.loc[changed_mask.values, business_keys]
                .apply(tuple, axis=1)
            )
        ].copy()

        # ── Stap 3: Verlopen van gewijzigde rijen ─────────────────────────
        stats["changed"] = _expire_rows(cur, table, sk_col, changed_sks, now)

        # ── Stap 4: Invoegen van nieuwe + gewijzigde rijen ────────────────
        to_insert = pd.concat([new_records, changed_recs], ignore_index=True)
        insert_cols = all_cols + ["RowStartDate", "RowEndDate"]
        inserted = _bulk_insert(cur, table, insert_cols, to_insert)
        stats["new"] = inserted - stats["changed"]

        stats["unchanged"] = len(source_df) - inserted

        conn.commit()
        logger.info(
            "%s – nieuw: %d | gewijzigd: %d | ongewijzigd: %d",
            table, stats["new"], stats["changed"], stats["unchanged"],
        )
        return stats


# ── Statische dimensies (geen SCD-2) ─────────────────────────────────────────

def _fetch_existing_keys(cur, table: str, business_keys: list[str]) -> set:
    """Haal bestaande business keys op als tuples."""
    cols = ", ".join(_quoted(c) for c in business_keys)
    cur.execute(f'SELECT {cols} FROM "{_SCHEMA}"."{table}"')
    if len(business_keys) == 1:
        return {row[0] for row in cur.fetchall()}
    return {tuple(row) for row in cur.fetchall()}


def load_dimension_static(
    conn,
    table: str,
    columns: list[str],
    business_keys: list[str],
    source_df: pd.DataFrame,
    force_reload: bool = False,
    chunk_size: int = 50_000,
) -> int:
    """
    Laad een dimensie zonder SCD-2 (DimDate, DimCountry).

    Standaard: alleen nieuwe business keys invoegen (geen TRUNCATE), zodat
    bestaande foreign keys in feit-tabellen intact blijven.

    Met force_reload=True: TRUNCATE ... CASCADE (verwijdert ook afhankelijke
    feit-tabellen — alleen gebruiken bij bewuste volledige herlading).
    """
    total = 0
    with conn.cursor() as cur:
        if force_reload:
            logger.warning(
                "%s – TRUNCATE CASCADE: verwijdert ook tabellen met FK naar %s",
                table, table,
            )
            cur.execute(
                f'TRUNCATE TABLE "{_SCHEMA}"."{table}" RESTART IDENTITY CASCADE'
            )
            to_load = source_df
        else:
            existing = _fetch_existing_keys(cur, table, business_keys)
            if not existing:
                logger.info("%s – initiële lading (lege tabel)", table)
                to_load = source_df
            else:
                if len(business_keys) == 1:
                    mask = ~source_df[business_keys[0]].isin(existing)
                else:
                    mask = ~source_df[business_keys].apply(tuple, axis=1).isin(existing)
                to_load = source_df[mask].copy()
                skipped = len(source_df) - len(to_load)
                logger.info(
                    "%s – %d bestaande keys overgeslagen, %d nieuwe rijen",
                    table, skipped, len(to_load),
                )

        for start in range(0, len(to_load), chunk_size):
            chunk = to_load.iloc[start : start + chunk_size]
            total += _bulk_insert(cur, table, columns, chunk)
            conn.commit()

    logger.info("%s – klaar: %d rijen ingevoegd", table, total)
    return total


# ── Feit-tabellen (truncate-and-reload) ──────────────────────────────────────

def load_fact_truncate_insert(
    conn,
    table: str,
    columns: list[str],
    source_df: pd.DataFrame,
    chunk_size: int = 50_000,
) -> int:
    """
    Laad een feit-tabel via TRUNCATE + batch INSERT.
    Gebruikt chunks voor grote datasets (FactPrincipal > 80 M rijen).

    Returns:
        Totaal aantal ingevoegde rijen.
    """
    total = 0
    with conn.cursor() as cur:
        logger.info("%s – tabel leegmaken ...", table)
        cur.execute(f'TRUNCATE TABLE "{_SCHEMA}"."{table}" RESTART IDENTITY CASCADE')

        for start in range(0, len(source_df), chunk_size):
            chunk = source_df.iloc[start : start + chunk_size]
            total += _bulk_insert(cur, table, columns, chunk)
            conn.commit()
            logger.debug("%s – %d / %d rijen geladen", table, total, len(source_df))

    logger.info("%s – klaar: %d rijen ingevoegd", table, total)
    return total


# ── SK-lookup opbouwen ───────────────────────────────────────────────────────

def fetch_sk_map(
    conn, table: str, sk_col: str, key_col: str, *, scd2: bool = True
) -> dict:
    """
    Lees een {key_col → sk_col}-woordenboek uit de doeltabel.
    Gebruikt voor het oplossen van foreign keys vóór het laden van afhankelijke tabellen.

    Args:
        scd2: True = alleen actieve rijen (RowEndDate IS NULL).
              False = alle rijen (DimDate, DimCountry).

    Voorbeeld:
        movie_sk_map = fetch_sk_map(conn, 'DimMovie', 'movie_sk', 'tconst')
    """
    where = ' WHERE "RowEndDate" IS NULL' if scd2 else ""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT "{key_col}", "{sk_col}" FROM "{_SCHEMA}"."{table}"{where}'
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def fetch_sk_map_composite(conn, table: str, sk_col: str, key_cols: list[str]) -> dict:
    """
    Lees een {tuple(key_cols) → sk_col}-woordenboek voor samengestelde sleutels.

    Voorbeeld:
        category_sk_map = fetch_sk_map_composite(
            conn, 'DimCategory', 'category_sk', ['category', 'job']
        )
    """
    cols = ", ".join(_quoted(c) for c in key_cols)
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT {cols}, "{sk_col}" FROM "{_SCHEMA}"."{table}" WHERE "RowEndDate" IS NULL'
        )
        return {row[:-1]: row[-1] for row in cur.fetchall()}

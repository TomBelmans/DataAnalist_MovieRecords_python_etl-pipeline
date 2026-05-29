"""
check_db.py – Verbindings- en schemaverificatie voor MovieRecordsDW.

Toont in de terminal:
  - Verbindingsgegevens (host, database, schema MovieRecordsDW)
  - Alle tabellen in het schema
  - Per tabel: kolommen, datatypes, NULL/NOT NULL, PK en FK

Gebruik:
    python check_db.py
    python check_db.py --table DimMovie
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

import pyodbc

from pipeline import config as cfg
from pipeline.load import get_connection


def connect():
    """
    Maakt een SQL Server-verbinding op basis van pipeline/config.py (.env),
    valideert dat host en wachtwoord aanwezig zijn, en zet autocommit aan.

    Returns:
        Tuple (conn, schema): open pyodbc-verbinding en het DW-schema
        (standaard 'MovieRecordsDW' via DB_SCHEMA in .env).
    """
    cfg.validate_config()
    conn = get_connection(cfg.DB_CONFIG)
    conn.autocommit = True
    return conn, cfg.DB_SCHEMA


def fetch_schemas(cur) -> list[str]:
    """
    Haalt alle gebruikersschema's op van de database (zonder systeemschema's).
    """
    cur.execute(
        """
        SELECT name
        FROM sys.schemas
        WHERE name NOT IN (
            'sys', 'guest', 'INFORMATION_SCHEMA',
            'db_owner', 'db_accessadmin', 'db_securityadmin',
            'db_ddladmin', 'db_backupoperator',
            'db_datareader', 'db_datawriter',
            'db_denydatareader', 'db_denydatawriter'
        )
        ORDER BY name
        """
    )
    return [row[0] for row in cur.fetchall()]


def fetch_tables(cur, schema: str) -> list[str]:
    """
    Haalt alle basistabellen op binnen het opgegeven schema.
    """
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = ?
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        (schema,),
    )
    return [row[0] for row in cur.fetchall()]


def fetch_columns(cur, schema: str, table: str) -> list[dict]:
    """
    Haalt alle kolomdefinities op voor één tabel via information_schema.
    """
    cur.execute(
        """
        SELECT
            column_name,
            ordinal_position,
            data_type,
            character_maximum_length,
            numeric_precision,
            numeric_scale,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = ?
          AND table_name = ?
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    cols = []
    for row in cur.fetchall():
        name, pos, dtype, char_len, num_prec, num_scale, nullable, default = row
        type_label = _format_type(dtype, char_len, num_prec, num_scale)
        cols.append(
            {
                "name":     name,
                "position": pos,
                "type":     type_label,
                "nullable": nullable == "YES",
                "default":  default,
            }
        )
    return cols


def _format_type(dtype: str, char_len, num_prec, num_scale) -> str:
    """Zet SQL Server-typen om naar een leesbaar label voor de terminal."""
    dtype = dtype.lower()
    if dtype in ("int", "integer"):
        return "INT"
    if dtype == "bigint":
        return "BIGINT"
    if dtype == "bit":
        return "BIT"
    if dtype in ("nvarchar", "varchar"):
        length = "MAX" if char_len == -1 else (char_len or "?")
        return f"{dtype.upper()}({length})"
    if dtype in ("nchar", "char"):
        return f"{dtype.upper()}({char_len or '?'})"
    if dtype == "numeric":
        return f"NUMERIC({num_prec},{num_scale})"
    if dtype in ("datetime2", "datetime", "smalldatetime"):
        return dtype.upper()
    if dtype == "date":
        return "DATE"
    if dtype == "text":
        return "TEXT"
    return dtype.upper()


def fetch_primary_keys(cur, schema: str, table: str) -> list[str]:
    """Haalt de kolomnamen op die deel uitmaken van de primary key van een tabel."""
    cur.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_schema = kcu.constraint_schema
         AND tc.constraint_name = kcu.constraint_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = ?
          AND tc.table_name = ?
        ORDER BY kcu.ordinal_position
        """,
        (schema, table),
    )
    return [row[0] for row in cur.fetchall()]


def fetch_foreign_keys(cur, schema: str, table: str) -> dict[str, list[str]]:
    """Haalt alle foreign key-relaties op voor één tabel."""
    cur.execute(
        """
        SELECT
            kcu.column_name,
            ccu.table_schema,
            ccu.table_name,
            ccu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_schema = kcu.constraint_schema
         AND tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_schema = tc.constraint_schema
         AND ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = ?
          AND tc.table_name = ?
        ORDER BY kcu.column_name
        """,
        (schema, table),
    )
    fks: dict[str, list[str]] = defaultdict(list)
    for col, ref_schema, ref_table, ref_col in cur.fetchall():
        fks[col].append(f'{ref_schema}.{ref_table}("{ref_col}")')
    return dict(fks)


def print_header(title: str) -> None:
    line = "=" * 72
    print(f"\n{line}\n  {title}\n{line}")


def print_connection_info(conn, schema: str) -> None:
    """Toont verbindingsdetails: host uit .env plus live info van de server."""
    print_header("VERBINDING")
    with conn.cursor() as cur:
        cur.execute("SELECT DB_NAME(), SYSTEM_USER, @@SERVERNAME, @@VERSION")
        db, user, server_name, version = cur.fetchone()

    print(f"  Host                : {cfg.DB_CONFIG['host']}")
    print(f"  Poort               : {cfg.DB_CONFIG['port']}")
    print(f"  SQL Server database : {db}")
    print(f"  DW-schema (logisch) : {schema}       (hier staan je DW-tabellen)")
    print(f"  Gebruiker           : {user}")
    print(f"  Server              : {server_name or '(via Docker)'}")
    print(f"  Versie              : {version.splitlines()[0]}")


def print_schemas(cur, target_schema: str) -> None:
    """Toont alle beschikbare schema's en markeert het doelschema."""
    schemas = fetch_schemas(cur)
    print_header("BESCHIKBARE SCHEMA'S")
    for s in schemas:
        marker = "  <-- doelschema" if s == target_schema else ""
        print(f"  - {s}{marker}")
    if target_schema not in schemas:
        print(f"\n  [!] Schema '{target_schema}' bestaat niet op deze server.")
        print("    Voer sql/create_tables.sql uit op de SQL Server.")


def print_tables(cur, schema: str) -> list[str]:
    """Toont een genummerde lijst van alle tabellen in het DW-schema."""
    tables = fetch_tables(cur, schema)
    print_header(f"TABELLEN IN SCHEMA '{schema}'")
    if not tables:
        print("  (geen tabellen gevonden)")
        return tables
    for i, name in enumerate(tables, 1):
        print(f"  {i:2}. {name}")
    print(f"\n  Totaal: {len(tables)} tabel(len)")
    return tables


def print_table_details(cur, schema: str, table: str) -> None:
    """Toont per kolom: datatype, NULL/NOT NULL, primary key en foreign keys."""
    columns = fetch_columns(cur, schema, table)
    pks     = set(fetch_primary_keys(cur, schema, table))
    fks     = fetch_foreign_keys(cur, schema, table)

    print_header(f"TABEL: {schema}.{table}")
    if not columns:
        print("  (geen kolommen gevonden)")
        return

    col_w = max(len(c["name"]) for c in columns)
    col_w = max(col_w, 10)
    print(f"  {'Kolom':<{col_w}}  {'Type':<22}  {'Null':<6}  {'PK':<4}  Relatie (FK)")
    print(f"  {'-' * col_w}  {'-' * 22}  {'-' * 6}  {'-' * 4}  {'-' * 30}")

    for col in columns:
        name     = col["name"]
        null_txt = "NULL" if col["nullable"] else "NOT NULL"
        pk_txt   = "PK" if name in pks else ""
        fk_txt   = ", ".join(fks.get(name, [])) or "-"
        default  = f"  default={col['default']}" if col["default"] else ""
        print(
            f"  {name:<{col_w}}  {col['type']:<22}  {null_txt:<6}  {pk_txt:<4}  {fk_txt}{default}"
        )


def run(table_filter: str | None = None) -> int:
    """
    Voert de volledige verificatie uit en geeft een exitcode terug.

    Args:
        table_filter: Optionele tabelnaam (bv. 'DimMovie'). None = alle tabellen.

    Returns:
        0 bij succes, 1 bij verbindings- of metadatafout.
    """
    try:
        conn, schema = connect()
    except Exception as exc:
        print(f"\n[X] Verbinding mislukt: {exc}")
        return 1

    try:
        with conn.cursor() as cur:
            print_connection_info(conn, schema)
            print_schemas(cur, schema)

            tables = fetch_tables(cur, schema)
            print_tables(cur, schema)

            if not tables:
                return 1

            targets = [table_filter] if table_filter else tables
            if table_filter and table_filter not in tables:
                print(f"\n[X] Tabel '{table_filter}' niet gevonden in schema '{schema}'.")
                print(f"  Beschikbaar: {', '.join(tables)}")
                return 1

            for table in targets:
                print_table_details(cur, schema, table)

        print_header("RESULTAAT")
        print("  [OK] Verbinding OK")
        print(f"  [OK] Schema '{schema}' bereikbaar")
        print(f"  [OK] {len(tables)} tabel(len) gelezen")
        return 0

    except Exception as exc:
        print(f"\n[X] Fout tijdens metadata-ophalen: {exc}")
        return 1
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Controleer de SQL Server-verbinding en toon MovieRecordsDW-metadata."
    )
    parser.add_argument(
        "--table",
        metavar="NAME",
        help="Toon alleen details van één tabel (bv. DimMovie).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(run(table_filter=args.table))

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

import psycopg2

from pipeline import config as cfg


def connect():
    """
    Maakt een PostgreSQL-verbinding op basis van pipeline/config.py (.env),
    valideert dat host en wachtwoord aanwezig zijn, en zet autocommit aan.

    Returns:
        Tuple (conn, schema): open psycopg2-verbinding en het DW-schema
        (standaard 'MovieRecordsDW' via DB_SCHEMA in .env).
    """
    cfg.validate_config()
    conn = psycopg2.connect(**cfg.DB_CONFIG)
    conn.autocommit = True
    return conn, cfg.DB_SCHEMA


def fetch_schemas(cur) -> list[str]:
    """
    Deze methode haalt alle gebruikersschema's op van de database (zonder systeemschema's) en f pg_catalog, information_schema en interne pg_*-schema's eruit, zodat alleen relevante schema's zoals MovieRecordsDW en public zichtbaar zijn.

    Args:
        cur: Actieve databasecursor.

    Returns:
        Gesorteerde lijst met schemanamen.
    """
    cur.execute(
        """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          AND schema_name NOT LIKE 'pg_%%'
        ORDER BY schema_name
        """
    )
    return [row[0] for row in cur.fetchall()]


def fetch_tables(cur, schema: str) -> list[str]:
    """
    Deze methode haalt alle basistabellen op binnen het opgegeven schema.

    Args:
        cur:    Actieve databasecursor.
        schema: Schemanaam (bv. 'MovieRecordsDW').

    Returns:
        Gesorteerde lijst met tabelnamen (bv. ['DimDate', 'DimMovie', ...]).
    """
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        (schema,),
    )
    return [row[0] for row in cur.fetchall()]


def fetch_columns(cur, schema: str, table: str) -> list[dict]:
    """
    Deze methode haalt alle kolomdefinities op voor één tabel via information_schema.

    Per kolom worden naam, positie, datatype, nullable-vlag en default-waarde
    opgeslagen. Het datatype wordt leesbaar gemaakt via _format_type().

    Args:
        cur:    Actieve databasecursor.
        schema: Schemanaam.
        table:  Tabelnaam.

    Returns:
        Lijst van dicts met keys: name, position, type, nullable, default.
    """
    cur.execute(
        """
        SELECT
            column_name,
            ordinal_position,
            data_type,
            udt_name,
            character_maximum_length,
            numeric_precision,
            numeric_scale,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    cols = []
    for row in cur.fetchall():
        name, pos, dtype, udt, char_len, num_prec, num_scale, nullable, default = row
        type_label = _format_type(dtype, udt, char_len, num_prec, num_scale)
        cols.append(
            {
                "name": name,
                "position": pos,
                "type": type_label,
                "nullable": nullable == "YES",
                "default": default,
            }
        )
    return cols


def _format_type(dtype, udt, char_len, num_prec, num_scale) -> str:
    """
   Deze methode zet ruwe PostgreSQL-typen om naar een leesbaar label voor de terminal.

    Combineert information_schema.data_type en udt_name (bijv. int4 → INTEGER,
    serial → INTEGER (serial), varchar → CHARACTER VARYING(10)).

    Args:
        dtype:    Algemeen datatype (information_schema).
        udt:      Underlying type name (PostgreSQL-specifiek).
        char_len: Maximale lengte voor teksttypes.
        num_prec: Precisie voor numeric.
        num_scale: Schaal voor numeric.

    Returns:
        Geformatteerde typestring voor weergave.
    """
    if udt in ("int4", "serial"):
        return "INTEGER (serial)" if udt == "serial" else "INTEGER"
    if udt == "int8":
        return "BIGINT (bigserial)" if dtype == "bigint" else "BIGINT"
    if udt == "bool":
        return "BOOLEAN"
    if udt == "text":
        return "TEXT"
    if udt in ("varchar", "bpchar"):
        length = char_len or "?"
        return f"{dtype.upper()}({length})"
    if udt == "numeric":
        return f"NUMERIC({num_prec},{num_scale})"
    if udt in ("timestamp", "timestamptz"):
        return dtype.upper()
    if udt == "date":
        return "DATE"
    return f"{dtype} ({udt})"


def fetch_primary_keys(cur, schema: str, table: str) -> list[str]:
    """
    Deze methode haalt de kolomnamen op die deel uitmaken van de primary key van een tabel.

    Args:
        cur:    Actieve databasecursor.
        schema: Schemanaam.
        table:  Tabelnaam.

    Returns:
        Lijst van PK-kolomnamen in constraint-volgorde (bv. ['movie_sk']).
    """
    cur.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_schema = kcu.constraint_schema
         AND tc.constraint_name = kcu.constraint_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = %s
          AND tc.table_name = %s
        ORDER BY kcu.ordinal_position
        """,
        (schema, table),
    )
    return [row[0] for row in cur.fetchall()]


def fetch_foreign_keys(cur, schema: str, table: str) -> dict[str, list[str]]:
    """
    Deze methode haalt alle foreign key-relaties op voor één tabel.

    Per lokale kolom wordt bijgehouden naar welke tabel.kolom de FK verwijst,
    bijv. dimMovieKey → MovieRecordsDW.DimMovie("movie_sk").

    Args:
        cur:    Actieve databasecursor.
        schema: Schemanaam.
        table:  Tabelnaam.

    Returns:
        Dict {kolomnaam: [referentie-strings]} — een kolom kan meerdere FK's hebben.
    """
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
          AND tc.table_schema = %s
          AND tc.table_name = %s
        ORDER BY kcu.column_name
        """,
        (schema, table),
    )
    fks: dict[str, list[str]] = defaultdict(list)
    for col, ref_schema, ref_table, ref_col in cur.fetchall():
        fks[col].append(f'{ref_schema}.{ref_table}("{ref_col}")')
    return dict(fks)


def print_header(title: str) -> None:
    """
    Print een visuele sectiekop in de terminal (72 tekens breed).

    Args:
        title: Titel van de sectie (bv. 'VERBINDING', 'TABELLEN IN SCHEMA ...').
    """
    line = "=" * 72
    print(f"\n{line}\n  {title}\n{line}")


def print_connection_info(conn, schema: str) -> None:
    """
    Deze methode haalt toont verbindingsdetails: host uit .env plus live info van de server.

    Vraagt aan PostgreSQL: huidige database, gebruiker, server-IP en versie.
    Legt uit dat 'postgres' de databasenaam is en schema het DW-logisch model.

    Args:
        conn:   Open psycopg2-verbinding.
        schema: Doelschema (MovieRecordsDW).
    """
    print_header("VERBINDING")
    with conn.cursor() as cur:
        cur.execute("SELECT current_database(), current_user, inet_server_addr(), version()")
        db, user, host, version = cur.fetchone()

    print(f"  Host                : {cfg.DB_CONFIG['host']}")
    print(f"  Poort               : {cfg.DB_CONFIG['port']}")
    print(f"  PostgreSQL database : {db}")
    print(f"  DW-schema (logisch) : {schema}       (hier staan je DW-tabellen)")
    print(f"  Gebruiker           : {user}")
    print(f"  Server IP           : {host or '(via pooler)'}")
    print(f"  PostgreSQL          : {version.split(',')[0]}")


def print_schemas(cur, target_schema: str) -> None:
    """
    Deze methode haalt alle beschikbare schema's op en toont ze, en markeert het doelschema (MovieRecordsDW).

    Geeft een waarschuwing als het doelschema niet bestaat (create_tables.sql nog
    niet uitgevoerd).

    Args:
        cur:            Actieve databasecursor.
        target_schema:  Schema dat je wilt gebruiken voor de ETL.
    """
    schemas = fetch_schemas(cur)
    print_header("BESCHIKBARE SCHEMA'S")
    for s in schemas:
        marker = "  <-- doelschema" if s == target_schema else ""
        print(f"  - {s}{marker}")
    if target_schema not in schemas:
        print(f"\n  [!] Schema '{target_schema}' bestaat niet op deze server.")
        print("    Voer sql/create_tables.sql uit op de PostgreSQL-server.")


def print_tables(cur, schema: str) -> list[str]:
    """
    Deze methode toont een genummerde lijst van alle tabellen in het DW-schema.

    Args:
        cur:    Actieve databasecursor.
        schema: Schemanaam.

    Returns:
        Lijst met tabelnamen (leeg als er geen tabellen zijn).
    """
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
    """
    Deze methode toont per kolom: datatype, NULL/NOT NULL, primary key en foreign keys.

    Combineert fetch_columns, fetch_primary_keys en fetch_foreign_keys in
    één overzichtelijke tabel in de terminal.

    Args:
        cur:    Actieve databasecursor.
        schema: Schemanaam.
        table:  Tabelnaam.
    """
    columns = fetch_columns(cur, schema, table)
    pks = set(fetch_primary_keys(cur, schema, table))
    fks = fetch_foreign_keys(cur, schema, table)

    print_header(f"TABEL: {schema}.{table}")
    if not columns:
        print("  (geen kolommen gevonden)")
        return

    col_w = max(len(c["name"]) for c in columns)
    col_w = max(col_w, 10)
    print(f"  {'Kolom':<{col_w}}  {'Type':<22}  {'Null':<6}  {'PK':<4}  Relatie (FK)")
    print(f"  {'-' * col_w}  {'-' * 22}  {'-' * 6}  {'-' * 4}  {'-' * 30}")

    for col in columns:
        name = col["name"]
        null_txt = "NULL" if col["nullable"] else "NOT NULL"
        pk_txt = "PK" if name in pks else ""
        fk_txt = ", ".join(fks.get(name, [])) or "-"
        default = f"  default={col['default']}" if col["default"] else ""
        print(
            f"  {name:<{col_w}}  {col['type']:<22}  {null_txt:<6}  {pk_txt:<4}  {fk_txt}{default}"
        )


def run(table_filter: str | None = None) -> int:
    """
    Deze methode voert de volledige verificatie uit en geef een exitcode terug.

    Stappen: verbinden → verbindingsinfo → schema's → tabellen → kolomdetails
    (alle tabellen of alleen table_filter). Sluit de verbinding altijd af.

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
    """
    Deze methode verwerkt command-line argumenten (--table voor filtering op één tabel).

    Returns:
        argparse.Namespace met optioneel veld 'table'.
    """
    parser = argparse.ArgumentParser(
        description="Controleer de PostgreSQL-verbinding en toon MovieRecordsDW-metadata."
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

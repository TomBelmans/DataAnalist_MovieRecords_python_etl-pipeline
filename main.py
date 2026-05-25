"""
main.py – Orchestrator voor de MovieRecords ETL-pipeline.

Volgorde van uitvoering (respecteert FK-dependencies, net als SSIS Control Flow):

    1.  DimDate                (geen FK's)
    2.  DimMovie               (geen FK's)
    3.  DimGenre               (verwijst logisch naar DimMovie via tconst)
    4.  DimCountry             (geen FK's)
    5.  DimPerson              (geen FK's)
    6.  DimCategory            (geen FK's)
    7.  DimKnownForTitle       (geen FK's)
    8.  DimProfession          (geen FK's)
    9.  DimAlternativeTitle    (FK's: DimMovie, DimCountry)
    10. FactRating             (FK's: DimMovie, DimGenre, DimDate)
    11. FactPrincipal          (FK's: DimMovie, DimPerson, DimCategory,
                                        DimKnownForTitle, DimProfession, DimDate)

Gebruik:
    python main.py                              # volledige pipeline
    python main.py --tables DimMovie DimGenre   # laad enkel specifieke tabellen
"""

import argparse
import logging
import sys
from datetime import UTC, datetime

from pipeline import config as cfg
from pipeline.extract import extract_all
from pipeline.transform import (
    transform_dim_date,
    transform_dim_movie,
    transform_dim_genre,
    transform_dim_person,
    transform_dim_profession,
    transform_dim_known_for_title,
    transform_dim_category,
    transform_dim_country,
    transform_dim_alternative_title,
    transform_fact_rating,
    transform_fact_principal,
)
from pipeline.load import (
    get_connection,
    load_scd2,
    load_dimension_static,
    load_fact_truncate_insert,
    fetch_sk_map,
    fetch_sk_map_composite,
)

logger = logging.getLogger(__name__)

ALL_TABLES = [
    "DimDate", "DimMovie", "DimGenre", "DimCountry",
    "DimPerson", "DimCategory", "DimKnownForTitle", "DimProfession",
    "DimAlternativeTitle", "FactRating", "FactPrincipal",
]


# ── Pipeline stappen ──────────────────────────────────────────────────────────

def run_dim_date(conn, raw: dict, now: datetime) -> None:
    # DimDate: statische dimensie (geen SCD-2)
    df = transform_dim_date(raw["dimdates"])
    load_dimension_static(
        conn, table="DimDate",
        columns=["date", "dateShortDescription", "dateLongName", "monthLongName", "year"],
        business_keys=["date"],
        source_df=df,
    )


def run_dim_movie(conn, raw: dict, now: datetime) -> None:
    df = transform_dim_movie(raw["title_basics"], now)
    load_scd2(
        conn, table="DimMovie", sk_col="movie_sk",
        business_keys=["tconst"],
        tracked_cols=["titleType", "primaryTitle", "originalTitle", "isAdult"],
        source_df=df, now=now,
    )


def run_dim_genre(conn, raw: dict, now: datetime) -> None:
    df = transform_dim_genre(raw["title_basics"], now)
    load_scd2(
        conn, table="DimGenre", sk_col="genre_sk",
        business_keys=["tconst"],
        tracked_cols=["genreName1", "genreName2", "genreName3"],
        source_df=df, now=now,
    )


def run_dim_country(conn, raw: dict, now: datetime) -> None:
    # DimCountry: stabiele referentietabel zonder SCD-2
    df = transform_dim_country(raw["iban"])
    load_dimension_static(
        conn, table="DimCountry",
        columns=["country", "alpha_code_2", "alpha_code_3", "number"],
        business_keys=["alpha_code_2"],
        source_df=df,
    )


def run_dim_person(conn, raw: dict, now: datetime) -> None:
    df = transform_dim_person(raw["name_basics"], now)
    load_scd2(
        conn, table="DimPerson", sk_col="person_sk",
        business_keys=["nconst"],
        tracked_cols=["primaryName"],
        source_df=df, now=now,
    )


def run_dim_category(conn, raw: dict, now: datetime) -> None:
    df = transform_dim_category(raw["title_principals"], now)
    load_scd2(
        conn, table="DimCategory", sk_col="category_sk",
        business_keys=["category", "job"],
        tracked_cols=[],           # stabiele dimensie
        source_df=df, now=now,
    )


def run_dim_known_for_title(conn, raw: dict, now: datetime) -> None:
    df = transform_dim_known_for_title(raw["name_basics"], now)
    # KnownForTitle heeft geen compacte business key in de bron – we gebruiken
    # de positie in name.basics (nconst) als proxy.  De SK wordt door de DB gegenereerd.
    load_scd2(
        conn, table="DimKnownForTitle", sk_col="knownForTitle_sk",
        business_keys=["nconst"],
        tracked_cols=["knownForTitleId1", "knownForTitleId2", "knownForTitleId3", "knownForTitleId4"],
        source_df=df, now=now,
    )


def run_dim_profession(conn, raw: dict, now: datetime) -> None:
    df = transform_dim_profession(raw["name_basics"], now)
    load_scd2(
        conn, table="DimProfession", sk_col="profession_sk",
        business_keys=["nconst"],
        tracked_cols=["professionName1", "professionName2", "professionName3"],
        source_df=df, now=now,
    )


def run_dim_alternative_title(conn, raw: dict, now: datetime) -> None:
    movie_sk_map   = fetch_sk_map(conn, "DimMovie",   "movie_sk",   "tconst")
    country_sk_map = fetch_sk_map(conn, "DimCountry", "country_sk", "alpha_code_2", scd2=False)

    df = transform_dim_alternative_title(
        raw["title_akas"], movie_sk_map, country_sk_map, now
    )
    load_scd2(
        conn, table="DimAlternativeTitle", sk_col="alternativeTitle_sk",
        business_keys=["dimMovieKey", "ordering"],
        tracked_cols=["dimCountryKey", "title", "language", "types", "isOriginalTitle"],
        source_df=df, now=now,
    )


def run_fact_rating(conn, raw: dict) -> None:
    movie_sk_map = fetch_sk_map(conn, "DimMovie",  "movie_sk",  "tconst")
    genre_sk_map = fetch_sk_map(conn, "DimGenre",  "genre_sk",  "tconst")

    # Bouw date_sk_map: year → date_sk  (enkel 1 januari per jaar als ankerdatum)
    date_sk_map = fetch_sk_map(conn, "DimDate", "date_sk", "year", scd2=False)

    df = transform_fact_rating(
        raw["title_basics"], raw["title_ratings"],
        movie_sk_map, genre_sk_map, date_sk_map,
    )

    load_fact_truncate_insert(
        conn, table="FactRating",
        columns=["dimMovieKey", "dimGenreKey", "dimStartYearKey", "dimEndYearKey",
                 "movieRunTimeMinutes", "averageRating", "numVotes"],
        source_df=df,
    )


def run_fact_principal(conn, raw: dict) -> None:
    movie_sk_map   = fetch_sk_map(conn, "DimMovie",   "movie_sk",   "tconst")
    person_sk_map  = fetch_sk_map(conn, "DimPerson",  "person_sk",  "nconst")
    prof_sk_map    = fetch_sk_map(conn, "DimProfession", "profession_sk", "nconst")

    cat_sk_map = fetch_sk_map_composite(
        conn, "DimCategory", "category_sk", ["category", "job"]
    )

    knownfortitle_sk_map = fetch_sk_map(
        conn, "DimKnownForTitle", "knownForTitle_sk", "nconst"
    )

    date_sk_map = fetch_sk_map(conn, "DimDate", "date_sk", "year", scd2=False)

    df = transform_fact_principal(
        raw["title_principals"], raw["name_basics"],
        movie_sk_map, person_sk_map, cat_sk_map,
        knownfortitle_sk_map, prof_sk_map, date_sk_map,
    )

    load_fact_truncate_insert(
        conn, table="FactPrincipal",
        columns=["dimMovieKey", "dimPersonKey", "dimCategoryKey",
                 "dimKnownForTitleKey", "dimProfessionKey",
                 "dimBirthYearKey", "dimDeathYearKey"],
        source_df=df,
        chunk_size=50_000,   # FactPrincipal kan > 80 M rijen bevatten
    )


# ── Pipeline orchestrator ─────────────────────────────────────────────────────

PIPELINE: dict = {
    "DimDate":              run_dim_date,
    "DimMovie":             run_dim_movie,
    "DimGenre":             run_dim_genre,
    "DimCountry":           run_dim_country,
    "DimPerson":            run_dim_person,
    "DimCategory":          run_dim_category,
    "DimKnownForTitle":     run_dim_known_for_title,
    "DimProfession":        run_dim_profession,
    "DimAlternativeTitle":  run_dim_alternative_title,
    "FactRating":           run_fact_rating,
    "FactPrincipal":        run_fact_principal,
}

# Feit-tabellen gebruiken geen SCD-2 'now' tijdstempel
NO_NOW = {"FactRating", "FactPrincipal"}


def run_pipeline(tables: list[str]) -> None:
    """
    Voer de ETL-pipeline uit voor de opgegeven tabellen.

    Alle bronbestanden worden gelezen uit de STAGING_DIR die in .env is ingesteld.
    """
    cfg.validate_config()
    now = datetime.now(UTC).replace(tzinfo=None)

    logger.info("=== MovieRecords ETL gestart: %s ===", now.strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("Te laden tabellen: %s", ", ".join(tables))
    logger.info("Staging-map: %s", cfg.STAGING_DIR)

    # ── Extract: lees alle staging-bestanden in één keer ──────────────────────
    raw = extract_all(cfg.STAGING_DIR)

    # ── Verbinding ────────────────────────────────────────────────────────────
    conn = get_connection(cfg.DB_CONFIG)
    logger.info("Verbonden met PostgreSQL: %s", cfg.DB_CONFIG["host"])

    try:
        for table in ALL_TABLES:
            if table not in tables:
                continue

            logger.info("── Starten: %s ─────────────────────────────", table)
            fn = PIPELINE[table]

            if table in NO_NOW:
                fn(conn, raw)
            else:
                fn(conn, raw, now)

            logger.info("── Klaar:   %s", table)

    except Exception as exc:
        conn.rollback()
        logger.exception("ETL mislukt bij tabel: %s", exc)
        raise
    finally:
        conn.close()

    logger.info("=== ETL succesvol afgerond ===")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MovieRecords ETL pipeline")
    parser.add_argument(
        "--tables", nargs="+", choices=ALL_TABLES, default=ALL_TABLES,
        metavar="TABLE",
        help="Laad enkel de opgegeven tabel(len). Standaard: alle tabellen.",
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="(Genegeerd - bestanden worden altijd uit Staging gelezen.)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        run_pipeline(tables=args.tables)
    except Exception:
        sys.exit(1)

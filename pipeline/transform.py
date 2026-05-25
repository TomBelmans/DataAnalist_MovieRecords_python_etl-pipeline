"""
transform.py – Transformeer ruwe IMDb DataFrames naar het DW-schema.

Elke functie ontvangt de ruwe DataFrames uit extract.py en geeft
een kant-en-klare DataFrame terug met exact de kolomnamen van de
doeltabel in PostgreSQL (zonder surrogate key – die genereert de DB).

Mapping IMDb → DW:
    title.basics    → DimMovie, DimGenre
    title.ratings   → (gecombineerd met title.basics in FactRating)
    title.akas      → DimAlternativeTitle
    name.basics     → DimPerson, DimProfession, DimKnownForTitle
    title.principals→ FactPrincipal

IMDb-conventies die hier worden afgehandeld:
    - Alle bronkolommen zijn strings; numerieke conversie gebeurt per functie.
    - Ontbrekende waarden staan als '\\N' in TSV's; extract.py zet die om naar NaN.
    - Booleaanse velden (isAdult, isOriginalTitle) zijn gecodeerd als '0'/'1'.
"""

import logging
from datetime import datetime, date

import pandas as pd

logger = logging.getLogger(__name__)


# ── Hulpfuncties ─────────────────────────────────────────────────────────────

def _split_column(series: pd.Series, sep: str, n: int) -> pd.DataFrame:
    """Splits een gescheiden Series in exact n kolommen (0 … n-1).
    Ontbrekende posities worden gevuld met NaN; overbodige worden weggegooid."""
    split = series.str.split(sep, expand=True)
    # reindex garandeert altijd precies n kolommen, ongeacht het maximum in de data
    return split.reindex(columns=range(n))


def _scd2_defaults(df: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """Voeg RowStartDate en RowEndDate toe voor SCD-2-dimensies.
    Niet gebruiken voor DimDate en DimCountry — die kennen geen historiek."""
    df = df.copy()
    df["RowStartDate"] = now
    df["RowEndDate"]   = None  # NULL = actieve rij; ingevuld bij versiewisseling
    return df



# ── Dimensies ────────────────────────────────────────────────────────────────

def transform_dim_date(dimdates_df: pd.DataFrame) -> pd.DataFrame:
    """
    DimDate vanuit dimdates.csv.

    Granulariteit: één rij per jaar (alleen 1 januari), zodat DimDate als
    jaarsdimensie werkt voor FactRating en FactPrincipal.

    Opmerking: kolom 'MonthShortName' in de CSV bevat het JAAR als string
    (bv. '1880') — de naam is misleidend maar de waarde is correct.
    """
    logger.info("Transformeren: DimDate (%d rijen)", len(dimdates_df))

    df = dimdates_df.rename(columns={
        "Date":                 "date",
        "DateShortDescription": "dateShortDescription",
        "DayLongName":          "dateLongName",
        "MonthLongName":        "monthLongName",
        "MonthShortName":       "year",  # bevat het jaar als string ("1880")
    }).copy()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Granulariteit: enkel 1 januari per jaar
    df = df[df["date"].dt.month == 1]
    df = df[df["date"].dt.day == 1].copy()

    df["date"] = df["date"].dt.date
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")

    df = df.dropna(subset=["date"])
    return df[["date", "dateShortDescription", "dateLongName", "monthLongName", "year"]]


def transform_dim_movie(title_basics: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """DimMovie uit title.basics: tconst, titleType, primaryTitle, originalTitle, isAdult."""
    logger.info("Transformeren: DimMovie (%d rijen)", len(title_basics))
    df = title_basics[["tconst", "titleType", "primaryTitle", "originalTitle", "isAdult"]].copy()

    # isAdult: IMDb codeert boolean als '0'/'1' string
    df["isAdult"] = df["isAdult"].map({"1": True, "0": False})

    df = df.dropna(subset=["tconst", "titleType", "primaryTitle", "originalTitle"])
    return _scd2_defaults(df, now)


def transform_dim_genre(title_basics: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """DimGenre uit title.basics (kolom 'genres'): tconst, genreName1/2/3."""
    logger.info("Transformeren: DimGenre")
    df = title_basics[["tconst", "genres"]].dropna(subset=["tconst"]).copy()

    split = _split_column(df["genres"].fillna(""), ",", 3)
    df["genreName1"] = split[0].replace("", None)
    df["genreName2"] = split[1].replace("", None)
    df["genreName3"] = split[2].replace("", None)

    return _scd2_defaults(df[["tconst", "genreName1", "genreName2", "genreName3"]], now)


def transform_dim_person(name_basics: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """DimPerson uit name.basics: nconst, primaryName."""
    logger.info("Transformeren: DimPerson (%d rijen)", len(name_basics))
    df = name_basics[["nconst", "primaryName"]].dropna(subset=["nconst"]).copy()
    return _scd2_defaults(df, now)


def transform_dim_profession(name_basics: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """DimProfession uit name.basics (kolom 'primaryProfession'): nconst, professionName1/2/3."""
    logger.info("Transformeren: DimProfession")
    df = name_basics[["nconst", "primaryProfession"]].dropna(subset=["nconst"]).copy()

    split = _split_column(df["primaryProfession"].fillna(""), ",", 3)
    df["professionName1"] = split[0].replace("", None)
    df["professionName2"] = split[1].replace("", None)
    df["professionName3"] = split[2].replace("", None)

    return _scd2_defaults(df[["nconst", "professionName1", "professionName2", "professionName3"]], now)


def transform_dim_known_for_title(name_basics: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """
    DimKnownForTitle uit name.basics (kolom 'knownForTitles'): nconst, knownForTitleId1…4.

    nconst is de business key: één rij per persoon. Personen zonder enige
    knownForTitle (knownForTitleId1 is NULL) worden uitgesloten.
    """
    logger.info("Transformeren: DimKnownForTitle")
    df = name_basics[["nconst", "knownForTitles"]].dropna(subset=["nconst"]).copy()

    split = _split_column(df["knownForTitles"].fillna(""), ",", 4)
    df["knownForTitleId1"] = split[0].replace("", None)
    df["knownForTitleId2"] = split[1].replace("", None)
    df["knownForTitleId3"] = split[2].replace("", None)
    df["knownForTitleId4"] = split[3].replace("", None)

    df = df.dropna(subset=["knownForTitleId1"])
    return _scd2_defaults(
        df[["nconst", "knownForTitleId1", "knownForTitleId2",
            "knownForTitleId3", "knownForTitleId4"]],
        now,
    )


def transform_dim_category(title_principals: pd.DataFrame, now: datetime) -> pd.DataFrame:
    """DimCategory uit title.principals: unieke (category, job)-combinaties."""
    logger.info("Transformeren: DimCategory")
    df = (
        title_principals[["category", "job"]]
        .drop_duplicates(subset=["category", "job"])
        .reset_index(drop=True)
    )
    return _scd2_defaults(df, now)


def transform_dim_country(iban_df: pd.DataFrame) -> pd.DataFrame:
    """
    DimCountry vanuit iban.csv (ISO 3166-1 landcodes).

    Verwachte invoerkolommen: Country, Alpha Code 2, Alpha Code 3, Number.
    Geen SCD-2: geen RowStartDate / RowEndDate.
    """
    logger.info("Transformeren: DimCountry (%d rijen)", len(iban_df))

    df = iban_df.rename(columns={
        "Country":      "country",
        "Alpha Code 2": "alpha_code_2",
        "Alpha Code 3": "alpha_code_3",
        "Number":       "number",
    }).copy()

    df["number"] = pd.to_numeric(df["number"], errors="coerce").astype("Int64")

    df = df.dropna(subset=["alpha_code_2"]).drop_duplicates(subset=["alpha_code_2"])
    return df[["country", "alpha_code_2", "alpha_code_3", "number"]]


def transform_dim_alternative_title(
    title_akas: pd.DataFrame,
    movie_sk_map: dict[str, int],   # tconst → movie_sk
    country_sk_map: dict[str, int], # alpha_code_2 → country_sk
    now: datetime,
) -> pd.DataFrame:
    """
    DimAlternativeTitle uit title.akas. Vereist opgeloste FK's.

    dimCountryKey kan NULL zijn: IMDb gebruikt soms regio-codes (bv. 'XWW')
    die niet in de ISO 3166-1 standaard voorkomen en dus niet worden gevonden.
    Rijen zonder dimMovieKey of zonder titel worden volledig uitgesloten.
    """
    logger.info("Transformeren: DimAlternativeTitle (%d rijen)", len(title_akas))
    df = title_akas[["titleId", "ordering", "title", "region", "language",
                      "types", "isOriginalTitle"]].copy()

    df["dimMovieKey"]   = df["titleId"].map(movie_sk_map)
    df["dimCountryKey"] = df["region"].map(country_sk_map)

    # isOriginalTitle: IMDb codeert boolean als '0'/'1' string
    df["isOriginalTitle"] = df["isOriginalTitle"].map({"1": True, "0": False})

    df["ordering"] = pd.to_numeric(df["ordering"], errors="coerce").astype("Int64")

    df = df.dropna(subset=["dimMovieKey", "title"])

    result = df[[
        "dimMovieKey", "dimCountryKey", "ordering", "title",
        "language", "types", "isOriginalTitle",
    ]].copy()

    return _scd2_defaults(result, now)


# ── Feiten ───────────────────────────────────────────────────────────────────

def transform_fact_rating(
    title_basics: pd.DataFrame,
    title_ratings: pd.DataFrame,
    movie_sk_map: dict[str, int],   # tconst → movie_sk
    genre_sk_map: dict[str, int],   # tconst → genre_sk
    date_sk_map: dict[int, int],    # year   → date_sk
) -> pd.DataFrame:
    """
    FactRating: inner join van title.basics (runtime, jaren) + title.ratings.

    Rijen zonder dimMovieKey worden uitgesloten. Overige FK's (genre, jaar)
    mogen NULL zijn als de dimensierij ontbreekt.
    """
    logger.info("Transformeren: FactRating")

    df = title_basics.merge(title_ratings, on="tconst", how="inner")

    df["startYear"]      = pd.to_numeric(df["startYear"],      errors="coerce").astype("Int64")
    df["endYear"]        = pd.to_numeric(df["endYear"],        errors="coerce").astype("Int64")
    df["runtimeMinutes"] = pd.to_numeric(df["runtimeMinutes"], errors="coerce").astype("Int64")
    df["averageRating"]  = pd.to_numeric(df["averageRating"],  errors="coerce")
    df["numVotes"]       = pd.to_numeric(df["numVotes"],       errors="coerce").astype("Int64")

    df["dimMovieKey"]     = df["tconst"].map(movie_sk_map)
    df["dimGenreKey"]     = df["tconst"].map(genre_sk_map)
    df["dimStartYearKey"] = df["startYear"].map(date_sk_map)
    df["dimEndYearKey"]   = df["endYear"].map(date_sk_map)

    df = df.dropna(subset=["dimMovieKey"])

    return df[[
        "dimMovieKey", "dimGenreKey", "dimStartYearKey", "dimEndYearKey",
        "runtimeMinutes", "averageRating", "numVotes",
    ]].rename(columns={"runtimeMinutes": "movieRunTimeMinutes"})


def transform_fact_principal(
    title_principals: pd.DataFrame,
    name_basics: pd.DataFrame,
    movie_sk_map: dict[str, int],
    person_sk_map: dict[str, int],
    category_sk_map: dict[tuple, int],   # (category, job) → category_sk
    knownfortitle_sk_map: dict[str, int], # nconst → knownForTitle_sk
    profession_sk_map: dict[str, int],    # nconst → profession_sk
    date_sk_map: dict[int, int],          # year   → date_sk
) -> pd.DataFrame:
    """
    FactPrincipal: koppeling van title.principals + name.basics.

    Verplichte FK's: dimMovieKey, dimPersonKey — rijen zonder deze worden
    uitgesloten. Overige FK's (category, knownForTitle, profession, jaar)
    mogen NULL zijn als de corresponderende dimensierij ontbreekt.
    """
    logger.info("Transformeren: FactPrincipal (%d rijen)", len(title_principals))

    df = title_principals[["tconst", "nconst", "category", "job"]].copy()

    # Geboorte-/sterfjaar ophalen via left join op nconst
    name_extra = name_basics[["nconst", "birthYear", "deathYear"]].copy()
    name_extra["birthYear"] = pd.to_numeric(name_extra["birthYear"], errors="coerce").astype("Int64")
    name_extra["deathYear"] = pd.to_numeric(name_extra["deathYear"], errors="coerce").astype("Int64")
    df = df.merge(name_extra[["nconst", "birthYear", "deathYear"]], on="nconst", how="left")

    df["dimMovieKey"]         = df["tconst"].map(movie_sk_map)
    df["dimPersonKey"]        = df["nconst"].map(person_sk_map)
    df["dimCategoryKey"]      = df.apply(
        lambda r: category_sk_map.get((r["category"], r["job"])), axis=1
    )
    # DimKnownForTitle is geïndexeerd op nconst (één rij per persoon)
    df["dimKnownForTitleKey"] = df["nconst"].map(knownfortitle_sk_map)
    df["dimProfessionKey"]    = df["nconst"].map(profession_sk_map)
    df["dimBirthYearKey"]     = df["birthYear"].map(date_sk_map)
    df["dimDeathYearKey"]     = df["deathYear"].map(date_sk_map)

    df = df.dropna(subset=["dimMovieKey", "dimPersonKey"])

    return df[[
        "dimMovieKey", "dimPersonKey", "dimCategoryKey",
        "dimKnownForTitleKey", "dimProfessionKey",
        "dimBirthYearKey", "dimDeathYearKey",
    ]]

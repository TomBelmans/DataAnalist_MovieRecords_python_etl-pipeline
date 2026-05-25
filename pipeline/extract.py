"""
extract.py – Lees bronbestanden uit de lokale Staging-map.

De Staging-map bevat:
    title.basics.tsv        → DimMovie, DimGenre
    title.ratings.tsv       → FactRating
    title.akas.tsv          → DimAlternativeTitle
    name.basics.tsv         → DimPerson, DimProfession, DimKnownForTitle
    title.principals.tsv    → FactPrincipal
    dimdates.csv            → DimDate  (reeds gegenereerd, dagelijkse rijen)
    iban.csv                → DimCountry (ISO 3166-1 landcodes)

Alle TSV-bestanden gebruiken tab als scheidingsteken en '\\N' voor NULL.
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

STAGING_TSV_FILES: dict[str, str] = {
    "title_basics":     "title.basics.tsv",
    "title_ratings":    "title.ratings.tsv",
    "title_akas":       "title.akas.tsv",
    "name_basics":      "name.basics.tsv",
    "title_principals": "title.principals.tsv",
}

STAGING_CSV_FILES: dict[str, str] = {
    "dimdates": "dimdates.csv",
    "iban":     "iban.csv",
}


# ── Lezers ───────────────────────────────────────────────────────────────────

def read_tsv(filepath: Path) -> pd.DataFrame:
    """
    Lees een IMDb TSV-bestand.
    '\\N' wordt automatisch omgezet naar NaN.
    Alle kolommen worden ingelezen als string om type-conversies later te beheren.
    """
    logger.info("Inlezen TSV: %s ...", filepath.name)
    df = pd.read_csv(
        filepath,
        sep="\t",
        na_values=["\\N"],
        dtype=str,
        low_memory=False,
        compression="infer",   # werkt voor zowel .tsv als .tsv.gz
    )
    logger.info("  → %d rijen, %d kolommen", len(df), len(df.columns))
    return df


def read_csv(filepath: Path) -> pd.DataFrame:
    """
    Lees een CSV-bestand met standaard instellingen.
    """
    logger.info("Inlezen CSV: %s ...", filepath.name)
    df = pd.read_csv(filepath, dtype=str, low_memory=False)
    logger.info("  → %d rijen, %d kolommen", len(df), len(df.columns))
    return df


# ── Hoofd extract-functie ────────────────────────────────────────────────────

def extract_all(staging_dir: Path) -> dict[str, pd.DataFrame]:
    """
    Lees alle bronbestanden uit de opgegeven Staging-map.

    Args:
        staging_dir: Pad naar de map met de staging-bestanden
                     (bv. Path('Staging') of Path('C:/School/python/movieRecords/Staging')).

    Returns:
        Dict met alias → DataFrame:
            'title_basics', 'title_ratings', 'title_akas',
            'name_basics', 'title_principals', 'dimdates', 'iban'

    Raises:
        FileNotFoundError: Als een verwacht bestand ontbreekt in staging_dir.
    """
    if not staging_dir.exists():
        raise FileNotFoundError(
            f"Staging-map niet gevonden: {staging_dir}\n"
            "Controleer het pad of stel STAGING_DIR in in je .env bestand."
        )

    dataframes: dict[str, pd.DataFrame] = {}

    # TSV-bestanden
    for alias, filename in STAGING_TSV_FILES.items():
        filepath = staging_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(
                f"Verwacht bestand ontbreekt in Staging: {filename}\n"
                f"Volledig pad: {filepath}"
            )
        dataframes[alias] = read_tsv(filepath)

    # CSV-bestanden
    for alias, filename in STAGING_CSV_FILES.items():
        filepath = staging_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(
                f"Verwacht bestand ontbreekt in Staging: {filename}\n"
                f"Volledig pad: {filepath}"
            )
        dataframes[alias] = read_csv(filepath)

    logger.info(
        "Extractie klaar — %d bronbestanden ingelezen uit %s",
        len(dataframes), staging_dir,
    )
    return dataframes

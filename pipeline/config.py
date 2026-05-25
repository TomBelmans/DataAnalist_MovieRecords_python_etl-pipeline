"""
config.py – Laadt omgevingsvariabelen en stelt de databaseverbinding in.

Gebruik:
    from config import DB_CONFIG, DATA_DIR
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Database configuratie ────────────────────────────────────────────────────

DB_CONFIG: dict = {
    "host":     os.getenv("DB_HOST"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME", "postgres"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
    # Verbindingstimeout in seconden
    "connect_timeout": 10,  # seconden
    # Docker gebruikt standaard 5432
}

# ── Database schema ──────────────────────────────────────────────────────────

DB_SCHEMA: str = os.getenv("DB_SCHEMA", "MovieRecordsDW")

# ── Bestandspaden ────────────────────────────────────────────────────────────

STAGING_DIR: Path = Path(os.getenv("STAGING_DIR", "./Staging"))

# Achterwaartse compatibiliteit
DATA_DIR: Path = STAGING_DIR

# ── Logging ──────────────────────────────────────────────────────────────────

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def validate_config() -> None:
    """Controleer of alle verplichte omgevingsvariabelen aanwezig zijn."""
    required = ["DB_HOST", "DB_PASSWORD"]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise EnvironmentError(
            f"Ontbrekende omgevingsvariabelen: {', '.join(missing)}\n"
            "Kopieer .env naar je eigen waarden en vul Docker-gegevens in."
        )

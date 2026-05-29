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

DB_AUTH: str = os.getenv("DB_AUTH", "sql").lower()

DB_CONFIG: dict = {
    "host":            os.getenv("DB_HOST"),
    "port":            int(os.getenv("DB_PORT", 1433)),
    "dbname":          os.getenv("DB_NAME", "MovieRecordsDW"),
    "auth":            DB_AUTH,
    "connect_timeout": 10,
}

if DB_AUTH == "sql":
    DB_CONFIG["user"]     = os.getenv("DB_USER", "sa")
    DB_CONFIG["password"] = os.getenv("DB_PASSWORD")

# ── Database schema ──────────────────────────────────────────────────────────

DB_SCHEMA: str = os.getenv("DB_SCHEMA", "dbo")

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
    required = ["DB_HOST"]
    if DB_AUTH == "sql":
        required.append("DB_PASSWORD")
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise EnvironmentError(
            f"Ontbrekende omgevingsvariabelen: {', '.join(missing)}\n"
            "Vul de juiste waarden in .env in."
        )

# MovieRecords ETL

Python-implementatie van de **MovieRecords** datawarehouse-pipeline. Laadt IMDb-stagingbestanden in een PostgreSQL-datawarehouse — dezelfde laadvolgorde en SCD-2-logica als het oorspronkelijke SSIS-pakket (`movierecords_initLoad`).

---

## Overzicht

| Onderdeel | Beschrijving |
|-----------|--------------|
| **Bron** | Lokale staging-bestanden (TSV/CSV) uit IMDb-datasets |
| **Doel** | Schema `MovieRecordsDW` op PostgreSQL |
| **Patroon** | ETL: Extract → Transform → Load |
| **Dimensies** | SCD Type 2 (historiek via `RowStartDate` / `RowEndDate`) |
| **Feiten** | Truncate-and-reload (`FactRating`, `FactPrincipal`) |

---

## Architectuur

### Procesflow

`main.py` orkestreert de volledige pipeline in vier fasen:

```mermaid
flowchart LR
    ENV[(".env")]
    STAGING[("staging/\nTSV · CSV")]
    DB[("PostgreSQL\nMovieRecordsDW")]

    ENV --> config["config.py\n① .env laden\nverbinding valideren"]
    STAGING --> extract["extract.py\n② bronbestanden inlezen\n→ raw DataFrames"]

    config & extract --> main["main.py\nOrchestrator\nrun_pipeline()"]

    main --> transform["transform.py\n③ kolommen hernoemen\ntypes converteren\nFK-maps koppelen"]
    transform -->|"DW DataFrames"| load["load.py\n④ SCD-2 vergelijking\nINSERT · expire · reload"]
    config -.->|"DB_CONFIG"| load
    load --> DB
```

### Laadvolgorde (FK-afhankelijkheden)

```mermaid
flowchart TD
    subgraph stap1 ["Stap 1 — geen FK-afhankelijkheden"]
        direction LR
        DimDate
        DimMovie
        DimGenre
        DimCountry
        DimPerson
        DimCategory
        DimKnownForTitle
        DimProfession
    end

    DimMovie & DimCountry --> DimAlternativeTitle

    DimMovie & DimGenre & DimDate --> FactRating

    DimMovie & DimPerson & DimCategory & DimKnownForTitle & DimProfession & DimDate --> FactPrincipal
```

> Feitentabellen altijd ná alle dimensies laden, anders falen de FK-lookups stilletjes (NULL-waarden) of crashen ze.

---

## Projectstructuur

```
movieRecords/
├── pipeline/               # ETL-kernpakket
│   ├── __init__.py
│   ├── config.py           # .env laden, DB_CONFIG, validate_config()
│   ├── extract.py          # Bronbestanden → raw DataFrames
│   ├── transform.py        # DataFrames → DW-schema (kolommen, types, FK's)
│   └── load.py             # SCD-2, statische dims, feit-tabellen, SK-maps
├── sql/
│   ├── create_tables.sql   # Eenmalig uitvoeren om het schema aan te maken
│   ├── truncate_tables.sql
│   └── erd.png             # Afbeelding van het Entity Relationship Diagram, gegenereerd in pgAdmin4
├── docker/
│   ├── docker-compose.yml
│   ├── pg_hba.conf         # PostgreSQL authenticatieconfiguratie
│   └── postgresql.conf     # PostgreSQL serverconfiguratie
├── staging/                # Bronbestanden (TSV + CSV, gitignored)
├── main.py                 # Entry point / CLI-orchestrator
├── check_db.py             # Verbindings- en schemaverificatie
├── requirements.txt
└── .env                    # Credentials (deze moet zelf aangemaakt worden, gitignored)
```

---

## Bronbestanden en DW-tabellen

Staging-bestanden horen in de map die je instelt via `STAGING_DIR` (standaard `./Staging`):

| Bestand | Alias in code | DW-tabel(len) | Laadtype |
|---------|---------------|---------------|----------|
| `title.basics.tsv` | `title_basics` | DimMovie, DimGenre | SCD-2 |
| `title.ratings.tsv` | `title_ratings` | FactRating | Feit |
| `title.akas.tsv` | `title_akas` | DimAlternativeTitle | SCD-2 |
| `name.basics.tsv` | `name_basics` | DimPerson, DimProfession, DimKnownForTitle | SCD-2 |
| `title.principals.tsv` | `title_principals` | DimCategory, FactPrincipal | SCD-2 / Feit |
| `dimdates.csv` | `dimdates` | DimDate | Statisch |
| `iban.csv` | `iban` | DimCountry | Statisch |

TSV-bestanden gebruiken tab als scheidingsteken; `\N` staat voor NULL. Gecomprimeerde bestanden (`.tsv.gz`) worden automatisch herkend.

---

## Installatie

**Vereisten:** Python 3.11+, PostgreSQL (lokaal via Docker of extern)

```powershell
cd c:\<bestandslocatie>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

In de IDE: kies als interpreter `.venv\Scripts\python.exe`.

---

## Configuratie

Maak een `.env` in de root van je projectmap:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=<jouw-wachtwoord>

STAGING_DIR=./Staging
DB_SCHEMA=MovieRecordsDW
LOG_LEVEL=INFO
```

| Variabele | Verplicht | Standaard | Beschrijving |
|-----------|-----------|-----------|--------------|
| `DB_HOST` | **Ja** | — | Hostnaam of IP van de PostgreSQL-server |
| `DB_PASSWORD` | **Ja** | — | Database-wachtwoord |
| `DB_PORT` | Nee | `5432` | Poort |
| `DB_NAME` | Nee | `postgres` | Database-naam |
| `DB_USER` | Nee | `postgres` | Database-gebruiker |
| `STAGING_DIR` | Nee | `./Staging` | Pad naar de staging-bestanden |
| `DB_SCHEMA` | Nee | `MovieRecordsDW` | PostgreSQL-schema |
| `LOG_LEVEL` | Nee | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |

---

## Database opstarten

### Via Docker

```powershell
cd docker
docker compose up -d
```

Docker laadt automatisch `pg_hba.conf` en `postgresql.conf` als volumes. Wacht tot de container `healthy` is:

```powershell
docker compose ps
```

### Schema aanmaken

Voer `sql/create_tables.sql` eenmalig uit (bv. via psql, pgAdmin of een andere SQL-client):

```powershell
psql -h localhost -U postgres -d postgres -f sql/create_tables.sql
```

Controleer daarna de verbinding en het schema:

```powershell
python check_db.py
python check_db.py --table DimMovie
```

---

## Pipeline uitvoeren

```powershell
# Volledige ETL (alle tabellen in FK-veilige volgorde)
python main.py

# Alleen specifieke tabellen
python main.py --tables DimMovie DimGenre
python main.py --tables FactRating
```

---

## Laadstrategie

| Type | Tabellen | Aanpak |
|------|----------|--------|
| **SCD-2** | DimMovie, DimGenre, DimPerson, DimKnownForTitle, DimProfession, DimAlternativeTitle | Historiek via `RowStartDate`/`RowEndDate`; gewijzigde rij afgesloten + nieuwe versie ingevoegd |
| **Statisch** | DimDate, DimCountry | Alleen nieuwe business keys invoegen — geen TRUNCATE, FK's blijven intact |
| **DimCategory** | — | Technisch SCD-2, maar zonder tracked kolommen; gedraagt zich als statische dimensie |
| **Feiten** | FactRating, FactPrincipal | `TRUNCATE` + batch `INSERT`; FactPrincipal in chunks van 50 000 rijen (> 80 M rijen) |

---

## Afhankelijkheden

| Package | Versie | Gebruik |
|---------|--------|---------|
| `pandas` | 3.0.3 | DataFrames en transformaties |
| `psycopg2-binary` | 2.9.12 | PostgreSQL-verbinding |
| `python-dotenv` | 1.2.2 | `.env` laden |
| `pycountry` | 26.2.16 | Landmetadata voor DimCountry |
| `requests` | 2.34.2 | (niet actief in gebruik) |
| `tqdm` | 4.67.3 | (niet actief in gebruik) |

---

## Troubleshooting

| Probleem | Oplossing |
|----------|-----------|
| `Import "pandas" could not be resolved` | Activeer `.venv` en selecteer de juiste Python-interpreter in je editor |
| Staging-map niet gevonden | Controleer `STAGING_DIR` in `.env`; standaard is `./Staging` (hoofdletter S) |
| Schema `MovieRecordsDW` bestaat niet | Voer `sql/create_tables.sql` uit op de database |
| Verbinding mislukt | Controleer `DB_HOST` en `DB_PASSWORD` in `.env`; test met `python check_db.py` |
| FK-fout bij feitentabellen | Dimensies moeten volledig geladen zijn vóór `FactRating`/`FactPrincipal` |
| `KeyError` bij transform | Kolom ontbreekt in kolomselectie `transform.py`; zet `LOG_LEVEL=DEBUG` voor details |
| Feitentabellen leeg na ETL | `LOG_LEVEL=DEBUG` toont FK-lookup statistieken en het aantal NULL-waarden per kolom |
| Rijen met `NULL`-FKs | De corresponderende dimensierij ontbreekt of is niet actief (`RowEndDate IS NULL`) |

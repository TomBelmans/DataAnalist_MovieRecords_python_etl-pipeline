-- ============================================================
-- MovieRecordsDW – PostgreSQL DDL voor PostgreSQL
-- Aanmaak volgorde respecteert FK-afhankelijkheden
-- ============================================================

CREATE SCHEMA IF NOT EXISTS "MovieRecordsDW";

-- ── 1. DimDate ───────────────────────────────────────────────
-- Stabiele jaardimensie (1 rij per jaar, geen SCD-2)
CREATE TABLE IF NOT EXISTS "MovieRecordsDW"."DimDate" (
    "date_sk"               SERIAL          PRIMARY KEY,
    "date"                  DATE            NOT NULL,
    "dateShortDescription"  TEXT,
    "dateLongName"          TEXT,
    "monthLongName"         TEXT,
    "year"                  INTEGER
);

-- ── 2. DimMovie ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "MovieRecordsDW"."DimMovie" (
    "movie_sk"              SERIAL          PRIMARY KEY,
    "tconst"                TEXT            NOT NULL,
    "titleType"             TEXT,
    "primaryTitle"          TEXT,
    "originalTitle"         TEXT,
    "isAdult"               BOOLEAN,
    "RowStartDate"          TIMESTAMP,
    "RowEndDate"            TIMESTAMP
);

-- ── 3. DimGenre ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "MovieRecordsDW"."DimGenre" (
    "genre_sk"              SERIAL          PRIMARY KEY,
    "tconst"                TEXT            NOT NULL,
    "genreName1"            TEXT,
    "genreName2"            TEXT,
    "genreName3"            TEXT,
    "RowStartDate"          TIMESTAMP,
    "RowEndDate"            TIMESTAMP
);

-- ── 4. DimCountry ────────────────────────────────────────────
-- Stabiele referentietabel (geen SCD-2)
CREATE TABLE IF NOT EXISTS "MovieRecordsDW"."DimCountry" (
    "country_sk"            SERIAL          PRIMARY KEY,
    "country"               TEXT,
    "alpha_code_2"          CHAR(2)         NOT NULL,
    "alpha_code_3"          CHAR(3),
    "number"                INTEGER
);

-- ── 5. DimPerson ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "MovieRecordsDW"."DimPerson" (
    "person_sk"             SERIAL          PRIMARY KEY,
    "nconst"                TEXT            NOT NULL,
    "primaryName"           TEXT,
    "RowStartDate"          TIMESTAMP,
    "RowEndDate"            TIMESTAMP
);

-- ── 6. DimCategory ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "MovieRecordsDW"."DimCategory" (
    "category_sk"           SERIAL          PRIMARY KEY,
    "category"              TEXT,
    "job"                   TEXT,
    "RowStartDate"          TIMESTAMP,
    "RowEndDate"            TIMESTAMP
);

-- ── 7. DimKnownForTitle ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS "MovieRecordsDW"."DimKnownForTitle" (
    "knownForTitle_sk"      SERIAL          PRIMARY KEY,
    "nconst"                TEXT            NOT NULL,
    "knownForTitleId1"      TEXT,
    "knownForTitleId2"      TEXT,
    "knownForTitleId3"      TEXT,
    "knownForTitleId4"      TEXT,
    "RowStartDate"          TIMESTAMP,
    "RowEndDate"            TIMESTAMP
);

-- ── 8. DimProfession ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "MovieRecordsDW"."DimProfession" (
    "profession_sk"         SERIAL          PRIMARY KEY,
    "nconst"                TEXT            NOT NULL,
    "professionName1"       TEXT,
    "professionName2"       TEXT,
    "professionName3"       TEXT,
    "RowStartDate"          TIMESTAMP,
    "RowEndDate"            TIMESTAMP
);

-- ── 9. DimAlternativeTitle ───────────────────────────────────
CREATE TABLE IF NOT EXISTS "MovieRecordsDW"."DimAlternativeTitle" (
    "alternativeTitle_sk"   SERIAL          PRIMARY KEY,
    "dimMovieKey"           INTEGER         REFERENCES "MovieRecordsDW"."DimMovie"("movie_sk"),
    "dimCountryKey"         INTEGER         REFERENCES "MovieRecordsDW"."DimCountry"("country_sk"),
    "ordering"              INTEGER,
    "title"                 TEXT,
    "language"              TEXT,
    "types"                 TEXT,
    "isOriginalTitle"       BOOLEAN,
    "RowStartDate"          TIMESTAMP,
    "RowEndDate"            TIMESTAMP
);

-- ── 10. FactRating ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "MovieRecordsDW"."FactRating" (
    "rating_sk"             SERIAL          PRIMARY KEY,
    "dimMovieKey"           INTEGER         REFERENCES "MovieRecordsDW"."DimMovie"("movie_sk"),
    "dimGenreKey"           INTEGER         REFERENCES "MovieRecordsDW"."DimGenre"("genre_sk"),
    "dimStartYearKey"       INTEGER         REFERENCES "MovieRecordsDW"."DimDate"("date_sk"),
    "dimEndYearKey"         INTEGER         REFERENCES "MovieRecordsDW"."DimDate"("date_sk"),
    "movieRunTimeMinutes"   INTEGER,
    "averageRating"         NUMERIC(4,1),
    "numVotes"              INTEGER
);

-- ── 11. FactPrincipal ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS "MovieRecordsDW"."FactPrincipal" (
    "principal_sk"          BIGSERIAL       PRIMARY KEY,
    "dimMovieKey"           INTEGER         REFERENCES "MovieRecordsDW"."DimMovie"("movie_sk"),
    "dimPersonKey"          INTEGER         REFERENCES "MovieRecordsDW"."DimPerson"("person_sk"),
    "dimCategoryKey"        INTEGER         REFERENCES "MovieRecordsDW"."DimCategory"("category_sk"),
    "dimKnownForTitleKey"   INTEGER         REFERENCES "MovieRecordsDW"."DimKnownForTitle"("knownForTitle_sk"),
    "dimProfessionKey"      INTEGER         REFERENCES "MovieRecordsDW"."DimProfession"("profession_sk"),
    "dimBirthYearKey"       INTEGER         REFERENCES "MovieRecordsDW"."DimDate"("date_sk"),
    "dimDeathYearKey"       INTEGER         REFERENCES "MovieRecordsDW"."DimDate"("date_sk")
);

-- ── Indexen op business keys (performance bij SCD-2 lookup) ──
CREATE INDEX IF NOT EXISTS idx_dimmovie_tconst
    ON "MovieRecordsDW"."DimMovie"("tconst") WHERE "RowEndDate" IS NULL;

CREATE INDEX IF NOT EXISTS idx_dimgenre_tconst
    ON "MovieRecordsDW"."DimGenre"("tconst") WHERE "RowEndDate" IS NULL;

CREATE INDEX IF NOT EXISTS idx_dimcountry_alpha2
    ON "MovieRecordsDW"."DimCountry"("alpha_code_2");

CREATE INDEX IF NOT EXISTS idx_dimperson_nconst
    ON "MovieRecordsDW"."DimPerson"("nconst") WHERE "RowEndDate" IS NULL;

CREATE INDEX IF NOT EXISTS idx_dimkft_nconst
    ON "MovieRecordsDW"."DimKnownForTitle"("nconst") WHERE "RowEndDate" IS NULL;

CREATE INDEX IF NOT EXISTS idx_dimprofession_nconst
    ON "MovieRecordsDW"."DimProfession"("nconst") WHERE "RowEndDate" IS NULL;

CREATE INDEX IF NOT EXISTS idx_dimcategory_cat_job
    ON "MovieRecordsDW"."DimCategory"("category", "job") WHERE "RowEndDate" IS NULL;

-- ── 0. Database aanmaken (verbonden als SA op master) ────────
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'MovieRecordsDW')
    CREATE DATABASE MovieRecordsDW;
GO

USE MovieRecordsDW;
GO


-- ── 1. DimDate ───────────────────────────────────────────────
IF OBJECT_ID('[dbo].[DimDate]', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[DimDate] (
        [date_sk]               INT             IDENTITY(1,1)   PRIMARY KEY,
        [date]                  DATE            NOT NULL,
        [dateShortDescription]  NVARCHAR(MAX),
        [dateLongName]          NVARCHAR(MAX),
        [monthLongName]         NVARCHAR(MAX),
        [year]                  INT
    );
END
GO

-- ── 2. DimMovie ──────────────────────────────────────────────
IF OBJECT_ID('[dbo].[DimMovie]', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[DimMovie] (
        [movie_sk]              INT             IDENTITY(1,1)   PRIMARY KEY,
        [tconst]                NVARCHAR(20)    NOT NULL,
        [titleType]             NVARCHAR(50),
        [primaryTitle]          NVARCHAR(500),
        [originalTitle]         NVARCHAR(500),
        [isAdult]               BIT,
        [RowStartDate]          DATETIME2,
        [RowEndDate]            DATETIME2
    );
END
GO

-- ── 3. DimGenre ──────────────────────────────────────────────
IF OBJECT_ID('[dbo].[DimGenre]', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[DimGenre] (
        [genre_sk]              INT             IDENTITY(1,1)   PRIMARY KEY,
        [tconst]                NVARCHAR(20)    NOT NULL,
        [genreName1]            NVARCHAR(100),
        [genreName2]            NVARCHAR(100),
        [genreName3]            NVARCHAR(100),
        [RowStartDate]          DATETIME2,
        [RowEndDate]            DATETIME2
    );
END
GO

-- ── 4. DimCountry ────────────────────────────────────────────
IF OBJECT_ID('[dbo].[DimCountry]', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[DimCountry] (
        [country_sk]            INT             IDENTITY(1,1)   PRIMARY KEY,
        [country]               NVARCHAR(200),
        [alpha_code_2]          CHAR(2)         NOT NULL,
        [alpha_code_3]          CHAR(3),
        [number]                INT
    );
END
GO

-- ── 5. DimPerson ─────────────────────────────────────────────
IF OBJECT_ID('[dbo].[DimPerson]', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[DimPerson] (
        [person_sk]             INT             IDENTITY(1,1)   PRIMARY KEY,
        [nconst]                NVARCHAR(20)    NOT NULL,
        [primaryName]           NVARCHAR(300),
        [RowStartDate]          DATETIME2,
        [RowEndDate]            DATETIME2
    );
END
GO

-- ── 6. DimCategory ───────────────────────────────────────────
IF OBJECT_ID('[dbo].[DimCategory]', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[DimCategory] (
        [category_sk]           INT             IDENTITY(1,1)   PRIMARY KEY,
        [category]              NVARCHAR(100),
        [job]                   NVARCHAR(500),
        [RowStartDate]          DATETIME2,
        [RowEndDate]            DATETIME2
    );
END
GO

-- ── 7. DimKnownForTitle ──────────────────────────────────────
IF OBJECT_ID('[dbo].[DimKnownForTitle]', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[DimKnownForTitle] (
        [knownForTitle_sk]      INT             IDENTITY(1,1)   PRIMARY KEY,
        [nconst]                NVARCHAR(20)    NOT NULL,
        [knownForTitleId1]      NVARCHAR(20),
        [knownForTitleId2]      NVARCHAR(20),
        [knownForTitleId3]      NVARCHAR(20),
        [knownForTitleId4]      NVARCHAR(20),
        [RowStartDate]          DATETIME2,
        [RowEndDate]            DATETIME2
    );
END
GO

-- ── 8. DimProfession ─────────────────────────────────────────
IF OBJECT_ID('[dbo].[DimProfession]', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[DimProfession] (
        [profession_sk]         INT             IDENTITY(1,1)   PRIMARY KEY,
        [nconst]                NVARCHAR(20)    NOT NULL,
        [professionName1]       NVARCHAR(100),
        [professionName2]       NVARCHAR(100),
        [professionName3]       NVARCHAR(100),
        [RowStartDate]          DATETIME2,
        [RowEndDate]            DATETIME2
    );
END
GO

-- ── 9. DimAlternativeTitle ───────────────────────────────────
IF OBJECT_ID('[dbo].[DimAlternativeTitle]', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[DimAlternativeTitle] (
        [alternativeTitle_sk]   INT             IDENTITY(1,1)   PRIMARY KEY,
        [dimMovieKey]           INT             REFERENCES [dbo].[DimMovie]([movie_sk]),
        [dimCountryKey]         INT             REFERENCES [dbo].[DimCountry]([country_sk]),
        [ordering]              INT,
        [title]                 NVARCHAR(MAX),
        [language]              NVARCHAR(20),
        [types]                 NVARCHAR(100),
        [isOriginalTitle]       BIT,
        [RowStartDate]          DATETIME2,
        [RowEndDate]            DATETIME2
    );
END
GO

-- ── 10. FactRating ───────────────────────────────────────────
IF OBJECT_ID('[dbo].[FactRating]', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[FactRating] (
        [ratingId]              INT             IDENTITY(1,1)   PRIMARY KEY,
        [dimMovieKey]           INT             REFERENCES [dbo].[DimMovie]([movie_sk]),
        [dimGenreKey]           INT             REFERENCES [dbo].[DimGenre]([genre_sk]),
        [dimStartYearKey]       INT             REFERENCES [dbo].[DimDate]([date_sk]),
        [dimEndYearKey]         INT             REFERENCES [dbo].[DimDate]([date_sk]),
        [movieRunTimeMinutes]   INT,
        [averageRating]         NUMERIC(4,1),
        [numVotes]              INT
    );
END
GO

-- ── 11. FactPrincipal ────────────────────────────────────────
IF OBJECT_ID('[dbo].[FactPrincipal]', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[FactPrincipal] (
        [principalId]           BIGINT          IDENTITY(1,1)   PRIMARY KEY,
        [dimMovieKey]           INT             REFERENCES [dbo].[DimMovie]([movie_sk]),
        [dimPersonKey]          INT             REFERENCES [dbo].[DimPerson]([person_sk]),
        [dimCategoryKey]        INT             REFERENCES [dbo].[DimCategory]([category_sk]),
        [dimKnownForTitleKey]   INT             REFERENCES [dbo].[DimKnownForTitle]([knownForTitle_sk]),
        [dimProfessionKey]      INT             REFERENCES [dbo].[DimProfession]([profession_sk]),
        [dimBirthYearKey]       INT             REFERENCES [dbo].[DimDate]([date_sk]),
        [dimDeathYearKey]       INT             REFERENCES [dbo].[DimDate]([date_sk])
    );
END
GO

-- ── Indexen op business keys (performance bij SCD-2 lookup) ──
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_dimmovie_tconst'
               AND object_id = OBJECT_ID('[dbo].[DimMovie]'))
    CREATE INDEX idx_dimmovie_tconst
        ON [dbo].[DimMovie]([tconst])
        WHERE [RowEndDate] IS NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_dimgenre_tconst'
               AND object_id = OBJECT_ID('[dbo].[DimGenre]'))
    CREATE INDEX idx_dimgenre_tconst
        ON [dbo].[DimGenre]([tconst])
        WHERE [RowEndDate] IS NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_dimcountry_alpha2'
               AND object_id = OBJECT_ID('[dbo].[DimCountry]'))
    CREATE INDEX idx_dimcountry_alpha2
        ON [dbo].[DimCountry]([alpha_code_2]);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_dimperson_nconst'
               AND object_id = OBJECT_ID('[dbo].[DimPerson]'))
    CREATE INDEX idx_dimperson_nconst
        ON [dbo].[DimPerson]([nconst])
        WHERE [RowEndDate] IS NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_dimkft_nconst'
               AND object_id = OBJECT_ID('[dbo].[DimKnownForTitle]'))
    CREATE INDEX idx_dimkft_nconst
        ON [dbo].[DimKnownForTitle]([nconst])
        WHERE [RowEndDate] IS NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_dimprofession_nconst'
               AND object_id = OBJECT_ID('[dbo].[DimProfession]'))
    CREATE INDEX idx_dimprofession_nconst
        ON [dbo].[DimProfession]([nconst])
        WHERE [RowEndDate] IS NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_dimcategory_cat_job'
               AND object_id = OBJECT_ID('[dbo].[DimCategory]'))
    CREATE INDEX idx_dimcategory_cat_job
        ON [dbo].[DimCategory]([category], [job])
        WHERE [RowEndDate] IS NULL;
GO

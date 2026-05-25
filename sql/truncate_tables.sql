TRUNCATE TABLE
    "MovieRecordsDW"."FactPrincipal",
    "MovieRecordsDW"."FactRating",
    "MovieRecordsDW"."DimAlternativeTitle",
    "MovieRecordsDW"."DimMovie",
    "MovieRecordsDW"."DimGenre",
    "MovieRecordsDW"."DimPerson",
    "MovieRecordsDW"."DimCategory",
    "MovieRecordsDW"."DimKnownForTitle",
    "MovieRecordsDW"."DimProfession",
    "MovieRecordsDW"."DimCountry",
    "MovieRecordsDW"."DimDate"
RESTART IDENTITY CASCADE;
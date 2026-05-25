"""
pipeline – ETL-kernpakket voor MovieRecords.

Modules:
    config    – Omgevingsvariabelen en databaseconfiguratie
    extract   – Inlezen staging-bestanden naar DataFrames
    transform – Mapping bron-DataFrames naar DW-schema
    load      – SCD-2 en feit-tabel laadlogica
"""

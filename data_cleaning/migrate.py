import polars as pl
from sqlalchemy import create_engine, inspect
import os

# Postgres Connection URI
POSTGRES_USERNAME = os.getenv("POSTGRES_USERNAME")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_DATABASE = os.getenv("POSTGRES_DATABASE")

# MSSQL Connection URI
MSSQL_USERNAME = os.getenv("MSSQL_USERNAME")
MSSQL_PASSWORD = os.getenv("MSSQL_PASSWORD")
MSSQL_HOST = os.getenv("MSSQL_HOST")
MSSQL_PORT = os.getenv("MSSQL_PORT")
MSSQL_DATABASE = os.getenv("MSSQL_DATABASE")

# Connection URIs
uri_mssql = f"mssql://{MSSQL_USERNAME}:{MSSQL_PASSWORD}@{MSSQL_HOST}:{MSSQL_PORT}/{MSSQL_DATABASE}?driver=ODBC+Driver+18+for+SQL+Server&encrypt=yes&trustServerCertificate=yes"
uri_pg = f"postgresql://{POSTGRES_USERNAME}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DATABASE}"

# 1. Get all table names from MSSQL
# We use SQLAlchemy's inspector to find only the "Base Tables" (ignoring system views)
mssql_engine = create_engine(uri_mssql)
inspector = inspect(mssql_engine)
tables = inspector.get_table_names()

print(f"Found {len(tables)} tables to migrate: {tables}")

# 2. Loop and Migrate
for table in tables:
    try:
        print(f"Migrating {table}...")
        # Use connectorx for high-speed extraction
        df = pl.read_database_uri(
            query=f"SELECT * FROM {table}", uri=uri_mssql, engine="connectorx"
        )

        # Write to Postgres
        df.write_database(
            table_name=table.lower(),  # Postgres prefers lowercase table names
            connection=uri_pg,
            if_table_exists="replace",
            engine="adbc",
        )
        print(f"Successfully migrated {table} ({len(df)} rows)")
    except Exception as e:
        print(f"Failed to migrate {table}: {e}")

print("\nFull Database Migration Complete.")

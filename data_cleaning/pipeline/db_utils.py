import os
from dotenv import load_dotenv

load_dotenv()


def get_mssql_connection_uri():
    """Builds the MSSQL connection URI from environment variables."""
    vars = [
        "MSSQL_USERNAME",
        "MSSQL_PASSWORD",
        "MSSQL_HOST",
        "MSSQL_PORT",
        "MSSQL_DATABASE",
    ]
    config = {v: os.getenv(v) for v in vars}

    if not all(config.values()):
        raise ValueError(
            f"Missing database environment variables: {[v for v, val in config.items() if not val]}"
        )

    return f"mssql+pyodbc://{config['MSSQL_USERNAME']}:{config['MSSQL_PASSWORD']}@{config['MSSQL_HOST']}:{config['MSSQL_PORT']}/{config['MSSQL_DATABASE']}"


def get_pg_connection_uri():
    """Builds the Postgres connection URI from environment variables."""
    vars = [
        "POSTGRES_USERNAME",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DATABASE",
    ]
    config = {v: os.getenv(v) for v in vars}

    if not all(config.values()):
        raise ValueError(
            f"Missing database environment variables: {[v for v, val in config.items() if not val]}"
        )

    return f"postgresql://{config['POSTGRES_USERNAME']}:{config['POSTGRES_PASSWORD']}@{config['POSTGRES_HOST']}:{config['POSTGRES_PORT']}/{config['POSTGRES_DATABASE']}"

import polars as pl
from db_utils import get_mssql_connection_uri, get_pg_connection_uri
from calculateVelocity import calculate_abc_velocity  # Your Final Velocity Engine


def run_transaction_stream():
    try:
        uri_mssql = get_mssql_connection_uri()
        uri_pg = get_pg_connection_uri()

        print("--- Stream B: Fetching 128k Transactions ---")
        # We only pull the columns we need to save memory
        query = """
            SELECT "StockCode", "DocumentNo", "DocumentType",
                   "LocationCode", "LocationBaseQty", "DocumentDate"
            FROM dbo.wmstransaction
        """
        df_tx = pl.read_database_uri(query, uri_mssql)

        print("--- Stream B: Executing Velocity Engine ---")
        # This applies the 'Unique Document' and 'Sign-Logic' we built
        df_velocity = calculate_abc_velocity(df_tx)

        print("--- Stream B: Saving Velocity to PostgreSQL ---")
        df_velocity.write_database(
            table_name="refined_velocity_master",
            connection=uri_pg,
            if_table_exists="replace",
            engine="adbc",
        )
        print("Stream B Completed Successfully.")

    except Exception as e:
        print(f"!!! Stream B Failed: {e} !!!")


if __name__ == "__main__":
    run_transaction_stream()

from main_pipeline import run_pipeline
from transaction_pipeline import run_transaction_stream
import polars as pl
from db_utils import get_pg_connection_uri
from db_utils import get_mssql_connection_uri
from location_master import generate_location_master
from cleanMissingLocations import cure_missing_locations


def create_optimization_master():
    try:
        uri_pg = get_pg_connection_uri()
        uri_mssql = get_mssql_connection_uri()
        print("--- Step 7: Consolidating the Golden Table ---")

        # 1. Load Cured Physical Data (Stream A)
        # We select only columns needed for 3D modeling and category constraints
        df_stock = pl.read_database_uri(
            """
            SELECT
                "StockCode",
                "Description",
                "clean_stock_code",
                "PrincipalGroup",
                "refined_category",
                "refined_hazard_class",
                "is_cold_room",
                "Cubic_Vol_Fixed",
                "Height_Fixed",
                "Weight_Fixed",
                "PalletRatio_Cleaned",
                "CartonRatio_Cleaned"
            FROM refined_stock_master
        """,
            uri_pg,
        )

        # 2. Load Labor Intelligence (Stream B)
        df_vel = pl.read_database_uri(
            """
            SELECT "StockCode", "Total_Hits", "Velocity_Class", "Total_Qty_Moved"
            FROM refined_velocity_master
        """,
            uri_pg,
        )

        # 3. Fetch Current addresses from MSSQL (Stream C)
        # This provides the 'Before' snapshot for distance calculation
        loc_query = 'SELECT "StockCode", "LocationCode" FROM dbo.admlocationinventory WHERE Quantity > 0'
        df_loc_raw = pl.read_database_uri(loc_query, uri_mssql)

        df_loc = df_loc_raw.group_by("StockCode").agg(
            [
                pl.col("LocationCode").first().alias("Primary_Location"),
                pl.col("LocationCode").count().alias("Bin_Count"),
                pl.col("LocationCode").str.concat(", ").alias("All_Locations"),
            ]
        )

        # 4. Generate Static Location Data and Normalize Join Keys
        df_locations = generate_location_master()

        # Normalize Primary_Location to ensure 2-digit area (e.g., FE-1-10 -> FE-01-10)
        # This handles the "both is valid" requirement
        df_loc = df_loc.with_columns(
            pl.col("Primary_Location")
            .str.replace(r"-(\d)-", r"-0$1-")
            .alias("Primary_Location_Fixed")
        )

        # 5. The Quad Join
        master_df = df_stock.join(df_vel, on="StockCode", how="left")
        master_df = master_df.join(df_loc, on="StockCode", how="left")
        master_df = master_df.join(
            df_locations,
            left_on="Primary_Location_Fixed",
            right_on="location_id",
            how="left",
        )

        # 6. Final Imputations for the 'Digital Twin'
        master_df = master_df.with_columns(
            [
                pl.col("Velocity_Class").fill_null("C"),
                pl.col("Total_Hits").fill_null(0),
            ]
        )

        # 7. Final Imputations for the 'Digital Twin'
        transaction_df = pl.read_database_uri(
            """
            SELECT
                "StockCode",
                "DocumentDate",
                "LocationCode",
                "DocumentType"
            FROM dbo.wmstransaction
            WHERE "DocumentType" IN ('PICK', 'PWAY', 'RECV')
        """,
            uri_mssql,
        )
        master_df = cure_missing_locations(master_df, transaction_df)
        print(
            master_df.select(
                ["StockCode", "Primary_Location", "Derived_Location", "Cured_Location"]
            ).head()
        )

        # 8. Save final Golden Table
        master_df.write_database(
            table_name="optimization_master",
            connection=uri_pg,
            if_table_exists="replace",
            engine="adbc",
        )
        print(f"Golden Table Created with {len(master_df.columns)} essential columns.")

        master_df.write_csv("optimization_master.csv")

    except Exception as e:
        print(f"!!! Merge Failed: {e} !!!")


if __name__ == "__main__":
    run_main = input("Run Main Pipeline? [y/n]: ")

    if run_main == "y":
        run_pipeline()
    else:
        print("Skipping Main Pipeline.")

    run_transaction = input("Run Transaction Pipeline? [y/n]: ")

    if run_transaction == "y":
        run_transaction_stream()
    else:
        print("Skipping Transaction Pipeline.")

    create_optimization_master()

import polars as pl
import spacy

# Initialize spaCy (disable unnecessary components for performance)
# Consider making this lazy loaded in the functions to avoid loading if not used
nlp = None


def get_nlp():
    global nlp
    if nlp is None:
        nlp = spacy.load("en_core_web_sm", disable=["ner"])
    return nlp


def lemmatize_batch(series: pl.Series) -> pl.Series:
    nlp = get_nlp()
    docs = nlp.pipe(series.fill_null("").to_list(), batch_size=1000)
    return pl.Series([" ".join([t.lemma_.lower() for t in doc]) for doc in docs])


def nlp_preprocess(series: pl.Series) -> pl.Series:
    nlp = get_nlp()
    docs = nlp.pipe(series.fill_null("").to_list(), batch_size=1000)
    data = []
    for doc in docs:
        lemmas = [t.lemma_.lower() for t in doc]
        root = ""
        for token in doc:
            if token.dep_ == "ROOT":
                root = token.lemma_.lower()
                break
        data.append({"clean": " ".join(lemmas), "root": root})
    return pl.Series(data)


def refine_stock_master(df: pl.DataFrame) -> pl.DataFrame:
    # 1. NLP Pre-processing
    df = (
        df.with_columns(
            pl.col("Description").map_batches(nlp_preprocess).alias("nlp_features")
        )
        .unnest("nlp_features")
        .rename({"clean": "clean_description", "root": "root_description"})
    )

    df = df.with_columns(
        pl.col("StockCode").map_batches(lemmatize_batch).alias("clean_stock_code")
    )

    # 2. Define Keywords
    hazard_patterns = {
        "Flammable": r"(?i)\b(flammable|fire|spirit|alcohol|solvent|ignite|perfume|deodorant|fragrance)\b",
        "Corrosive": r"(?i)\b(acid|corrosive|caustic|alkali|chemical|sulfuric)\b",
        "Toxic": r"(?i)\b(poison|toxic|pesticide|insecticide|hazard)\b",
        "Fertilizer": r"(\d+\s*-\s*\d+\s*-\s*\d+|\bagri\b|\bnpk\b|\bfertilizer\b)",
    }

    category_patterns = {
        "Food": r"(?i)\b(durum|rice|sugar|flour|food|grain|organic|pasta|meat|fish|cake|skewer|sauce|slice|eggplant|lotus root|pork|chicken|beef|mutton|vegetable|fruit|seasoning|dumpling|drink|tiger|tsingtao)\b",
        "Packaging": r"(?i)\b(bag|plastic|packaging|box|wrap|container)\b",
        "Crockery_Equipment": r"(?i)\b(cup|spoon|basket|tray|bowl|molded|melamine|wooden|injection)\b",
        "Uniform": r"(?i)\b(uniform|apron|mask|t\s*-\s*shirt|waistcoat)\b",
        "Electronics": r"(?i)\b(tv|hanger|sign|microwave|steamer|monitor|cable|plug|switch|sensor|battery|module|electronics|freezer|fryer|machine)\b",
        "Chemical": r"(?i)\b(perfume|deodorant|scent|fragrance|chemical|solvent|alcohol|acid|alkali|caustic|corrosive|sulfuric)\b",
    }

    # Manual Overrides
    df = df.with_columns(
        pl.when(
            pl.col("PrincipalCode").is_null()
            & (
                pl.col("clean_description").str.contains(r"(?i)\bgift set\b")
                | pl.col("clean_description").str.contains(r"(?i)\bbody mist\b")
            )
        )
        .then(pl.lit("I SCENT"))
        .when(
            pl.col("PrincipalCode").is_null()
            & pl.col("clean_description").str.contains(r"(?i)\braudhah borneo\b")
        )
        .then(pl.lit("DIFAN"))
        .otherwise(pl.col("PrincipalCode"))
        .alias("PrincipalCode")
    )

    # 3. Apply Refinement Layer
    df = df.with_columns(
        pl.when(
            pl.col("clean_description").str.contains(hazard_patterns["Flammable"])
            | pl.col("clean_stock_code").str.contains(hazard_patterns["Flammable"])
        )
        .then(pl.lit("Flammable"))
        .when(
            pl.col("clean_description").str.contains(hazard_patterns["Corrosive"])
            | pl.col("clean_stock_code").str.contains(hazard_patterns["Corrosive"])
        )
        .then(pl.lit("Corrosive"))
        .when(
            pl.col("clean_description").str.contains(hazard_patterns["Toxic"])
            | pl.col("clean_stock_code").str.contains(hazard_patterns["Toxic"])
        )
        .then(pl.lit("Toxic"))
        .when(
            pl.col("clean_description").str.contains(hazard_patterns["Fertilizer"])
            | pl.col("clean_stock_code").str.contains(hazard_patterns["Fertilizer"])
        )
        .then(pl.lit("Chemical: Agricultural"))
        .otherwise(pl.lit("General"))
        .alias("refined_hazard_class")
    ).with_columns(
        pl.when(pl.col("PrincipalCode") == "LONGSAIL")
        .then(pl.lit("Electronics"))
        .when(
            pl.col("PrincipalCode").is_in(
                ["I SCENT", "CIDOLS", "YUNH CHENG", "THE CHEMIE"]
            )
        )
        .then(pl.lit("Chemical"))
        .when(pl.col("refined_hazard_class") != "General")
        .then(pl.lit("Chemical"))
        .when(
            pl.col("PrincipalCode").is_in(["AIC", "YS", "XZ", "DING DON"])
            | pl.col("PrincipalCode").str.starts_with("HDL")
            | pl.col("PrincipalCode").str.starts_with("ORIENTAL")
            | pl.col("PrincipalCode").str.starts_with("TRANS Z")
        )
        .then(pl.lit("Food-Grade"))
        .when(
            pl.col("clean_description").str.contains(category_patterns["Food"])
            | pl.col("clean_stock_code").str.contains(category_patterns["Food"])
        )
        .then(pl.lit("Food-Grade"))
        .when(
            pl.col("clean_description").str.contains(category_patterns["Electronics"])
            | pl.col("clean_stock_code").str.contains(category_patterns["Electronics"])
        )
        .then(pl.lit("Electronics"))
        .when(
            (
                pl.col("clean_description").str.contains(category_patterns["Packaging"])
                | pl.col("clean_stock_code").str.contains(
                    category_patterns["Packaging"]
                )
            )
            & (pl.col("PrincipalCode") != "AGRIPRO")
        )
        .then(pl.lit("Packaging Material"))
        .when(
            pl.col("clean_description").str.contains(
                category_patterns["Crockery_Equipment"]
            )
            | pl.col("clean_stock_code").str.contains(
                category_patterns["Crockery_Equipment"]
            )
        )
        .then(pl.lit("Crockery / Equipment"))
        .when(
            pl.col("clean_description").str.contains(category_patterns["Uniform"])
            | pl.col("clean_stock_code").str.contains(category_patterns["Uniform"])
        )
        .then(pl.lit("Uniform / PPE"))
        .when(
            pl.col("clean_description").str.contains(category_patterns["Chemical"])
            | pl.col("clean_stock_code").str.contains(category_patterns["Chemical"])
        )
        .then(pl.lit("Chemical"))
        .otherwise(pl.lit("General / Other"))
        .alias("refined_category")
    )

    return df


def categorize_cold_room(df: pl.DataFrame) -> pl.DataFrame:
    cold_storage_keywords = r"(frozen|chilled|ice cream|meat|fish|pork|chicken|beef|mutton|shrimp|prawn|seafood)"
    return df.with_columns(
        pl.when(
            pl.col("refined_category").is_in(
                [
                    "Electronics",
                    "Chemical",
                    "Packaging Material",
                    "Uniform / PPE",
                    "Crockery / Equipment",
                ]
            )
        )
        .then(False)
        .when(
            pl.col("PrincipalCode").is_in(["YS", "XZ", "DING DON"])
            | pl.col("PrincipalCode").str.starts_with("HDL")
            | pl.col("PrincipalCode").str.starts_with("ORIENTAL")
            | pl.col("PrincipalCode").str.starts_with("TRANS Z")
            | pl.col("clean_description").str.contains(cold_storage_keywords)
            | pl.col("clean_stock_code").str.contains(cold_storage_keywords)
        )
        .then(True)
        .otherwise(False)
        .alias("is_cold_room")
    )


if __name__ == "__main__":
    from db_utils import get_mssql_connection_uri

    uri_mssql = get_mssql_connection_uri()
    print("Running categorize as standalone...")
    # Fetch sample data and test
    query = """
        SELECT TOP 100 s.*, p."PrincipalCode"
        FROM dbo.admstock s
        LEFT JOIN dbo.admstockprincipal p
            ON s."CompanyCode" = p."CompanyCode"
            AND s."BranchCode" = p."BranchCode"
            AND s."StockCode" = p."StockCode"
    """
    df = pl.read_database_uri(query, uri_mssql)
    df_refined = refine_stock_master(df)
    df_refined = categorize_cold_room(df_refined)
    print(df_refined.select(["StockCode", "refined_category", "is_cold_room"]).head())

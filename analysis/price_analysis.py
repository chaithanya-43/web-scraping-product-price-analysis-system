import logging
logger = logging.getLogger(__name__)
import pandas as pd


EXPECTED_COLUMNS = [
    "product_name",
    "price",
    "currency",
    "website_name",
    "category",
    "rating",
    "availability",
    "product_link",
    "discount",
    "last_updated"
]



def clean_product_data(products, *, return_report=False):
    """Clean product rows; optionally return the drop counts alongside the frame."""

    df = pd.DataFrame(products)

    if df.empty:
        logger.debug("[Cleaning] No products received.")
        report = {"rows_received": 0, "duplicates_removed": 0,
                  "invalid_prices_removed": 0, "valid_rows": 0}
        return (df, report) if return_report else df

    rows_received = len(df)
    logger.debug(f"[Cleaning] Products received: {rows_received}")

    for column in EXPECTED_COLUMNS:
        if column not in df.columns:
            df[column] = None

    # Normalize prices.
    df["price"] = (
        df["price"].astype("string")
        .str.replace(r"[^0-9,.-]", "", regex=True)
        .str.replace(",", "", regex=False)
        .str.strip()
    )

    df["price"] = pd.to_numeric(
        df["price"],
        errors="coerce"
    )

    valid_prices = df["price"].notna() & (df["price"] >= 0)
    logger.debug(f"[Cleaning] Products with valid prices: {valid_prices.sum()}")
    logger.debug(f"[Cleaning] Missing/invalid prices: {(~valid_prices).sum()}")

    df["rating"] = pd.to_numeric(
        df["rating"],
        errors="coerce"
    )
    df.loc[~df["rating"].between(0, 5), "rating"] = None

    df["discount"] = pd.to_numeric(
        df["discount"],
        errors="coerce"
    )

    before_duplicates = len(df)

    df = df.drop_duplicates(
        subset=["product_link", "product_name"]
    )

    logger.debug(
        f"[Cleaning] Duplicates removed: "
        f"{before_duplicates - len(df)}"
    )

    before_prices = len(df)

    df = df.dropna(subset=["price"])
    df = df[df["price"] >= 0]

    logger.debug(
        f"[Cleaning] Products removed by price validation: "
        f"{before_prices - len(df)}"
    )
    logger.debug(f"[Cleaning] Final valid products: {len(df)}")

    df = df.reset_index(drop=True)
    report = {
        "rows_received": rows_received,
        "duplicates_removed": before_duplicates - len(df) - (before_prices - len(df)),
        "invalid_prices_removed": before_prices - len(df),
        "valid_rows": len(df),
    }
    return (df, report) if return_report else df



def calculate_price_statistics(df):
    """
    Calculate basic price statistics.
    """

    if df.empty:
        return {
            "minimum_price": None,
            "maximum_price": None,
            "average_price": None,
            "price_difference": None,
            "median_price": None
        }

    minimum_price = df["price"].min()
    maximum_price = df["price"].max()
    average_price = df["price"].mean()
    price_difference = maximum_price - minimum_price
    median_price = df["price"].median()

    return {
        "minimum_price": minimum_price,
        "maximum_price": maximum_price,
        "average_price": average_price,
        "price_difference": price_difference,
        "median_price": median_price
    }


def get_product_insights(df):
    """
    Find useful product-level insights from the cleaned dataset.
    """

    if df.empty:
        return {
            "highest_rated_product": None,
            "lowest_priced_product": None,
            "most_expensive_product": None
        }

    valid_ratings = df.dropna(
        subset=["rating"]
    )

    highest_rated_product = None

    if not valid_ratings.empty:

        highest_rated_row = valid_ratings.loc[
            valid_ratings["rating"].idxmax()
        ]

        highest_rated_product = {
            "product_name": highest_rated_row["product_name"],
            "rating": highest_rated_row["rating"],
            "price": highest_rated_row["price"],
            "product_link": highest_rated_row.get("product_link")
        }

    lowest_priced_row = df.loc[
        df["price"].idxmin()
    ]

    most_expensive_row = df.loc[
        df["price"].idxmax()
    ]

    return {
        "highest_rated_product": highest_rated_product,
        "lowest_priced_product": {
            "product_name": lowest_priced_row["product_name"],
            "price": lowest_priced_row["price"],
            "product_link": lowest_priced_row.get("product_link")
        },
        "most_expensive_product": {
            "product_name": most_expensive_row["product_name"],
            "price": most_expensive_row["price"],
            "product_link": most_expensive_row.get("product_link")
        }
    }


def save_data(
    df,
    output_path="data/processed/products.csv"
):
    """
    Save cleaned product data to a CSV file.
    """

    df.to_csv(
        output_path,
        index=False
    )

import pandas as pd


def clean_product_data(products):
    """
    Convert scraped product dictionaries into a clean DataFrame.
    """

    df = pd.DataFrame(products)

    # Clean price
    df["price"] = (
        df["price"]
        .str.replace("Â£", "", regex=False)
        .str.replace("£", "", regex=False)
        .str.strip()
    )

    df["price"] = pd.to_numeric(df["price"], errors="coerce")

    # Convert rating to numeric
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")

    # Remove duplicate products
    df = df.drop_duplicates(subset=["product_name"])

    # Remove rows without a valid price
    df = df.dropna(subset=["price"])

    return df.reset_index(drop=True)


def calculate_price_statistics(df):
    """
    Calculate basic price statistics.
    """

    if df.empty:
        return {
            "minimum_price": None,
            "maximum_price": None,
            "average_price": None,
            "price_difference": None
        }

    minimum_price = df["price"].min()
    maximum_price = df["price"].max()
    average_price = df["price"].mean()
    price_difference = maximum_price - minimum_price

    return {
        "minimum_price": minimum_price,
        "maximum_price": maximum_price,
        "average_price": average_price,
        "price_difference": price_difference
    }

def save_data(df, output_path="data/processed/products.csv"):
    """
    Save cleaned product data to a CSV file.
    """

    df.to_csv(output_path, index=False)
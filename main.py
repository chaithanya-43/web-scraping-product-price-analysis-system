import os
import pandas as pd

from scraper.fetcher import fetch_page
from scraper.parser import parse_products
from analysis.price_analysis import (
    clean_product_data,
    calculate_price_statistics,
    save_data
)
from visualization.charts import plot_price_comparison


URL = "https://books.toscrape.com/"


def main():
    print("=" * 60)
    print("       WEB SCRAPING AND PRODUCT PRICE ANALYSIS")
    print("=" * 60)

    try:
        print("\n[1/5] Fetching website...")

        html = fetch_page(URL)

        print(f"      HTML fetched: {len(html)} characters")

        print("\n[2/5] Extracting products...")

        products = parse_products(html)

        if not products:
            print("      No products were found on the webpage.")
            return

        print(f"      Products extracted: {len(products)}")

        os.makedirs("data/raw", exist_ok=True)
        os.makedirs("data/processed", exist_ok=True)

        raw_df = pd.DataFrame(products)

        raw_df.to_csv(
            "data/raw/products_raw.csv",
            index=False
        )

        print("      Raw data saved to data/raw/products_raw.csv")

        print("\n[3/5] Cleaning product data...")

        df = clean_product_data(products)

        if df.empty:
            print("      No valid product data remains after cleaning.")
            return

        print(f"      Products after cleaning: {len(df)}")

        save_data(
            df,
            "data/processed/products.csv"
        )

        print("      Cleaned data saved to data/processed/products.csv")

        print("\n[4/5] Analyzing prices...")

        statistics = calculate_price_statistics(df)

        print("\n      PRICE ANALYSIS")
        print("      " + "-" * 35)
        print(f"      Minimum price : £{statistics['minimum_price']:.2f}")
        print(f"      Maximum price : £{statistics['maximum_price']:.2f}")
        print(f"      Average price : £{statistics['average_price']:.2f}")
        print(f"      Price range   : £{statistics['price_difference']:.2f}")

        print("\n[5/5] Generating visualization...")

        plot_price_comparison(
            df,
            "data/processed/price_comparison.png"
        )

        print("\n" + "=" * 60)
        print("Project execution completed successfully.")
        print("=" * 60)

    except ValueError as error:
        print(f"\nInput error: {error}")

    except RuntimeError as error:
        print(f"\nWebsite error: {error}")

    except Exception as error:
        print(f"\nUnexpected error: {error}")


if __name__ == "__main__":
    main()
import os
import pandas as pd

from scraper.scraper import scrape_products
from analysis.price_analysis import (
    clean_product_data,
    calculate_price_statistics,
    get_product_insights,
    save_data
)
from visualization.charts import (
    plot_price_comparison,
    plot_price_distribution,
    plot_rating_vs_price
)


DEFAULT_URL = "https://books.toscrape.com/"


def main():
    print("=" * 60)
    print("       WEB SCRAPING AND PRODUCT PRICE ANALYSIS")
    print("=" * 60)

    try:
        url = input(
            f"\nEnter website URL [{DEFAULT_URL}]: "
        ).strip()

        if not url:
            url = DEFAULT_URL

        pages_input = input(
            "Enter number of pages [1]: "
        ).strip()

        pages = int(pages_input) if pages_input else 1

        print(f"\n[1/5] Scraping {pages} page(s)...")

        products = scrape_products(
            url,
            pages=pages
        )

        if not products:
            print("      No products were found.")
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

        print("\n[2/5] Cleaning product data...")

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

        print("\n[3/5] Analyzing prices...")

        statistics = calculate_price_statistics(df)
        insights = get_product_insights(df)

        print("\n      PRICE ANALYSIS")
        print("      " + "-" * 35)

        print(
            f"      Minimum price : "
            f"£{statistics['minimum_price']:.2f}"
        )

        print(
            f"      Maximum price : "
            f"£{statistics['maximum_price']:.2f}"
        )

        print(
            f"      Average price : "
            f"£{statistics['average_price']:.2f}"
        )

        print(
            f"      Median price  : "
            f"£{statistics['median_price']:.2f}"
        )

        print(
            f"      Price range   : "
            f"£{statistics['price_difference']:.2f}"
        )

        print("\n      PRODUCT INSIGHTS")
        print("      " + "-" * 35)

        highest_rated = insights["highest_rated_product"]

        if highest_rated:
            print(
                f"      Highest rated : "
                f"{highest_rated['product_name']} "
                f"({highest_rated['rating']:.0f}/5)"
            )

        lowest_priced = insights["lowest_priced_product"]

        print(
            f"      Lowest priced : "
            f"{lowest_priced['product_name']} "
            f"(£{lowest_priced['price']:.2f})"
        )

        most_expensive = insights["most_expensive_product"]

        print(
            f"      Most expensive: "
            f"{most_expensive['product_name']} "
            f"(£{most_expensive['price']:.2f})"
        )

        print("\n[4/5] Generating visualizations...")

        plot_price_comparison(
            df,
            "data/processed/price_comparison.png"
        )

        plot_price_distribution(
            df,
            "data/processed/price_distribution.png"
        )

        plot_rating_vs_price(
            df,
            "data/processed/rating_vs_price.png"
        )

        print("\n[5/5] Finalizing output...")

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
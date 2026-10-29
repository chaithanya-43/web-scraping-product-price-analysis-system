import matplotlib.pyplot as plt
import seaborn as sns


def plot_price_comparison(
    df,
    output_path="data/processed/price_comparison.png",
    max_products=20
):
    """
    Create a readable horizontal bar chart comparing product prices.
    """

    if df.empty:
        return

    chart_df = (
        df.sort_values("price", ascending=False)
        .head(max_products)
        .sort_values("price", ascending=True)
    )

    plt.figure(figsize=(12, 8))

    sns.barplot(
        data=chart_df,
        x="price",
        y="product_name"
    )

    plt.title("Top Product Price Comparison")
    plt.xlabel("Price (GBP)")
    plt.ylabel("Product")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.show()
    plt.close()


def plot_price_distribution(
    df,
    output_path="data/processed/price_distribution.png"
):
    """
    Create a histogram showing the distribution of product prices.
    """

    if df.empty:
        return

    plt.figure(figsize=(10, 6))

    sns.histplot(
        data=df,
        x="price",
        bins=15,
        kde=True
    )

    plt.title("Product Price Distribution")
    plt.xlabel("Price (GBP)")
    plt.ylabel("Number of Products")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.show()
    plt.close()


def plot_rating_vs_price(
    df,
    output_path="data/processed/rating_vs_price.png"
):
    """
    Create a scatter plot showing the relationship
    between product rating and price.
    """

    if df.empty:
        return

    chart_df = df.dropna(subset=["rating", "price"])

    if chart_df.empty:
        return

    plt.figure(figsize=(10, 6))

    sns.scatterplot(
        data=chart_df,
        x="rating",
        y="price",
        s=80
    )

    plt.title("Rating vs Price")
    plt.xlabel("Rating")
    plt.ylabel("Price (GBP)")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.show()
    plt.close()

import matplotlib.pyplot as plt
import seaborn as sns


def plot_price_comparison(df, output_path="data/processed/price_comparison.png"):
    """
    Create a bar chart comparing product prices.
    """

    plt.figure(figsize=(12, 6))

    sns.barplot(
        data=df,
        x="price",
        y="product_name"
    )

    plt.title("Product Price Comparison")
    plt.xlabel("Price (£)")
    plt.ylabel("Product")

    plt.tight_layout()

    plt.savefig(output_path, dpi=150)
    plt.show()
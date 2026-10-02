from analysis.price_analysis import clean_product_data

products = [
    {
        "product_name": "Book A",
        "price": "£20.00",
        "rating": 4,
        "availability": "In stock",
        "category": "Books",
        "product_link": "https://example.com/book-a"
    },
    {
        "product_name": "Book A",
        "price": "£20.00",
        "rating": 4,
        "availability": "In stock",
        "category": "Books",
        "product_link": "https://example.com/book-a"
    },
    {
        "product_name": "Book B",
        "price": "£30.00",
        "rating": 5,
        "availability": "In stock",
        "category": "Books",
        "product_link": "https://example.com/book-b"
    }
]

df = clean_product_data(products)

print("Products after cleaning:", len(df))
print(df[["product_name", "price"]])

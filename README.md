**# Web Scraping and Product Price Analysis System**



**## Project Overview**



**The Web Scraping and Product Price Analysis System automatically collects product information from an online source, cleans and processes the collected data, performs price analysis, and generates a visualization of product prices.**



**## Objectives**



**- Scrape product information from a website**

**- Extract product name, price, rating, availability, category, and product link**

**- Clean scraped data**

**- Remove duplicate products**

**- Handle missing and invalid values**

**- Calculate minimum, maximum, average, and price-range values**

**- Generate a product price comparison chart**

**- Save raw and processed data as CSV files**



**## Technology Stack**



**- Python 3.x**

**- Requests**

**- BeautifulSoup**

**- Pandas**

**- NumPy**

**- Matplotlib**

**- Seaborn**

**- Pytest**



**## Architecture**



**```text**

**Website**

&#x20;  **|**

&#x20;  **v**

**Requests**

&#x20;  **|**

&#x20;  **v**

**BeautifulSoup**

&#x20;  **|**

&#x20;  **v**

**Data Extraction**

&#x20;  **|**

&#x20;  **v**

**Pandas Data Cleaning**

&#x20;  **|**

&#x20;  **+--> Remove duplicates**

&#x20;  **+--> Handle missing values**

&#x20;  **+--> Convert prices to numeric values**

&#x20;  **|**

&#x20;  **v**

**Price Analysis**

&#x20;  **|**

&#x20;  **+--> Minimum price**

&#x20;  **+--> Maximum price**

&#x20;  **+--> Average price**

&#x20;  **+--> Price difference**

&#x20;  **|**

&#x20;  **v**

**Visualization**

&#x20;  **|**

&#x20;  **v**

**CSV + Price Comparison Chart**


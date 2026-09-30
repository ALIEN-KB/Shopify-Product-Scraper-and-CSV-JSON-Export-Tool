## Project Title

Shopify Product Scraper and CSV/JSON Export Tool

## Project Description

I developed a Python-based web scraping tool that extracts publicly available product data from Shopify stores and exports it into clean, structured CSV and JSON files.

The scraper uses Shopify’s public product catalog endpoint and automatically handles pagination, allowing it to collect large product catalogs efficiently. It also includes configurable request delays, retry handling, collection filtering, and error management.

The exported data can include:

- Product names and descriptions
- Product and variant IDs
- Prices and comparison prices
- SKUs
- Vendors and product types
- Tags and availability
- Product and image URLs
- Variant options
- Published and updated dates

The CSV output creates one row per product variant, making the data easy to use in Excel, inventory systems, analytics tools, or product migration workflows.

## Key Features

- Automatic Shopify catalog pagination
- CSV and JSON exports
- Product-variant data extraction
- Collection-specific scraping
- Configurable request delay and timeout
- Automatic retries for temporary request failures
- Duplicate-product prevention
- No external Python dependencies
- Unit-tested pagination and data transformation
- Clear command-line interface

## Technologies Used

Python, HTTP requests, JSON processing, CSV generation, Shopify storefront endpoints, command-line interface development, and unit testing.

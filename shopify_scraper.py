#!/usr/bin/env python3
"""Export products from a public Shopify storefront to JSON and/or CSV.

This uses Shopify's storefront ``products.json`` endpoint. It does not bypass
authentication, CAPTCHAs, or other access controls.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


USER_AGENT = "ShopifyCatalogExporter/1.0 (+public-products-export)"
CSV_FIELDS = [
    "product_id",
    "title",
    "handle",
    "product_type",
    "vendor",
    "product_url",
    "published_at",
    "created_at",
    "updated_at",
    "tags",
    "variant_id",
    "variant_title",
    "sku",
    "price",
    "compare_at_price",
    "available",
    "option1",
    "option2",
    "option3",
    "image_url",
]


class ScrapeError(RuntimeError):
    """Raised when a storefront cannot be exported."""


def normalize_store_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    if not parsed.hostname:
        raise ScrapeError(f"Invalid store URL: {value!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


def endpoint_for(store_url: str, collection: str | None) -> str:
    if collection:
        safe_handle = collection.strip().strip("/")
        if "/" in safe_handle or not safe_handle:
            raise ScrapeError("Collection must be a Shopify collection handle, e.g. shoes")
        return f"{store_url}/collections/{safe_handle}/products.json"
    return f"{store_url}/products.json"


def fetch_json(url: str, timeout: float, retries: int) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                body = response.read()
            if "json" not in content_type.lower() and not body.lstrip().startswith(b"{"):
                raise ScrapeError(
                    "The store did not return JSON. Its public product endpoint may be disabled."
                )
            payload = json.loads(body)
            if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
                raise ScrapeError("Unexpected response: missing a products list")
            return payload
        except HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < retries:
                retry_after = exc.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                time.sleep(wait + random.uniform(0, 0.25))
                continue
            if exc.code in {401, 403, 404}:
                raise ScrapeError(
                    f"Store returned HTTP {exc.code}; its public product endpoint may be unavailable."
                ) from exc
            raise ScrapeError(f"Store returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            if attempt < retries:
                time.sleep(2**attempt + random.uniform(0, 0.25))
                continue
            raise ScrapeError(f"Network error: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ScrapeError("Store returned invalid JSON") from exc
    raise AssertionError("retry loop exited unexpectedly")


def scrape_products(
    store_url: str,
    collection: str | None = None,
    limit: int = 250,
    delay: float = 0.5,
    timeout: float = 30,
    retries: int = 3,
    max_products: int | None = None,
) -> list[dict[str, Any]]:
    endpoint = endpoint_for(store_url, collection)
    products: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    page = 1

    while True:
        separator = "&" if "?" in endpoint else "?"
        url = f"{endpoint}{separator}limit={limit}&page={page}"
        payload = fetch_json(url, timeout=timeout, retries=retries)
        batch = payload["products"]
        if not batch:
            break

        new_products = []
        for product in batch:
            product_id = str(product.get("id", ""))
            if product_id and product_id not in seen_ids:
                seen_ids.add(product_id)
                new_products.append(product)
        if not new_products:
            break

        products.extend(new_products)
        print(f"Fetched page {page}: {len(new_products)} products ({len(products)} total)", file=sys.stderr)

        if max_products is not None and len(products) >= max_products:
            return products[:max_products]
        if len(batch) < limit:
            break
        page += 1
        if delay:
            time.sleep(delay)

    return products


def product_rows(products: Iterable[dict[str, Any]], store_url: str) -> Iterable[dict[str, Any]]:
    for product in products:
        images = product.get("images") or []
        fallback_image = images[0].get("src", "") if images else ""
        variants = product.get("variants") or [{}]
        for variant in variants:
            image = variant.get("featured_image") or {}
            yield {
                "product_id": product.get("id", ""),
                "title": product.get("title", ""),
                "handle": product.get("handle", ""),
                "product_type": product.get("product_type", ""),
                "vendor": product.get("vendor", ""),
                "product_url": f"{store_url}/products/{product.get('handle', '')}",
                "published_at": product.get("published_at", ""),
                "created_at": product.get("created_at", ""),
                "updated_at": product.get("updated_at", ""),
                "tags": ", ".join(product.get("tags") or []),
                "variant_id": variant.get("id", ""),
                "variant_title": variant.get("title", ""),
                "sku": variant.get("sku", ""),
                "price": variant.get("price", ""),
                "compare_at_price": variant.get("compare_at_price", ""),
                "available": variant.get("available", ""),
                "option1": variant.get("option1", ""),
                "option2": variant.get("option2", ""),
                "option3": variant.get("option3", ""),
                "image_url": image.get("src") or fallback_image,
            }


def write_json(path: Path, products: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(products, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, products: list[dict[str, Any]], store_url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(product_rows(products, store_url))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store", help="Store domain or URL, e.g. example.myshopify.com")
    parser.add_argument("--format", choices=("json", "csv", "both"), default="both")
    parser.add_argument("--output", default="products", help="Output path without extension")
    parser.add_argument("--collection", help="Only export this collection handle")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between pages (default: 0.5)")
    parser.add_argument("--timeout", type=float, default=30, help="Request timeout in seconds")
    parser.add_argument("--retries", type=int, default=3, help="Retries for transient errors")
    parser.add_argument("--max-products", type=int, help="Stop after this many products")
    args = parser.parse_args(argv)
    if args.delay < 0 or args.timeout <= 0 or args.retries < 0:
        parser.error("delay/retries cannot be negative and timeout must be positive")
    if args.max_products is not None and args.max_products <= 0:
        parser.error("--max-products must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        store_url = normalize_store_url(args.store)
        products = scrape_products(
            store_url,
            collection=args.collection,
            delay=args.delay,
            timeout=args.timeout,
            retries=args.retries,
            max_products=args.max_products,
        )
        base = Path(args.output)
        if args.format in {"json", "both"}:
            write_json(base.with_suffix(".json"), products)
        if args.format in {"csv", "both"}:
            write_csv(base.with_suffix(".csv"), products, store_url)
        print(f"Done: exported {len(products)} products.", file=sys.stderr)
        return 0
    except (ScrapeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

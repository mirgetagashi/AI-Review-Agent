"""Inventory report for a small shop - written for the data assignment."""

import csv
import statistics


class Product:
    def __init__(self, sku, name, price, quantity):
        self.sku = sku
        self.name = name
        self.price = price
        self.quantity = quantity

    @property
    def stock_value(self):
        return round(self.price * self.quantity, 2)

    def needs_restock(self, threshold=5):
        return self.quantity < threshold


def load_products(path):
    products = []
    with open(path, newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            products.append(Product(record["sku"], record["name"],
                                    float(record["price"]), int(record["quantity"])))
    return products


def price_summary(products):
    prices = [product.price for product in products]
    if not prices:
        return {"count": 0}
    return {
        "count": len(prices),
        "mean": round(statistics.mean(prices), 2),
        "median": statistics.median(prices),
        "stdev": round(statistics.pstdev(prices), 2),
        "cheapest": min(products, key=lambda product: product.price).name,
        "priciest": max(products, key=lambda product: product.price).name,
    }


def restock_list(products, threshold=5):
    low = [product for product in products if product.needs_restock(threshold)]
    return sorted(low, key=lambda product: (product.quantity, product.name))


def group_by_initial(products):
    groups = {}
    for product in products:
        key = product.name[:1].upper() or "?"
        groups.setdefault(key, []).append(product.sku)
    return {key: sorted(skus) for key, skus in sorted(groups.items())}


def format_report(products, threshold=5):
    summary = price_summary(products)
    lines = ["Inventory report", "================"]
    lines.append("products: {0}".format(summary["count"]))
    if summary["count"]:
        lines.append("mean price: {0}".format(summary["mean"]))
        lines.append("median price: {0}".format(summary["median"]))
        lines.append("cheapest: {0}, priciest: {1}".format(summary["cheapest"], summary["priciest"]))
    total = sum(product.stock_value for product in products)
    lines.append("total stock value: {0:.2f}".format(total))
    lines.append("")
    lines.append("restock:")
    for product in restock_list(products, threshold):
        lines.append("  {0} ({1} left)".format(product.name, product.quantity))
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    print(format_report(load_products(sys.argv[1])))

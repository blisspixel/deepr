"""Financial ratio calculations."""

from __future__ import annotations

from typing import Any


def calculate_financial_ratios(
    data: dict[str, Any],
    ratios: list[str] | None = None,
) -> dict[str, Any]:
    """Calculate financial ratios from raw data.

    Args:
        data: Financial data with keys like revenue, net_income, total_assets, etc.
        ratios: Which ratios to calculate (defaults to all applicable)

    Returns:
        Dictionary with calculated ratios and metadata
    """
    all_ratios = ratios or [
        "pe",
        "pb",
        "de",
        "roe",
        "roa",
        "gross_margin",
        "net_margin",
        "current_ratio",
        "quick_ratio",
    ]

    results: dict[str, Any] = {}
    errors: list[str] = []

    for ratio in all_ratios:
        try:
            value = _calculate_single(ratio, data)
            if value is not None:
                results[ratio] = round(value, 4)
            else:
                errors.append(f"{ratio}: insufficient data")
        except (ZeroDivisionError, TypeError, ValueError) as e:
            errors.append(f"{ratio}: {e}")

    return {
        "ratios": results,
        "errors": errors if errors else None,
        "data_keys_provided": list(data.keys()),
        "ratios_calculated": len(results),
    }


def _calculate_single(ratio: str, data: dict[str, Any]) -> float | None:
    """Calculate a single ratio."""

    def get(*keys: str) -> float | None:
        for key in keys:
            val = data.get(key)
            if val is not None:
                return float(val)
        return None

    if ratio == "pe":
        price = get("share_price", "price")
        eps = get("eps", "earnings_per_share")
        if price is not None and eps is not None and eps != 0:
            return price / eps

    elif ratio == "pb":
        price = get("share_price", "price")
        bvps = get("book_value_per_share", "bvps")
        if price is not None and bvps is not None and bvps != 0:
            return price / bvps

    elif ratio == "de":
        debt = get("total_debt", "total_liabilities")
        equity = get("equity", "total_equity", "shareholders_equity")
        if debt is not None and equity is not None and equity != 0:
            return debt / equity

    elif ratio == "roe":
        net_income = get("net_income")
        equity = get("equity", "total_equity", "shareholders_equity")
        if net_income is not None and equity is not None and equity != 0:
            return net_income / equity

    elif ratio == "roa":
        net_income = get("net_income")
        assets = get("total_assets")
        if net_income is not None and assets is not None and assets != 0:
            return net_income / assets

    elif ratio == "gross_margin":
        revenue = get("revenue")
        cogs = get("cogs", "cost_of_goods_sold")
        if revenue is not None and cogs is not None and revenue != 0:
            return (revenue - cogs) / revenue

    elif ratio == "net_margin":
        net_income = get("net_income")
        revenue = get("revenue")
        if net_income is not None and revenue is not None and revenue != 0:
            return net_income / revenue

    elif ratio == "current_ratio":
        current_assets = get("current_assets")
        current_liabilities = get("current_liabilities")
        if current_assets is not None and current_liabilities is not None and current_liabilities != 0:
            return current_assets / current_liabilities

    elif ratio == "quick_ratio":
        current_assets = get("current_assets")
        inventory = get("inventory")
        current_liabilities = get("current_liabilities")
        if current_assets is not None and current_liabilities is not None and current_liabilities != 0:
            inv = inventory or 0
            return (current_assets - inv) / current_liabilities

    return None

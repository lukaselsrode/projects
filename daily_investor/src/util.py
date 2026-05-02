"""
util.py — Configuration, shared constants, and I/O helpers.

Single source of truth for:
  - All YAML-driven config values
  - DATA_DIRECTORY path
  - METRIC_KEYS (canonical schema for agg_data rows)
  - safe_float
  - CSV read/write helpers
  - Finviz valuation updater
"""

import csv
import datetime
import logging
import os
import random
import re

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIRECTORY = os.path.join(ROOT_DIR, "data")
INVESTMENTS_FILE = os.path.join(ROOT_DIR, "investments.yaml")

os.makedirs(DATA_DIRECTORY, exist_ok=True)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _load_cfg() -> dict:
    with open(INVESTMENTS_FILE, "r") as f:
        return yaml.safe_load(f)


_cfg = _load_cfg()
_app = _cfg.get("config", {})
_inv = {k: v for k, v in _cfg.items() if k != "config"}

# ---------------------------------------------------------------------------
# Public config constants
# ---------------------------------------------------------------------------

IGNORE_NEGATIVE_PE:   bool  = _app.get("ignore_negative_pe", False)
IGNORE_NEGATIVE_PB:   bool  = _app.get("ignore_negative_pb", False)
DIVIDEND_THRESHOLD:   float = float(_app.get("dividend_threshold", 2.5))
METRIC_THRESHOLD:     float = float(_app.get("metric_threshold", 4))
SELLOFF_THRESHOLD:    float = float(_app.get("selloff_threshold", 30))
WEEKLY_INVESTMENT:    float = float(_app.get("weekly_investment", 400))
INDEX_PCT:            float = float(_app.get("index_pct", 0.85))
AUTO_APPROVE:         bool  = _app.get("auto_approve", False)
USE_SENTIMENT_ANALYSIS: bool = _app.get("use_sentiment_analysis", False)
CONFIDENCE_THRESHOLD: float = float(_app.get("confidence_threshold", 70))
ETFS:                 list  = _app.get("etfs", ["SPY", "VOO", "VTI", "QQQ", "SCHD"])

# ---------------------------------------------------------------------------
# Canonical agg_data schema — single definition used by all modules
# ---------------------------------------------------------------------------

METRIC_KEYS: list[str] = [
    "industry",
    "sector",
    "volume",
    "pe_ratio",
    "pb_ratio",
    "dividend_yield",
    "pe_comp",
    "pb_comp",
    "value_score",
    "income_score",
    "quality_score",
    "yield_trap_flag",
    "value_metric",
    "buy_to_sell_ratio",
]

AGG_DATA_COLUMNS: list[str] = ["symbol"] + METRIC_KEYS

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def safe_float(value, default: Optional[float] = None) -> Optional[float]:
    """Convert value to float, returning default on failure or None/NaN input."""
    try:
        if value is None or value == "" or str(value).lower() == "nan":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# CSV / DataFrame I/O
# ---------------------------------------------------------------------------

def _dated_filename(dataset: str) -> str:
    date_str = datetime.datetime.now().strftime("%Y_%m_%d")
    return os.path.join(DATA_DIRECTORY, f"{dataset}_{date_str}.csv")


def store_data_as_csv(
    dataset: str,
    schema: list[str],
    data: list[list] | pd.DataFrame,
    add_timestamp: bool = True,
) -> None:
    filename = _dated_filename(dataset) if add_timestamp else os.path.join(DATA_DIRECTORY, f"{dataset}.csv")

    if isinstance(data, pd.DataFrame):
        data.to_csv(filename, index=False)
        logger.info(f"Stored {dataset} → {filename}")
        return

    if not data:
        logger.warning(f"store_data_as_csv called with empty data for {dataset}")
        return

    row_len = len(data[0])
    if len(schema) != row_len:
        raise ValueError(f"Schema length {len(schema)} != data row length {row_len}")
    if not all(len(r) == row_len for r in data):
        raise ValueError("Mismatched row lengths in data")

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(schema)
        writer.writerows(data)

    logger.info(f"Stored {dataset} → {filename}")


def read_data_as_pd(dataset: str) -> pd.DataFrame | None:
    """Return the first matching CSV for dataset, or None if not found."""
    try:
        files = sorted(os.listdir(DATA_DIRECTORY))
    except FileNotFoundError:
        return None

    matches = [f for f in files if dataset in f and f.endswith(".csv")]
    if not matches:
        logger.debug(f"No CSV found for dataset '{dataset}' in {DATA_DIRECTORY}")
        return None

    path = os.path.join(DATA_DIRECTORY, matches[0])
    logger.debug(f"Using {matches[0]} as {dataset} data")
    print(f"Using {matches[0]} as {dataset} data")
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Sector/industry ratio lookup
# ---------------------------------------------------------------------------

def _split_to_set(s: str) -> set[str]:
    return set(re.split(r"[\/ :&]+", s))


def get_investment_ratios(sector: str, industry: str | None = None) -> list[float]:
    """Return [PE_threshold, PB_threshold] for the given sector/industry."""
    DEFAULT = [15.0, 2.5]

    if not sector or sector not in _inv:
        return DEFAULT

    sector_cfg = _inv[sector]
    default = sector_cfg.get("default", DEFAULT)

    def _coerce(ratios: list) -> list[float]:
        return [
            ratios[0] if ratios and len(ratios) > 0 and ratios[0] is not None else default[0],
            ratios[1] if ratios and len(ratios) > 1 and ratios[1] is not None else default[1],
        ]

    if not industry:
        return default

    # Exact match
    if industry in sector_cfg and sector_cfg[industry]:
        return _coerce(sector_cfg[industry])

    # Fuzzy match
    try:
        query = _split_to_set(industry)
        best, best_diff = None, float("inf")
        for key in sector_cfg:
            if key == "default":
                continue
            diff = len(query.difference(_split_to_set(key)))
            if diff == 0 and len(_split_to_set(key)) == len(query):
                return _coerce(sector_cfg[key])
            if diff < best_diff:
                best_diff, best = diff, key
        if best and best_diff < 3:
            return _coerce(sector_cfg[best])
    except Exception as e:
        logger.warning(f"Fuzzy match error for industry '{industry}': {e}")

    return default


# ---------------------------------------------------------------------------
# Finviz valuation updater
# ---------------------------------------------------------------------------

_FINVIZ_HEADERS = {"User-Agent": "Mozilla/5.0"}

_SECTOR_MAP = {
    "Materials": "Basic Materials",
    "Consumer Discretionary": "Consumer Cyclical",
    "Consumer Staples": "Consumer Defensive",
    "Financials": "Financial",
    "Health Care": "Healthcare",
    "Information Technology": "Technology",
    "Real Estate": "Real Estate",
    "Utilities": "Utilities",
    "Energy": "Energy",
    "Industrials": "Industrials",
    "Communication Services": "Communication Services",
    "Consumer Services": "Consumer Cyclical",
    "Technology Services": "Technology",
    "Health Technology": "Healthcare",
    "Communications": "Communication Services",
    "Electronic Technology": "Technology",
    "Retail Trade": "Consumer Cyclical",
    "Consumer Durables": "Consumer Cyclical",
    "Transportation": "Industrials",
}

_INDUSTRY_MAP = {
    "Insurance - Life": "Life Insurance",
    "Insurance - Property & Casualty": "Property & Casualty Insurance",
    "Insurance - Specialty": "Specialty Insurance",
    "Insurance - Diversified": "Diversified Insurance",
    "REIT - Mortgage": "Mortgage REITs",
    "REIT - Diversified": "Diversified REITs",
    "REIT - Retail": "Retail REITs",
    "REIT - Residential": "Residential REITs",
    "REIT - Industrial": "Industrial REITs",
    "REIT - Office": "Office REITs",
    "REIT - Hotel & Motel": "Hotel & Motel REITs",
    "REIT - Healthcare Facilities": "Health Care REITs",
    "REIT - Specialty": "Specialty REITs",
    "Oil & Gas E&P": "Oil & Gas Exploration & Production",
    "Beverages - Brewers": "Brewers",
    "Beverages - Wineries & Distilleries": "Distillers & Vintners",
    "Beverages - Non-Alcoholic": "Non-Alcoholic Beverages",
    "Telecom Services": "Telecommunication Services",
    "Internet Content & Information": "Interactive Media & Services",
    "Software - Application": "Application Software",
    "Software - Infrastructure": "Systems Software",
}


def _fetch_finviz_table(url: str) -> dict[str, dict[str, Optional[float]]]:
    resp = requests.get(url, headers=_FINVIZ_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("div", class_="content").find(
        "table",
        class_="styled-table-new is-medium is-rounded is-tabular-nums w-full groups_table",
    )
    if not table:
        raise ValueError(f"Could not find data table at {url}")

    result = {}
    for row in table.find_all("tr")[1:]:
        link = row.find("a")
        if not link:
            continue
        cells = row.find_all("td")
        pe_text = cells[3].get_text() if len(cells) > 3 else "-"
        pb_text = cells[7].get_text() if len(cells) > 7 else "-"
        result[link.get_text()] = {
            "PE": float(pe_text) if pe_text != "-" else None,
            "PB": float(pb_text) if pb_text != "-" else None,
        }
    return result


def update_industry_valuations(verbose: bool = True) -> None:
    SECTOR_URL = "https://finviz.com/groups.ashx?g=sector&v=120&o=pe"
    INDUSTRY_URL = "https://finviz.com/groups.ashx?g=industry&v=120&o=pe"

    try:
        sector_data = _fetch_finviz_table(SECTOR_URL)
        industry_data = _fetch_finviz_table(INDUSTRY_URL)
    except Exception as e:
        logger.error(f"Failed to fetch Finviz data: {e}")
        raise

    cfg = _load_cfg()
    changes: list[dict] = []

    for sector_yaml, industries in cfg.items():
        if sector_yaml == "config" or not isinstance(industries, dict):
            continue

        finviz_sector = _SECTOR_MAP.get(sector_yaml)
        if finviz_sector and finviz_sector in sector_data:
            new_pe = sector_data[finviz_sector]["PE"]
            new_pb = sector_data[finviz_sector]["PB"]
            default = industries.get("default")
            if isinstance(default, list) and len(default) >= 2:
                old_pe, old_pb = default[0], default[1]
                updated_pe = new_pe if new_pe is not None else old_pe
                updated_pb = new_pb if new_pb is not None else old_pb
                if updated_pe != old_pe or updated_pb != old_pb:
                    industries["default"] = [updated_pe, updated_pb]
                    changes.append({
                        "type": "sector", "name": sector_yaml,
                        "old": f"PE={old_pe}, PB={old_pb}",
                        "new": f"PE={updated_pe}, PB={updated_pb}",
                    })

        for ind_yaml, metrics in industries.items():
            if ind_yaml == "default" or not isinstance(metrics, list) or len(metrics) < 2:
                continue
            finviz_ind = _INDUSTRY_MAP.get(ind_yaml, ind_yaml)
            if finviz_ind not in industry_data:
                continue
            new_pe = industry_data[finviz_ind]["PE"]
            new_pb = industry_data[finviz_ind]["PB"]
            old_pe, old_pb = metrics[0], metrics[1]
            changed = False
            if new_pe is not None and new_pe != old_pe:
                metrics[0] = new_pe
                changed = True
            if new_pb is not None and new_pb != old_pb:
                metrics[1] = new_pb
                changed = True
            if changed:
                changes.append({
                    "type": "industry", "sector": sector_yaml, "name": ind_yaml,
                    "old": f"PE={old_pe}, PB={old_pb}",
                    "new": f"PE={metrics[0]}, PB={metrics[1]}",
                })

    if changes:
        with open(INVESTMENTS_FILE, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
        if verbose:
            logger.info(f"Updated {len(changes)} valuations in investments.yaml")
            for c in changes:
                loc = c["name"] if c["type"] == "sector" else f"{c['sector']} / {c['name']}"
                logger.info(f"  {c['type'].upper()} {loc}: {c['old']} → {c['new']}")
    else:
        if verbose:
            logger.info("No valuation changes detected")
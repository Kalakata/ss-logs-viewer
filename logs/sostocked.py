import json
import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger(__name__)
from django.conf import settings

API_URL = "https://api.sostocked.com/order-shipment-logs/logs"
PER_PAGE = 100
DELAY_BETWEEN_PAGES = 0.3
DELAY_BETWEEN_ASINS = 0.5
MANUAL_INV_TYPE = 14000  # Manual inventory change

COLUMNS = [
    {"id": "created_at", "show": 1, "text": "Date Created"},
    {"id": "id", "show": 1, "text": "ID"},
    {"id": "order", "show": 1, "text": "Order Number"},
    {"id": "in_out", "show": 1, "text": "In/Out"},
    {"id": "inventory", "show": 1, "text": "Inventory"},
    {"id": "user", "show": 1, "text": "User Name"},
    {"id": "log", "show": 1, "text": "Description"},
    {"id": "vendor", "show": 1, "text": "Vendor Name"},
    {"id": "product", "show": 1, "text": "Product Name"},
    {"id": "shipment", "show": 1, "text": "Shipment ID"},
    {"id": "area_asins", "show": 1, "text": "ASIN"},
    {"id": "area_skus", "show": 1, "text": "SKU"},
    {"id": "area_fn_skus", "show": 1, "text": "FN SKU"},
]

TYPE_LABELS = {
    10200: "System shipped",
    10500: "Status → arrived",
    11000: "Shipment canceled",
    13000: "Removed from shipment",
    13100: "Added to shipment",
    13200: "Reduced sent qty",
    13300: "Increased arrived qty",
    14000: "Manual inventory change",
    15000: "Work order combine",
    19100: "Vendor update revert",
    20000: "System: units arrived",
    21000: "Combine product created",
    30100: "Units arrived changed",
    30200: "Units ordered changed",
    40000: "Amazon: units arrived",
    40100: "Amazon: units missing",
    40300: "Amazon: units ordered",
    55300: "Shipment → draft",
    60300: "Reconciliation",
    75000: "Product config",
    75100: "Product config",
    76000: "Product config",
    76100: "Product config",
    77000: "Bundle config",
    80000: "Shipped from warehouse",
}


def _load_credentials():
    # Prefer env vars (production), fall back to files (local dev)
    bearer_token = settings.SS_BEARER_TOKEN
    if bearer_token:
        cfg = {
            "client_id": settings.SS_CLIENT_ID,
            "client_secret": settings.SS_CLIENT_SECRET,
            "account_id": settings.SS_ACCOUNT_ID,
        }
        return bearer_token, cfg

    ss_dir = settings.SS_LOGS_DIR
    with open(os.path.join(ss_dir, "token.txt"), "r") as f:
        bearer_token = f.read().strip()
    with open(os.path.join(ss_dir, "config.json"), "r") as f:
        cfg = json.load(f)
    return bearer_token, cfg


def _build_params(page, asin, cfg):
    params = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "account_id": cfg["account_id"],
        "page": page,
        "per_page": PER_PAGE,
        "order_by": "",
        "order_direction": "DESC",
        "term": "",
        "group_by": "",
        "apply_custom_params": 1,
    }
    for i, col in enumerate(COLUMNS):
        params[f"columns[{i}][id]"] = col["id"]
        params[f"columns[{i}][show]"] = col["show"]
        params[f"columns[{i}][text]"] = col["text"]

    params["filters[0][x]"] = "AND"
    params["filters[0][c]"] = "product_asin"
    params["filters[0][o]"] = "EQUAL"
    params["filters[0][v]"] = asin
    return params


PERIOD_PER_PAGE = 1000  # Larger page size for period queries (API supports it)


def _build_params_by_period(page, days, cfg):
    """Build API params that filter by created_at within N days (no ASIN filter)."""
    params = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "account_id": cfg["account_id"],
        "page": page,
        "per_page": PERIOD_PER_PAGE,
        "order_by": "",
        "order_direction": "DESC",
        "term": "",
        "group_by": "",
        "apply_custom_params": 1,
    }
    for i, col in enumerate(COLUMNS):
        params[f"columns[{i}][id]"] = col["id"]
        params[f"columns[{i}][show]"] = col["show"]
        params[f"columns[{i}][text]"] = col["text"]

    params["filters[0][x]"] = "AND"
    params["filters[0][c]"] = "created_at"
    params["filters[0][o]"] = "WITHINP"
    params["filters[0][v]"] = str(days)
    return params


def _format_field(record, field):
    value = record.get(field)
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    if value is None:
        return ""
    return value


def _fetch_asin_logs(asin, bearer_token, cfg, max_pages=0):
    """Fetch log pages for a single ASIN. max_pages=0 means all."""
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    page = 1
    total_pages = None
    logs = []

    while True:
        try:
            resp = requests.get(
                API_URL,
                headers=headers,
                params=_build_params(page, asin, cfg),
                timeout=60,
            )
        except Exception:
            break

        if not resp.ok:
            break

        try:
            data = resp.json()
        except json.JSONDecodeError:
            break

        if data.get("code") != 200:
            break

        if total_pages is None:
            total_pages = data.get("total_pages", 0)

        page_logs = data.get("logs", [])
        if not page_logs:
            break

        for record in page_logs:
            p = record.get("params") or {}
            type_id = record.get("type_id", 0)
            logs.append({
                "filter_asin": asin,
                "id": record.get("id"),
                "created_at": record.get("created_at", ""),
                "order_number": record.get("order_number", ""),
                "param_diff": record.get("param_diff", 0),
                "real_diff": record.get("real_diff", 0),
                "old_qty": p.get("old_quantity"),
                "new_qty": p.get("new_quantity"),
                "user_name": record.get("user_name", ""),
                "description": record.get("description", ""),
                "vendor_name": record.get("vendor_name", ""),
                "product_name": record.get("product_name", ""),
                "order_shipment_id": record.get("order_shipment_id", ""),
                "type_id": type_id,
                "type_label": TYPE_LABELS.get(type_id, str(type_id)),
                "area_asins": _format_field(record, "area_asins"),
                "area_skus": _format_field(record, "area_skus"),
                "area_fn_skus": _format_field(record, "area_fn_skus"),
                # Movement detection fields
                "movement_group": None,  # filled in by _detect_movements
            })

        if page >= total_pages:
            break
        if max_pages and page >= max_pages:
            break

        page += 1
        if DELAY_BETWEEN_PAGES > 0:
            time.sleep(DELAY_BETWEEN_PAGES)

    return logs


def _parse_period_page(page_logs):
    """Parse raw API log records into our internal format."""
    logs = []
    for record in page_logs:
        p = record.get("params") or {}
        type_id = record.get("type_id", 0)
        # area_asins is a list of dicts like:
        #   {"area_type":1, "area_id":5, "area_name":"UK", "values":["B06Y487SQC"]}
        area_asins = record.get("area_asins") or []
        filter_asin = ""
        area_name = ""
        if isinstance(area_asins, list) and area_asins:
            first = area_asins[0]
            if isinstance(first, dict):
                vals = first.get("values") or []
                filter_asin = vals[0] if vals else ""
                area_name = first.get("area_name", "")
            else:
                filter_asin = str(first)
        if not filter_asin:
            filter_asin = _format_field(record, "area_asins")
        logs.append({
            "filter_asin": filter_asin,
            "area_name": area_name,
            "id": record.get("id"),
            "created_at": record.get("created_at", ""),
            "order_number": record.get("order_number", ""),
            "param_diff": record.get("param_diff", 0),
            "real_diff": record.get("real_diff", 0),
            "old_qty": p.get("old_quantity"),
            "new_qty": p.get("new_quantity"),
            "user_name": record.get("user_name", ""),
            "description": record.get("description", ""),
            "vendor_name": record.get("vendor_name", ""),
            "product_name": record.get("product_name", ""),
            "order_shipment_id": record.get("order_shipment_id", ""),
            "type_id": type_id,
            "type_label": TYPE_LABELS.get(type_id, str(type_id)),
            "area_asins": _format_field(record, "area_asins"),
            "area_skus": _format_field(record, "area_skus"),
            "area_fn_skus": _format_field(record, "area_fn_skus"),
            "movement_group": None,
        })
    return logs


def _fetch_period_page(page_num, days, bearer_token, cfg):
    """Fetch a single page of period logs. Returns parsed log list."""
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(
            API_URL, headers=headers,
            params=_build_params_by_period(page_num, days, cfg),
            timeout=60,
        )
        if not resp.ok:
            return []
        data = resp.json()
        if data.get("code") != 200:
            return []
        return _parse_period_page(data.get("logs", []))
    except Exception:
        return []


def _fetch_all_logs(days, bearer_token, cfg, max_pages=0):
    """Fetch log pages for a time period using parallel requests."""
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # First request: get page 1 and discover total_pages
    try:
        resp = requests.get(
            API_URL, headers=headers,
            params=_build_params_by_period(1, days, cfg),
            timeout=60,
        )
        if not resp.ok:
            return []
        data = resp.json()
        if data.get("code") != 200:
            return []
    except Exception:
        return []

    total_pages = data.get("total_pages", 0)
    total_records = data.get("total", 0)
    page1_count = len(data.get("logs", []))
    logger.info("Period fetch: %d days, total_pages=%d, total_records=%d, page1_count=%d, per_page=%d",
                days, total_pages, total_records, page1_count, PERIOD_PER_PAGE)
    logs = _parse_period_page(data.get("logs", []))

    if total_pages <= 1:
        return logs

    # Determine how many more pages to fetch
    pages_to_fetch = min(total_pages, max_pages) if max_pages else total_pages
    remaining_pages = list(range(2, pages_to_fetch + 1))
    logger.info("Fetching %d more pages (total_pages=%d, max_pages=%d)", len(remaining_pages), total_pages, max_pages)

    # Fetch remaining pages in parallel
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {
            pool.submit(_fetch_period_page, p, days, bearer_token, cfg): p
            for p in remaining_pages
        }
        for future in as_completed(futures):
            logs.extend(future.result())

    return logs


def _detect_movements(logs):
    """Detect cross-ASIN movements: manual inventory changes (type 14000)
    at the exact same timestamp across 2+ ASINs."""
    by_timestamp = defaultdict(list)
    for log in logs:
        if log["type_id"] == MANUAL_INV_TYPE:
            by_timestamp[log["created_at"]].append(log)

    group_id = 0
    for ts, group_logs in by_timestamp.items():
        asins_involved = set(l["filter_asin"] for l in group_logs)
        if len(asins_involved) < 2:
            continue
        group_id += 1
        total_diff = sum(l["param_diff"] for l in group_logs)
        for l in group_logs:
            l["movement_group"] = group_id
            l["movement_net"] = total_diff
            l["movement_asins"] = len(asins_involved)


def fetch_logs_for_asins(asin_list):
    """Fetch all SoStocked logs for a list of ASINs. Returns combined list sorted by created_at DESC."""
    bearer_token, cfg = _load_credentials()
    all_logs = []

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_fetch_asin_logs, asin, bearer_token, cfg): asin
            for asin in asin_list
        }
        for future in as_completed(futures):
            all_logs.extend(future.result())

    _detect_movements(all_logs)
    all_logs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return all_logs


MAX_PERIOD_PAGES = 0  # 0 = no limit; fetch all pages


def fetch_all_logs_by_period(days):
    """Fetch all SoStocked logs within the last N days.
    Returns combined list sorted by created_at DESC."""
    bearer_token, cfg = _load_credentials()
    logs = _fetch_all_logs(days, bearer_token, cfg, max_pages=MAX_PERIOD_PAGES)
    _detect_movements(logs)
    logs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return logs

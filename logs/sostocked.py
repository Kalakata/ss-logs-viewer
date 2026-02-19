import json
import os
import time
from collections import defaultdict

import requests
from django.conf import settings

API_URL = "https://api.sostocked.com/order-shipment-logs/logs"
PER_PAGE = 100
DELAY_BETWEEN_PAGES = 0.3
DELAY_BETWEEN_ASINS = 0.5

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


MANUAL_INV_TYPE = 14000  # Manual inventory change


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

    for i, asin in enumerate(asin_list):
        logs = _fetch_asin_logs(asin, bearer_token, cfg)
        all_logs.extend(logs)
        if i < len(asin_list) - 1 and DELAY_BETWEEN_ASINS > 0:
            time.sleep(DELAY_BETWEEN_ASINS)

    _detect_movements(all_logs)
    all_logs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return all_logs

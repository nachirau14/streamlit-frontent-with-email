"""
utils/data.py
Shared data-access layer for the Streamlit dashboard.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
import uuid
import logging

import boto3
import streamlit as st
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import (
    ClientError, NoCredentialsError, PartialCredentialsError,
    EndpointResolutionError, NoRegionError,
)

logger = logging.getLogger(__name__)

# Email notifications — imported lazily so missing config never breaks data ops

def _ticker_table():
    """Return the DynamoDB ticker master table resource."""
    try:
        name = st.secrets["dynamodb"]["tickers_table"]
    except KeyError:
        raise RuntimeError(
            "tickers_table not set. Add it under [dynamodb] in your secrets: "
            "tickers_table = \"portfolio_tickers_prod\""
        )
    return _get_ddb().Table(name)


def search_tickers(prefix: str, limit: int = 12) -> list[dict]:
    """
    Search the ticker master table for symbols starting with `prefix`.
    Returns list of {symbol, company_name, exchange, face_value, isin}.
    Not cached here — caller caches via session_state if needed.
    """
    prefix = prefix.strip().upper()
    if not prefix:
        return []
    try:
        # Get raw boto3 resource directly — avoids caching unpicklable objects
        cfg = get_aws_config()
        ddb = boto3.resource(
            "dynamodb",
            region_name=cfg["region"],
            aws_access_key_id=cfg["access_key_id"],
            aws_secret_access_key=cfg["secret_access_key"],
        )
        tbl_name = st.secrets["dynamodb"]["tickers_table"]
        tbl  = ddb.Table(tbl_name)
        resp = tbl.query(
            IndexName="TickerSearchIndex",
            KeyConditionExpression=(
                Key("gsi1pk").eq("ALL_TICKERS") &
                Key("gsi1sk").begins_with(prefix)
            ),
            Limit=limit * 2,
        )
        seen:    set[str]  = set()
        results: list[dict] = []
        for item in _from_decimal_list(resp.get("Items", [])):
            sym = item.get("symbol", "")
            if sym and sym not in seen:
                seen.add(sym)
                results.append({
                    "symbol":       sym,
                    "company_name": item.get("company_name", ""),
                    "exchange":     item.get("exchange", ""),
                    "face_value":   float(item.get("face_value", 10)),
                    "isin":         item.get("isin", ""),
                })
            if len(results) >= limit:
                break
        return results
    except KeyError as exc:
        logger.warning("Ticker table not configured: %s", exc)
        return []
    except Exception as exc:
        logger.error("Ticker search error: %s", exc)
        return []


def _from_decimal_list(items: list) -> list[dict]:
    return [_from_decimal(i) for i in items]


def _notify(*args, fn_name: str, **kwargs):
    """Fire-and-forget email notification. Never raises."""
    try:
        import importlib
        mod = importlib.import_module("utils.email_alerts")
        getattr(mod, fn_name)(*args, **kwargs)
    except Exception as exc:
        logger.debug("Email notification skipped: %s", exc)

# ── Secrets helpers ──────────────────────────────────────────────────────────

def _get_secret(section: str, key: str) -> str:
    """
    Read a value from st.secrets with a clear error if missing.
    Supports both nested ([aws] access_key_id) and flat (AWS_ACCESS_KEY_ID) formats.
    """
    # Try nested first: [aws] / access_key_id
    try:
        val = st.secrets[section][key]
        if val:
            return str(val).strip()
    except (KeyError, TypeError):
        pass

    # Try flat uppercase fallback: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, etc.
    flat_key = f"{section.upper()}_{key.upper()}"
    try:
        val = st.secrets[flat_key]
        if val:
            return str(val).strip()
    except (KeyError, TypeError):
        pass

    raise KeyError(
        f"Secret '{key}' not found. "
        f"Add [{section}] {key} = \"...\" to your secrets.toml, "
        f"or set {flat_key} = \"...\" as a flat key."
    )


def get_aws_config() -> dict:
    """Return AWS credentials and config from secrets."""
    return {
        "access_key_id":     _get_secret("aws", "access_key_id"),
        "secret_access_key": _get_secret("aws", "secret_access_key"),
        "region":            _get_secret("aws", "region"),
        "trades_table":      _get_secret("dynamodb", "trades_table"),
        "xirr_table":        _get_secret("dynamodb", "xirr_table"),
    }


# ── DynamoDB connection ───────────────────────────────────────────────────────
# NOTE: NOT cached with @st.cache_resource so that credential errors don't
# get frozen into the cache and require an app restart to recover from.

def _make_dynamodb():
    cfg = get_aws_config()
    session = boto3.Session(
        aws_access_key_id=cfg["access_key_id"],
        aws_secret_access_key=cfg["secret_access_key"],
        region_name=cfg["region"],
    )
    return session.resource("dynamodb")


def _get_table(table_key: str):
    """Get a DynamoDB Table object. Raises a clear error if connection fails."""
    cfg = get_aws_config()
    ddb = _make_dynamodb()
    return ddb.Table(cfg[table_key])


def _broker_config_table():
    """Return the broker config DynamoDB table."""
    try:
        name = st.secrets["dynamodb"]["broker_config_table"]
    except (KeyError, TypeError):
        raise KeyError(
            "broker_config_table not set. Add it under [dynamodb] in your secrets: "
            "broker_config_table = \"portfolio_broker_config_prod\""
        )
    return _make_dynamodb().Table(name)


def test_connection() -> tuple[bool, str]:
    """
    Test DynamoDB connectivity. Returns (success, message).
    Used by the debug page and the main app startup check.
    """
    try:
        cfg = get_aws_config()
    except KeyError as e:
        return False, f"Missing secret: {e}"

    try:
        ddb = _make_dynamodb()
        tbl = ddb.Table(cfg["trades_table"])
        # describe_table is a lightweight call that verifies credentials + table existence
        tbl.load()
        return True, f"Connected to '{cfg['trades_table']}' in {cfg['region']}"
    except NoCredentialsError:
        return False, (
            "No AWS credentials found. "
            "Check that access_key_id and secret_access_key are set in secrets."
        )
    except PartialCredentialsError as e:
        return False, f"Incomplete credentials: {e}"
    except ClientError as e:
        code = e.response["Error"]["Code"]
        msg  = e.response["Error"]["Message"]
        if code == "ResourceNotFoundException":
            return False, (
                f"Table '{cfg['trades_table']}' not found in region '{cfg['region']}'. "
                "Check the table name and region in your secrets."
            )
        if code in ("InvalidSignatureException", "UnrecognizedClientException"):
            return False, (
                f"Invalid AWS credentials ({code}). "
                "Double-check access_key_id and secret_access_key."
            )
        if code == "AccessDeniedException":
            return False, (
                f"Access denied ({msg}). "
                "Ensure the IAM user has dynamodb:Query, Scan, GetItem, PutItem on both tables."
            )
        return False, f"AWS error ({code}): {msg}"
    except EndpointResolutionError as e:
        return False, f"Invalid region or endpoint: {e}"
    except NoRegionError:
        return False, "No AWS region specified. Add region = \"ap-south-1\" under [aws] in secrets."
    except Exception as e:
        return False, f"Unexpected error: {type(e).__name__}: {e}"


# ── Decimal helpers ───────────────────────────────────────────────────────────

def _to_decimal(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if isinstance(value, dict):
        return {k: _to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_decimal(i) for i in value]
    return value


def _from_decimal(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _from_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_decimal(i) for i in value]
    return value


def _paginate_query(table, **kwargs) -> list[dict]:
    items    = []
    response = table.query(**kwargs)
    items   += response.get("Items", [])
    while response.get("LastEvaluatedKey"):
        response = table.query(**kwargs, ExclusiveStartKey=response["LastEvaluatedKey"])
        items   += response.get("Items", [])
    return items


# ── Constants ─────────────────────────────────────────────────────────────────

VALID_ACTIONS = {"BUY", "SELL", "DIVIDEND", "BONUS", "RIGHTS",
                 "SPLIT", "MERGER", "DEMERGER"}
ACTION_SK_PREFIX = {
    "BUY":       "trade",
    "SELL":      "trade",
    "DIVIDEND":  "dividend",
    "BONUS":     "bonus",
    "RIGHTS":    "rights",
    "SPLIT":     "split",
    "MERGER":    "merger",
    "DEMERGER":  "demerger",
}
ACTION_COLOURS = {
    "BUY":       "#00A88A",
    "SELL":      "#E53E3E",
    "DIVIDEND":  "#0891B2",
    "BONUS":     "#7C3AED",
    "RIGHTS":    "#D97706",
    "SPLIT":     "#0284C7",
    "MERGER":    "#9333EA",
    "DEMERGER":  "#EA580C",
}


# ── Cached DynamoDB reads ─────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def load_all_latest_xirr() -> list[dict]:
    """All latest XIRR snapshots (one per scrip + PORTFOLIO). Cached 5 min."""
    tbl      = _get_table("xirr_table")
    response = tbl.scan(FilterExpression=Attr("sk").eq("snapshot#LATEST"))
    items    = response.get("Items", [])
    while response.get("LastEvaluatedKey"):
        response = tbl.scan(
            FilterExpression=Attr("sk").eq("snapshot#LATEST"),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items += response.get("Items", [])
    return [_from_decimal(i) for i in items]


@st.cache_data(ttl=300, show_spinner=False)
def load_snapshot_on_date(symbol: str | None, target_date: str) -> dict | None:
    """
    Return the XIRR snapshot closest to (but not after) target_date.
    symbol=None → portfolio-level snapshot.
    target_date: ISO date string e.g. "2026-03-07"
    """
    pk = "PORTFOLIO" if symbol is None else f"scrip#{symbol.upper()}"
    try:
        items = _paginate_query(
            _get_table("xirr_table"),
            KeyConditionExpression=(
                Key("pk").eq(pk) &
                Key("sk").between("snapshot#2000", f"snapshot#{target_date}z")
            ),
            ScanIndexForward=False,
            Limit=1,
        )
        return _from_decimal(items[0]) if items else None
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def load_xirr_history(symbol: str | None, limit: int = 90) -> list[dict]:
    pk    = "PORTFOLIO" if symbol is None else f"scrip#{symbol.upper()}"
    items = _paginate_query(
        _get_table("xirr_table"),
        KeyConditionExpression=Key("pk").eq(pk) & Key("sk").begins_with("snapshot#2"),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [_from_decimal(i) for i in items]


@st.cache_data(ttl=300, show_spinner=False)
def load_trades_for_scrip(symbol: str) -> list[dict]:
    items = _paginate_query(
        _get_table("trades_table"),
        KeyConditionExpression=Key("pk").eq(f"scrip#{symbol.upper()}"),
    )
    valid = [_from_decimal(i) for i in items if i.get("action", "").upper() in VALID_ACTIONS]
    return sorted(valid, key=lambda x: x["trade_date"])


@st.cache_data(ttl=300, show_spinner=False)
def load_all_trades() -> dict[str, list[dict]]:
    items = _paginate_query(
        _get_table("trades_table"),
        IndexName="AllTradesIndex",
        KeyConditionExpression=Key("gsi1pk").eq("ALL_TRADES"),
    )
    result: dict[str, list[dict]] = {}
    for raw in items:
        item   = _from_decimal(raw)
        symbol = item.get("symbol", "").upper()
        action = item.get("action", "").upper()
        if symbol and action in VALID_ACTIONS:
            result.setdefault(symbol, []).append(item)
    return result


# ── Write ─────────────────────────────────────────────────────────────────────

def put_record(record: dict) -> str:
    symbol = record["symbol"].upper()
    tdate  = record["trade_date"]
    action = record["action"].upper()
    broker = record.get("broker", "").strip().upper()
    sector = record.get("sector", "").strip().upper()

    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action '{action}'")

    prefix = ACTION_SK_PREFIX[action]
    sk     = f"{prefix}#{tdate}#{uuid.uuid4()}"
    gsi_sk = f"{action}#{symbol}#{tdate}"

    item = {
        "pk":         f"scrip#{symbol}",
        "sk":         sk,
        "gsi1pk":     "ALL_TRADES",
        "gsi1sk":     gsi_sk,
        "symbol":     symbol,
        "trade_date": tdate,
        "action":     action,
        "qty":        Decimal(str(record["qty"])),
        "price":      Decimal(str(record["price"])),
        "charges":    Decimal(str(record.get("charges", 0))),
        "notes":      record.get("notes", ""),
        "broker":     broker,
        "sector":     sector,
    }
    # Only set GSI2/GSI3 keys when broker/sector are provided
    # (DynamoDB only indexes items that have the GSI key attributes)
    if broker:
        item["gsi2pk"] = f"broker#{broker}"
        item["gsi2sk"] = gsi_sk
    if sector:
        item["gsi3pk"] = f"sector#{sector}"
        item["gsi3sk"] = gsi_sk

    _get_table("trades_table").put_item(Item=item)

    load_trades_for_scrip.clear()
    load_all_trades.clear()
    load_all_latest_xirr.clear()
    load_xirr_history.clear()
    # Auto-register broker if new
    if record.get("broker"):
        ensure_brokers_registered([record["broker"]])
    _notify(record, fn_name="notify_trade_added")
    return sk



def batch_put_records(records: list[dict]) -> tuple[int, list[str]]:
    """
    Write a list of validated records to DynamoDB using batch_writer.
    Returns (written_count, list_of_errors).
    Records are appended — existing items with different SKs are untouched.
    """
    table    = _get_table("trades_table")
    written  = 0
    errors   = []

    # Build all items first so validation errors surface before any writes
    items = []
    for i, record in enumerate(records):
        try:
            symbol = record["symbol"].upper()
            tdate  = record["trade_date"]
            action = record["action"].upper()

            if action not in VALID_ACTIONS:
                errors.append(f"Row {i+1} ({symbol}): invalid action '{action}'")
                continue

            prefix = ACTION_SK_PREFIX[action]
            broker = record.get("broker", "").strip().upper()
            sector = record.get("sector", "").strip().upper()
            gsi_sk = f"{action}#{symbol}#{tdate}"
            item   = {
                "pk":         f"scrip#{symbol}",
                "sk":         f"{prefix}#{tdate}#{uuid.uuid4()}",
                "gsi1pk":     "ALL_TRADES",
                "gsi1sk":     gsi_sk,
                "symbol":     symbol,
                "trade_date": tdate,
                "action":     action,
                "qty":        Decimal(str(record["qty"])),
                "price":      Decimal(str(record["price"])),
                "charges":    Decimal(str(record.get("charges", 0))),
                "notes":      record.get("notes", ""),
                "broker":     broker,
                "sector":     sector,
            }
            if broker:
                item["gsi2pk"] = f"broker#{broker}"
                item["gsi2sk"] = gsi_sk
            if sector:
                item["gsi3pk"] = f"sector#{sector}"
                item["gsi3sk"] = gsi_sk
            items.append(item)
        except Exception as e:
            errors.append(f"Row {i+1}: {e}")

    # Batch write in chunks of 25 (DynamoDB limit)
    chunk_size = 25
    for start in range(0, len(items), chunk_size):
        chunk = items[start:start + chunk_size]
        try:
            with table.batch_writer() as batch:
                for item in chunk:
                    batch.put_item(Item=item)
            written += len(chunk)
        except Exception as e:
            errors.append(f"Batch write error (rows {start+1}-{start+len(chunk)}): {e}")

    if written > 0:
        load_trades_for_scrip.clear()
        load_all_trades.clear()
        load_all_latest_xirr.clear()
        symbols_written = list({r.get("symbol","") for r in records if r.get("symbol")})
        broker_names = list({r.get("broker","") for r in records if r.get("broker")})
        ensure_brokers_registered(broker_names)
        _notify(written, len(errors), symbols_written, fn_name="notify_bulk_upload")

    return written, errors


def delete_record(pk: str, sk: str, symbol: str = "") -> None:
    """Delete a single trade record by its primary key."""
    _get_table("trades_table").delete_item(Key={"pk": pk, "sk": sk})
    load_trades_for_scrip.clear()
    load_all_trades.clear()
    load_all_latest_xirr.clear()
    load_xirr_history.clear()
    _notify(pk, sk, symbol, fn_name="notify_trade_deleted")


def rename_symbol_record(pk: str, sk: str, new_symbol: str, existing_record: dict) -> str:
    """
    Rename the symbol on a trade record. Because symbol is embedded in pk, sk,
    and all GSI keys, we delete the old item and write a fresh one with the new symbol.
    Returns the new SK.
    """
    new_symbol = new_symbol.strip().upper()
    table      = _get_table("trades_table")

    # Build the new item from the existing record
    action = existing_record.get("action", "").upper()
    tdate  = existing_record.get("trade_date", "")
    broker = existing_record.get("broker", "").strip().upper()
    sector = existing_record.get("sector", "").strip().upper()
    gsi_sk = f"{action}#{new_symbol}#{tdate}"
    prefix = ACTION_SK_PREFIX.get(action, "trade")
    new_sk = f"{prefix}#{tdate}#{uuid.uuid4()}"

    new_item = {
        "pk":         f"scrip#{new_symbol}",
        "sk":         new_sk,
        "gsi1pk":     "ALL_TRADES",
        "gsi1sk":     gsi_sk,
        "symbol":     new_symbol,
        "trade_date": tdate,
        "action":     action,
        "qty":        _to_decimal(float(existing_record.get("qty", 0))),
        "price":      _to_decimal(float(existing_record.get("price", 0))),
        "charges":    _to_decimal(float(existing_record.get("charges", 0))),
        "notes":      existing_record.get("notes", ""),
        "broker":     broker,
        "sector":     sector,
    }
    if broker:
        new_item["gsi2pk"] = f"broker#{broker}"
        new_item["gsi2sk"] = gsi_sk
    if sector:
        new_item["gsi3pk"] = f"sector#{sector}"
        new_item["gsi3sk"] = gsi_sk

    # Write new, then delete old — order matters for safety
    table.put_item(Item=new_item)
    table.delete_item(Key={"pk": pk, "sk": sk})

    load_trades_for_scrip.clear()
    load_all_trades.clear()
    load_all_latest_xirr.clear()
    return new_sk


def update_record(pk: str, sk: str, updates: dict) -> None:
    """
    Update editable fields on an existing trade record.
    Allowed fields: trade_date, qty, price, charges, notes.
    Symbol changes must go through rename_symbol_record().
    """
    allowed = {"trade_date", "qty", "price", "charges", "notes"}
    expr_parts = []
    attr_names  = {}
    attr_values = {}

    for field, value in updates.items():
        if field not in allowed:
            continue
        placeholder_n = f"#f_{field}"
        placeholder_v = f":v_{field}"
        expr_parts.append(f"{placeholder_n} = {placeholder_v}")
        attr_names[placeholder_n] = field

        if field in ("qty", "price", "charges"):
            attr_values[placeholder_v] = Decimal(str(value))
        else:
            attr_values[placeholder_v] = str(value)

    if not expr_parts:
        return

    _get_table("trades_table").update_item(
        Key={"pk": pk, "sk": sk},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )
    load_trades_for_scrip.clear()
    load_all_trades.clear()
    load_all_latest_xirr.clear()
    load_xirr_history.clear()
    _notify({"pk": pk, "sk": sk, **updates}, fn_name="notify_trade_edited")



# ── NSE Sectors ───────────────────────────────────────────────────────────────

NSE_SECTORS = sorted([
    "Auto", "Aviation", "Banking", "Capital Goods", "Chemicals",
    "Consumer Durables", "Consumer Staples", "Defence", "Energy",
    "Fertilisers", "Financial Services", "FMCG", "Healthcare",
    "Infrastructure", "IT", "Logistics", "Media", "Metals & Mining",
    "Oil & Gas", "Paints", "Pharma", "Power", "PSU", "Real Estate",
    "Retail", "Telecom", "Textiles", "Others",
])

DEFAULT_BROKERS = [
    "ZERODHA", "GROWW", "ICICI_DIRECT", "HDFC_SECURITIES",
    "UPSTOX", "ANGEL_ONE", "KOTAK_SECURITIES", "5PAISA",
    "MOTILAL_OSWAL", "SBI_SECURITIES",
]


# ── Broker config CRUD ────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def load_broker_configs() -> list[dict]:
    """
    Return all broker configs sorted by name.
    Filters to only broker config items (sk="config"),
    excluding email/other config items in the same table.
    """
    try:
        tbl      = _broker_config_table()
        response = tbl.scan()
        items    = [_from_decimal(i) for i in response.get("Items", [])]
        while response.get("LastEvaluatedKey"):
            response = tbl.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items   += [_from_decimal(i) for i in response.get("Items", [])]
        # Only return broker config items, not email config or other special items
        broker_items = [
            i for i in items
            if str(i.get("pk","")).startswith("broker#")
            and i.get("sk") == "config"
        ]
        return sorted(broker_items, key=lambda x: x.get("broker_name", ""))
    except Exception:
        return []


def get_all_broker_names() -> list[str]:
    """
    Return a sorted list of all known broker names — from both the config table
    and directly from trade records. Ensures brokers in trades always appear
    in dropdowns even before explicit registration.
    """
    # From config table
    configured = {
        c.get("broker_key", ""): c.get("broker_name", c.get("broker_key", ""))
        for c in load_broker_configs()
        if c.get("broker_key")
    }
    # From trades — pick up any brokers used but not yet in config table
    try:
        all_t = load_all_trades()
        for trades in all_t.values():
            for t in trades:
                bk = t.get("broker","").strip().upper()
                if bk and bk not in configured:
                    configured[bk] = bk.replace("_"," ").title()
    except Exception:
        pass
    return sorted(configured.values())


def save_broker_config(config: dict) -> None:
    """
    Upsert a broker config item.
    config must contain: broker_key or broker_name.
    Charge rates are optional — stored if provided, defaulted to 0 otherwise.
    broker_key is derived from broker_name if not explicitly provided.
    """
    broker_name = config.get("broker_name", "").strip()
    broker_key  = config.get("broker_key", "").strip().upper()
    if not broker_key and broker_name:
        # Derive key from name: uppercase, spaces → underscores
        broker_key = broker_name.upper().replace(" ", "_")
    if not broker_key:
        raise ValueError("broker_key or broker_name is required")
    if not broker_name:
        broker_name = broker_key.replace("_", " ").title()

    item = {
        "pk":           f"broker#{broker_key}",
        "sk":           "config",
        "broker_key":   broker_key,
        "broker_name":  broker_name,
        "buy_pct":      Decimal(str(config.get("buy_pct",    0.0))),
        "buy_min":      Decimal(str(config.get("buy_min",    0.0))),
        "sell_pct":     Decimal(str(config.get("sell_pct",   0.0))),
        "sell_min":     Decimal(str(config.get("sell_min",   0.0))),
        "rights_pct":   Decimal(str(config.get("rights_pct", 0.0))),
        "rights_min":   Decimal(str(config.get("rights_min", 0.0))),
    }
    _broker_config_table().put_item(Item=item)
    load_broker_configs.clear()


def ensure_brokers_registered(broker_names: list[str]) -> None:
    """
    Auto-register any broker names that appear in trades but aren't in
    the broker config table yet. Called after bulk upload and add trade.
    Creates a minimal config entry with zero rates.
    """
    if not broker_names:
        return
    try:
        existing = {c.get("broker_key", "") for c in load_broker_configs()}
        for name in broker_names:
            name = name.strip().upper()
            if not name:
                continue
            key = name.replace(" ", "_")
            if key not in existing:
                save_broker_config({"broker_key": key, "broker_name": name})
                logger.info("Auto-registered broker: %s", key)
    except Exception as exc:
        logger.warning("ensure_brokers_registered failed: %s", exc)


def delete_broker_config(broker_key: str) -> None:
    _broker_config_table().delete_item(
        Key={"pk": f"broker#{broker_key.upper()}", "sk": "config"}
    )
    load_broker_configs.clear()


def calc_broker_charges(
    broker_key: str,
    action: str,
    qty: float,
    price: float,
    configs: list[dict],
) -> float:
    """
    Calculate brokerage charges for a trade using the broker's preset rates.
    Returns max(trade_value * rate_pct / 100, min_charge).
    Returns 0.0 for DIVIDEND and BONUS (no charges apply).
    """
    if action.upper() in ("DIVIDEND", "BONUS") or not broker_key:
        return 0.0

    cfg = next((c for c in configs if c.get("broker_key") == broker_key.upper()), None)
    if cfg is None:
        return 0.0

    trade_value = qty * price
    action_up   = action.upper()

    if action_up in ("BUY",):
        pct = float(cfg.get("buy_pct",    0.03))
        min_c = float(cfg.get("buy_min",  20.0))
    elif action_up == "SELL":
        pct   = float(cfg.get("sell_pct",  0.03))
        min_c = float(cfg.get("sell_min", 20.0))
    elif action_up == "RIGHTS":
        pct   = float(cfg.get("rights_pct",  0.03))
        min_c = float(cfg.get("rights_min", 20.0))
    else:
        return 0.0

    calculated = trade_value * pct / 100.0
    return round(max(calculated, min_c), 2)


# ── Broker / Sector trade reads ───────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def load_trades_by_broker(broker_key: str) -> dict[str, list[dict]]:
    """
    All trade records for a given broker, grouped by symbol.
    Uses the BrokerIndex GSI.
    """
    items = _paginate_query(
        _get_table("trades_table"),
        IndexName="BrokerIndex",
        KeyConditionExpression=Key("gsi2pk").eq(f"broker#{broker_key.upper()}"),
    )
    result: dict[str, list[dict]] = {}
    for raw in items:
        item   = _from_decimal(raw)
        symbol = item.get("symbol", "").upper()
        action = item.get("action", "").upper()
        if symbol and action in VALID_ACTIONS:
            result.setdefault(symbol, []).append(item)
    return result


@st.cache_data(ttl=300, show_spinner=False)
def load_trades_by_sector(sector: str) -> dict[str, list[dict]]:
    """
    All trade records for a given sector, grouped by symbol.
    Uses the SectorIndex GSI.
    """
    items = _paginate_query(
        _get_table("trades_table"),
        IndexName="SectorIndex",
        KeyConditionExpression=Key("gsi3pk").eq(f"sector#{sector.upper()}"),
    )
    result: dict[str, list[dict]] = {}
    for raw in items:
        item   = _from_decimal(raw)
        symbol = item.get("symbol", "").upper()
        action = item.get("action", "").upper()
        if symbol and action in VALID_ACTIONS:
            result.setdefault(symbol, []).append(item)
    return result


def get_all_brokers_from_trades() -> list[str]:
    """Scan all trades and return unique broker keys (excluding empty)."""
    all_trades = load_all_trades()
    brokers: set[str] = set()
    for records in all_trades.values():
        for r in records:
            b = r.get("broker", "").strip().upper()
            if b:
                brokers.add(b)
    return sorted(brokers)


def get_all_sectors_from_trades() -> list[str]:
    """Scan all trades and return unique sector values (excluding empty)."""
    all_trades = load_all_trades()
    sectors: set[str] = set()
    for records in all_trades.values():
        for r in records:
            s = r.get("sector", "").strip().upper()
            if s:
                sectors.add(s)
    return sorted(sectors)



# ── Email alert config (stored in broker_config table under pk="email#config") ─

_EMAIL_CONFIG_PK = "email#config"
_EMAIL_CONFIG_SK = "settings"

@st.cache_data(ttl=60, show_spinner=False)
def load_email_config() -> dict:
    """
    Load email alert preferences from DynamoDB.
    Returns defaults if no config has been saved yet.
    """
    defaults = {
        "enabled":          False,
        "to_address":       "",
        "alert_trade_add":  True,
        "alert_trade_edit": True,
        "alert_trade_del":  True,
        "alert_bulk":       True,
        "alert_weekly":     True,
        "weekly_day":       "Friday",
    }
    try:
        tbl  = _broker_config_table()
        resp = tbl.get_item(Key={"pk": _EMAIL_CONFIG_PK, "sk": _EMAIL_CONFIG_SK})
        item = resp.get("Item")
        if not item:
            return defaults
        merged = {**defaults}
        for k in defaults:
            if k in item:
                v = item[k]
                # DynamoDB booleans are stored as bool; numbers as Decimal
                if isinstance(v, bool):
                    merged[k] = v
                elif str(v).lower() in ("true", "false"):
                    merged[k] = str(v).lower() == "true"
                else:
                    merged[k] = str(v)
        return merged
    except Exception:
        return defaults


def save_email_config(cfg: dict) -> None:
    """Save email alert preferences to DynamoDB."""
    tbl = _broker_config_table()
    item = {
        "pk":               _EMAIL_CONFIG_PK,
        "sk":               _EMAIL_CONFIG_SK,
        "enabled":          bool(cfg.get("enabled", False)),
        "to_address":       str(cfg.get("to_address", "")).strip(),
        "alert_trade_add":  bool(cfg.get("alert_trade_add",  True)),
        "alert_trade_edit": bool(cfg.get("alert_trade_edit", True)),
        "alert_trade_del":  bool(cfg.get("alert_trade_del",  True)),
        "alert_bulk":       bool(cfg.get("alert_bulk",       True)),
        "alert_weekly":     bool(cfg.get("alert_weekly",     True)),
        "weekly_day":       str(cfg.get("weekly_day", "Friday")),
    }
    tbl.put_item(Item=item)
    load_email_config.clear()


def _fetch_prices_via_yfinance(symbols: list[str]) -> dict[str, float]:
    """
    Fetch current prices using yfinance from Streamlit Cloud.
    Tries NSE (.NS) first, then BSE (.BO) for any that failed.
    Handles both single-ticker (simple columns) and multi-ticker
    (MultiIndex columns) responses from yfinance.
    """
    import yfinance as yf
    import pandas as pd

    prices: dict[str, float] = {}

    def _parse_yf_data(data, syms: list[str], suffix: str) -> dict[str, float]:
        """Extract close prices from a yfinance download result."""
        result: dict[str, float] = {}
        if data is None or data.empty:
            return result

        # yfinance returns MultiIndex columns for multiple tickers,
        # simple columns for a single ticker
        if isinstance(data.columns, pd.MultiIndex):
            # Multi-ticker: columns are (field, ticker) e.g. ('Close', 'RELIANCE.NS')
            if "Close" in data.columns.get_level_values(0):
                close_df = data["Close"]
            elif "Adj Close" in data.columns.get_level_values(0):
                close_df = data["Adj Close"]
            else:
                return result
            last = close_df.dropna(how="all").iloc[-1]
            for col in last.index:
                sym   = str(col).replace(suffix, "").upper()
                price = last[col]
                try:
                    p = float(price)
                    if p > 0 and p == p:  # > 0 and not NaN
                        result[sym] = p
                except (TypeError, ValueError):
                    pass
        else:
            # Single ticker: columns are field names e.g. 'Close'
            col_name = "Close" if "Close" in data.columns else (
                "Adj Close" if "Adj Close" in data.columns else None
            )
            if col_name:
                series = data[col_name].dropna()
                if not series.empty:
                    # syms should have exactly one entry here
                    sym = syms[0] if syms else ""
                    try:
                        p = float(series.iloc[-1])
                        if p > 0:
                            result[sym] = p
                    except (TypeError, ValueError):
                        pass
        return result

    def _download(syms: list[str], suffix: str) -> dict[str, float]:
        if not syms:
            return {}
        tickers_str = " ".join(f"{s}{suffix}" for s in syms)
        try:
            data = yf.download(
                tickers_str,
                period="2d",
                interval="1d",
                progress=False,
                threads=True,
                timeout=30,
            )
            return _parse_yf_data(data, syms, suffix)
        except Exception as e:
            logger.warning("yfinance download %s failed: %s", suffix, e)
            return {}

    def _individual(sym: str, suffix: str) -> float | None:
        try:
            hist = yf.Ticker(f"{sym}{suffix}").history(period="2d", timeout=15)
            if not hist.empty:
                p = float(hist["Close"].dropna().iloc[-1])
                if p > 0:
                    return p
        except Exception:
            pass
        return None

    # Pass 1: batch NSE
    prices.update(_download(symbols, ".NS"))

    # Pass 2: missing symbols — try BSE batch
    missing = [s for s in symbols if s not in prices]
    if missing:
        logger.info("Trying BSE (.BO) for %d symbol(s): %s", len(missing), missing)
        prices.update(_download(missing, ".BO"))

    # Pass 3: still missing — individual fetch for both exchanges
    still_missing = [s for s in symbols if s not in prices]
    for sym in still_missing:
        price = _individual(sym, ".NS") or _individual(sym, ".BO")
        if price:
            prices[sym] = price
            logger.info("Fetched %s individually: %.2f", sym, price)
        else:
            logger.warning("No price for %s on NSE or BSE", sym)

    return prices


# ── NSE face value lookup ─────────────────────────────────────────────────────
# Standard NSE face values for common scrips.
# Source: NSE website / company filings.
# These only change on a SPLIT — when that happens, record a SPLIT trade
# with price = new face value, which overrides this lookup.

_NSE_FACE_VALUES: dict[str, float] = {
    # ₹1 face value
    "INFY": 5.0, "TCS": 1.0, "WIPRO": 2.0, "HCLTECH": 2.0, "TECHM": 5.0,
    "LTIM": 1.0, "MPHASIS": 10.0, "COFORGE": 10.0, "PERSISTENT": 5.0, "KPITTECH": 2.0,
    "RELIANCE": 10.0, "ONGC": 5.0, "BPCL": 10.0, "IOC": 10.0, "HINDPETRO": 10.0,
    "HDFCBANK": 1.0, "ICICIBANK": 2.0, "AXISBANK": 2.0, "KOTAKBANK": 5.0,
    "SBIN": 1.0, "BANKBARODA": 2.0, "PNB": 2.0, "CANBK": 2.0, "UNIONBANK": 1.0,
    "INDUSINDBK": 10.0, "FEDERALBNK": 2.0, "IDFCFIRSTB": 10.0, "RBLBANK": 10.0,
    "HDFCLIFE": 10.0, "SBILIFE": 10.0, "ICICIGI": 10.0, "MAXHEALTH": 2.0,
    "SUNPHARMA": 1.0, "DRREDDY": 5.0, "CIPLA": 2.0, "DIVISLAB": 2.0,
    "AUROPHARMA": 1.0, "LUPIN": 2.0, "BIOCON": 5.0, "ALKEM": 2.0, "IPCALAB": 2.0,
    "HINDUNILVR": 1.0, "ITC": 1.0, "NESTLEIND": 1.0, "BRITANNIA": 1.0,
    "DABUR": 1.0, "MARICO": 1.0, "COLPAL": 1.0, "GODREJCP": 1.0, "TATACONSUM": 1.0,
    "MARUTI": 5.0, "TATAMOTORS": 2.0, "BAJAJ-AUTO": 10.0, "HEROMOTOCO": 2.0,
    "EICHERMOT": 1.0, "TVSMOTOR": 1.0, "ASHOKLEY": 1.0, "MOTHERSON": 1.0,
    "ASIANPAINT": 1.0, "BERGEPAINT": 1.0, "KANSAINER": 1.0, "PIDILITIND": 1.0,
    "TITAN": 1.0, "TRENT": 10.0, "BATAINDIA": 5.0, "VBL": 2.0,
    "BAJFINANCE": 2.0, "BAJAJFINSV": 2.0, "CHOLAFIN": 2.0, "MUTHOOTFIN": 10.0,
    "HDFCAMC": 5.0, "NAUKRI": 10.0, "PAYTM": 1.0, "POLICYBZR": 2.0,
    "ADANIENT": 1.0, "ADANIPORTS": 2.0, "ADANIPOWER": 10.0, "ADANIGREEN": 10.0,
    "JSWSTEEL": 1.0, "TATASTEEL": 1.0, "HINDALCO": 1.0, "VEDL": 1.0,
    "COALINDIA": 10.0, "NMDC": 1.0, "SAIL": 10.0, "NATIONALUM": 5.0,
    "NTPC": 10.0, "POWERGRID": 10.0, "NHPC": 10.0, "SJVN": 10.0,
    "TATAPOWER": 1.0, "JSWENERGY": 10.0, "TORNTPOWER": 10.0,
    "LT": 2.0, "BHEL": 2.0, "BEL": 1.0, "HAL": 10.0, "CONCOR": 10.0,
    "IRCTC": 2.0, "RVNL": 10.0, "NBCC": 1.0,
    "GRASIM": 2.0, "ULTRACEMCO": 10.0, "AMBUJACEM": 2.0, "ACC": 10.0,
    "SHREECEM": 10.0, "JKCEMENT": 10.0,
    "DLF": 2.0, "GODREJPROP": 5.0, "OBEROIRLTY": 10.0, "PHOENIXLTD": 2.0,
    "ZOMATO": 1.0, "NYKAA": 1.0, "DELHIVERY": 1.0, "MAPMYINDIA": 2.0,
    "DIXON": 2.0, "AMBER": 10.0, "DMART": 10.0, "PVRINOX": 10.0,
    "INDIGO": 10.0, "SPICEJET": 10.0,
    "BHARTIARTL": 5.0, "IDEA": 10.0, "INDUSTOWER": 10.0,
    "OFSS": 5.0, "MFSL": 10.0, "POONAWALLA": 2.0,
    "PAGEIND": 10.0, "POLYCAB": 10.0, "HAVELLS": 1.0, "VGUARD": 1.0,
    "SUPREMEIND": 2.0, "ASTRAL": 1.0, "APOLLOTYRE": 1.0, "BALKRISIND": 2.0,
    "CUMMINSIND": 2.0, "ABB": 2.0, "BOSCHLTD": 10.0, "SKFINDIA": 10.0,
    "DEEPAKNTR": 20.0, "PIDILITIND": 1.0, "ATUL": 10.0, "FINEORG": 5.0,
    "LALPATHLAB": 10.0, "METROPOLIS": 2.0, "THYROCARE": 10.0,
    "SOLARINDS": 10.0, "NAVINFLUOR": 10.0, "FLUOROCHEM": 1.0,
    "IRFC": 10.0, "PFC": 10.0, "RECLTD": 10.0, "HUDCO": 10.0,
    # default for unknown scrips
}

_NSE_FACE_VALUE_DEFAULT = 10.0   # most common NSE face value


def fetch_face_values_yfinance(symbols: list[str]) -> dict[str, float]:
    """
    Return face values for the given symbols using the curated lookup table.
    Returns the default ₹10 for any symbol not in the table.
    When a scrip has a SPLIT trade record, that overrides this value.
    """
    return {sym: _NSE_FACE_VALUES.get(sym, _NSE_FACE_VALUE_DEFAULT) for sym in symbols}


def trigger_lambda(symbols: list[str] | None = None) -> tuple[bool, str]:
    """
    Fetch current prices from Yahoo Finance (Streamlit Cloud IPs are not blocked),
    then invoke the XIRR updater Lambda synchronously with the prices in the payload.

    Lambda receives: {"prices": {"RELIANCE": 2950.5, ...}}
    and skips its own price-fetching step entirely.

    Returns (success, message).
    """
    try:
        fn_name = st.secrets["lambda"]["function_name"].strip()
    except (KeyError, TypeError):
        return False, (
            "Lambda function name not configured. "
            "Add [lambda] function_name = \"portfolio-xirr-updater-prod\" to your secrets."
        )

    # Step 1: determine which symbols to recalculate
    # If a filtered list is passed, only those symbols are recalculated.
    try:
        all_trades    = load_all_trades()
        all_symbols   = list(all_trades.keys())
        target_symbols = symbols if symbols else all_symbols
        if not target_symbols:
            return False, "No trades found in the trades table. Upload trades first."
    except Exception as e:
        return False, f"Could not load trades: {e}"

    # Step 2: fetch prices via yfinance (Streamlit Cloud IPs work fine)
    try:
        prices = _fetch_prices_via_yfinance(target_symbols)
        if not prices:
            return False, (
                "Could not fetch any prices from Yahoo Finance. "
                "Check your internet connection or try again in a few minutes."
            )
        if len(prices) < len(target_symbols):
            no_price = [s for s in target_symbols if s not in prices]
            logger.warning("No price for %d symbol(s): %s", len(no_price), no_price)
            # Continue — Lambda will use DynamoDB snapshots for missing ones
        logger.info("Fetched %d/%d prices via yfinance", len(prices), len(target_symbols))
    except Exception as e:
        return False, f"Price fetch failed: {e}"

    # Step 3: invoke Lambda synchronously (RequestResponse) so we get the result
    try:
        import json as _json
        cfg     = get_aws_config()
        session = boto3.Session(
            aws_access_key_id=cfg["access_key_id"],
            aws_secret_access_key=cfg["secret_access_key"],
            region_name=cfg["region"],
        )
        client  = session.client("lambda")
        payload = _json.dumps({"prices": prices, "symbols": target_symbols}).encode()

        response = client.invoke(
            FunctionName=fn_name,
            InvocationType="RequestResponse",  # synchronous — wait for result
            Payload=payload,
        )
        status = response.get("StatusCode", 0)

        if status == 200:
            result_payload = _json.loads(response["Payload"].read())
            body = _json.loads(result_payload.get("body", "{}"))
            updated = body.get("scrips_updated", "?")
            failed  = body.get("scrips_failed", 0)
            xirr    = body.get("portfolio_xirr")
            xirr_str = f" · Portfolio XIRR: {xirr:.2f}%" if xirr else ""
            msg = (
                f"XIRR updated for {updated} scrips "
                f"({len(prices)} prices fetched){xirr_str}."
            )
            if failed:
                msg += f" {failed} scrip(s) failed — check Lambda logs."
            # Bust caches so dashboard shows fresh data immediately
            load_all_latest_xirr.clear()
            load_xirr_history.clear()
            return True, msg

        return False, f"Lambda returned unexpected status {status}."

    except Exception as e:
        err = getattr(e, "response", {})
        if isinstance(err, dict):
            ec = err.get("Error", {}).get("Code", "")
            if ec == "AccessDeniedException":
                return False, (
                    "Access denied invoking Lambda. "
                    "Add lambda:InvokeFunction permission to your IAM user."
                )
        return False, f"{type(e).__name__}: {e}"

# ── XIRR engine ───────────────────────────────────────────────────────────────

def _parse_date(d):
    if isinstance(d, datetime): return d.date()
    if isinstance(d, date):     return d
    return date.fromisoformat(str(d))


def _xirr_newton(cashflows: list[tuple[date, float]], guess: float = 0.1) -> float | None:
    if not cashflows:
        return None
    dates, amounts = zip(*cashflows)
    t0 = dates[0]

    def _y(d):    return (d - t0).days / 365.0

    def _npv(r):
        try:
            return sum(a / (1 + r) ** _y(d) for d, a in zip(dates, amounts))
        except (ZeroDivisionError, OverflowError):
            return float("inf")

    def _dnpv(r):
        try:
            return sum(-_y(d) * a / (1 + r) ** (_y(d) + 1) for d, a in zip(dates, amounts))
        except (ZeroDivisionError, OverflowError):
            return 0.0

    rate = guess
    for _ in range(1000):
        # Guard: (1 + rate) must stay positive to avoid complex numbers
        # from fractional exponentiation of negative base
        if rate <= -1.0:
            rate = -0.9
        npv, dnpv = _npv(rate), _dnpv(rate)
        if abs(dnpv) < 1e-12:
            break
        new_rate = rate - npv / dnpv
        # Clamp to avoid divergence below -1
        new_rate = max(new_rate, -0.9999)
        if abs(new_rate - rate) < 1e-8:
            result = new_rate
            # Final safety: return None if result is complex or non-finite
            if isinstance(result, complex) or not (-1 < result < 100):
                return None
            return float(result)
        rate = new_rate

    return None


def compute_xirr(trades: list[dict], lmp: float, as_of_str: str) -> dict:
    """
    Compute XIRR and portfolio metrics from raw trade records.
    Handles BUY, SELL, DIVIDEND, BONUS, RIGHTS, SPLIT, MERGER, DEMERGER.
    SPLIT events retroactively adjust prior BUY/SELL quantities and prices.
    """
    as_of    = _parse_date(as_of_str)
    holdings = 0.0
    merged   = False
    cashflows: list[tuple[date, float]] = []
    totals   = dict(total_invested=0.0, total_realised=0.0, total_dividends=0.0,
                    bonus_shares=0.0, rights_shares=0.0, rights_cost=0.0,
                    split_factor=1.0, face_value=None)

    # Pre-compute cumulative split adjustment factors
    split_events: list[tuple[date, float]] = []
    for t in sorted(trades, key=lambda x: x["trade_date"]):
        if t["action"].upper() == "SPLIT":
            ratio = float(t.get("qty", 1))
            if ratio > 0 and ratio != 1:
                split_events.append((_parse_date(t["trade_date"]), ratio))

    def _split_adj(cf_date: date) -> float:
        """Cumulative factor from splits AFTER cf_date."""
        f = 1.0
        for sd, r in split_events:
            if sd > cf_date:
                f *= r
        return f

    for t in sorted(trades, key=lambda x: x["trade_date"]):
        d       = _parse_date(t["trade_date"])
        qty     = float(t.get("qty", 0))
        price   = float(t.get("price", 0))
        charges = float(t.get("charges", 0))
        action  = t["action"].upper()

        if action == "BUY":
            adj      = _split_adj(d)
            adj_qty  = qty * adj
            out      = qty * price + charges
            cashflows.append((d, -out))
            holdings += adj_qty
            totals["total_invested"] += out

        elif action == "SELL":
            adj     = _split_adj(d)
            adj_qty = qty * adj
            inp     = qty * price - charges
            cashflows.append((d, inp))
            holdings -= adj_qty
            totals["total_realised"] += inp

        elif action == "DIVIDEND":
            cashflows.append((d, qty * price))
            totals["total_dividends"] += qty * price

        elif action == "BONUS":
            adj      = _split_adj(d)
            adj_qty  = qty * adj
            holdings += adj_qty
            totals["bonus_shares"] += adj_qty

        elif action == "RIGHTS":
            adj     = _split_adj(d)
            adj_qty = qty * adj
            out     = qty * price + charges
            cashflows.append((d, -out))
            holdings += adj_qty
            totals["total_invested"] += out
            totals["rights_shares"]  += adj_qty
            totals["rights_cost"]    += out

        elif action == "SPLIT":
            ratio = qty if qty > 0 else 1.0
            totals["split_factor"] *= ratio
            if price > 0:
                totals["face_value"] = price

        elif action == "MERGER":
            # If price > 0, it represents the acquisition cost per share received
            # e.g. a cash merger where you receive Rs.X per share held.
            # If price = 0, it's a pure share-swap (no cash outflow here;
            # record a BUY in the acquirer at price=0 for the shares received).
            if price > 0:
                outflow = holdings * price   # total acquisition value
                cashflows.append((d, outflow))   # inflow — you received cash
                totals["total_realised"] += outflow
            holdings = 0.0
            merged   = True

        elif action == "DEMERGER":
            pass  # new shares tracked in the demerged entity's own ledger

    if holdings > 0 and not merged:
        cashflows.append((as_of, holdings * lmp))

    rate = _xirr_newton(cashflows)
    result = {
        "holdings_qty":  round(holdings, 4),
        "current_value": round(holdings * lmp, 2) if not merged else 0.0,
        "xirr_pct":      round(rate * 100, 4) if rate is not None else None,
        "split_factor":  totals["split_factor"],
        "face_value":    totals["face_value"],
    }
    for k in ("total_invested", "total_realised", "total_dividends",
              "bonus_shares", "rights_shares", "rights_cost"):
        result[k] = round(totals[k], 2)
    return result

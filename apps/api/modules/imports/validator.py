import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from storeops_contracts.models import (
    ImportError,
    Kind2,
    Location,
    Product,
    Store,
)

CODE_REGEX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
REVENUE_REGEX = re.compile(r"^\d+\.\d{2}$")

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ROWS = 50000
MAX_ERRORS = 50

SALES_COLUMNS = ["store_code", "sku", "business_date", "units", "revenue", "currency"]
INVENTORY_COLUMNS = ["location_code", "sku", "observed_at", "quantity", "unit"]


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[ImportError]
    row_count: int
    parsed_rows: list[dict[str, Any]]


def validate_csv_content(
    kind: Kind2,
    csv_bytes: bytes,
    workspace_currency: str,
    active_stores_by_code: dict[str, Store],
    active_locations_by_code: dict[str, Location],
    active_products_by_sku: dict[str, Product],
    now: datetime | None = None,
) -> ValidationResult:
    if now is None:
        now = datetime.now(UTC)

    errors: list[ImportError] = []

    def add_error(row: int, field: str, code: str, message: str) -> None:
        if len(errors) < MAX_ERRORS:
            errors.append(ImportError(row=row, field=field, code=code, message=message))

    # 1. Byte size check
    if len(csv_bytes) > MAX_FILE_BYTES:
        add_error(
            1,
            "file",
            "FILE_TOO_LARGE",
            f"File size exceeds maximum {MAX_FILE_BYTES} bytes",
        )
        return ValidationResult(
            is_valid=False, errors=errors, row_count=0, parsed_rows=[]
        )

    # 2. Decode UTF-8 (handling BOM if present)
    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        add_error(1, "file", "ENCODING_ERROR", "CSV file must be UTF-8 encoded")
        return ValidationResult(
            is_valid=False, errors=errors, row_count=0, parsed_rows=[]
        )

    stream = io.StringIO(text)
    reader = csv.reader(stream)

    # 3. Read header
    try:
        header = next(reader)
    except StopIteration:
        add_error(1, "file", "EMPTY_FILE", "File is empty; header row required")
        return ValidationResult(
            is_valid=False, errors=errors, row_count=0, parsed_rows=[]
        )

    expected_cols = SALES_COLUMNS if kind == Kind2.SALES else INVENTORY_COLUMNS
    if header != expected_cols:
        if set(header) != set(expected_cols):
            missing = [c for c in expected_cols if c not in header]
            extra = [c for c in header if c not in expected_cols]
            msg = f"Invalid columns. Expected {expected_cols}."
            if missing:
                msg += f" Missing: {missing}."
            if extra:
                msg += f" Extra: {extra}."
            add_error(1, "header", "COLUMN_MISMATCH", msg)
        else:
            add_error(
                1,
                "header",
                "COLUMN_ORDER_MISMATCH",
                f"Header columns must be in exact order: {expected_cols}",
            )
        return ValidationResult(
            is_valid=False, errors=errors, row_count=0, parsed_rows=[]
        )

    # 4. Iterate data rows
    seen_keys: set[tuple[Any, ...]] = set()
    parsed_rows: list[dict[str, Any]] = []
    row_idx = 0

    today = now.date()
    max_inventory_time = now + timedelta(minutes=5)

    for row_data in reader:
        row_idx += 1
        if row_idx > MAX_ROWS:
            add_error(
                row_idx,
                "file",
                "TOO_MANY_ROWS",
                f"File exceeds maximum allowed {MAX_ROWS} rows",
            )
            break

        if len(row_data) != len(expected_cols):
            add_error(
                row_idx,
                "row",
                "INVALID_COLUMN_COUNT",
                f"Row has {len(row_data)} columns, expected {len(expected_cols)}",
            )
            continue

        row_dict = dict(zip(expected_cols, row_data))

        if kind == Kind2.SALES:
            store_code = row_dict["store_code"].strip()
            sku = row_dict["sku"].strip()
            bdate_str = row_dict["business_date"].strip()
            units_str = row_dict["units"].strip()
            rev_str = row_dict["revenue"].strip()
            curr_str = row_dict["currency"].strip()

            # Logical key uniqueness
            key = (store_code, sku, bdate_str)
            if key in seen_keys:
                add_error(
                    row_idx,
                    "logical_key",
                    "DUPLICATE_KEY",
                    f"Duplicate sales key (store={store_code}, sku={sku}, date={bdate_str})",
                )
            else:
                seen_keys.add(key)

            # Store resolution
            store: Store | None = active_stores_by_code.get(store_code)
            if not CODE_REGEX.match(store_code):
                add_error(
                    row_idx,
                    "store_code",
                    "INVALID_FORMAT",
                    f"Invalid store code format: {store_code}",
                )
            elif not store:
                add_error(
                    row_idx,
                    "store_code",
                    "UNKNOWN_STORE",
                    f"Active store '{store_code}' not found in workspace",
                )

            # SKU resolution
            prod: Product | None = active_products_by_sku.get(sku)
            if not CODE_REGEX.match(sku):
                add_error(
                    row_idx, "sku", "INVALID_FORMAT", f"Invalid SKU format: {sku}"
                )
            elif not prod:
                add_error(
                    row_idx,
                    "sku",
                    "UNKNOWN_SKU",
                    f"Active product '{sku}' not found in workspace",
                )

            # Business date
            parsed_date: date | None = None
            try:
                parsed_date = date.fromisoformat(bdate_str)
                if parsed_date > today:
                    add_error(
                        row_idx,
                        "business_date",
                        "FUTURE_DATE",
                        f"Business date {bdate_str} is in the future",
                    )
            except ValueError:
                add_error(
                    row_idx,
                    "business_date",
                    "INVALID_DATE",
                    f"Invalid date format: {bdate_str}",
                )

            # Units
            parsed_units: int | None = None
            try:
                parsed_units = int(units_str)
                if parsed_units < 0:
                    add_error(
                        row_idx,
                        "units",
                        "NEGATIVE_UNITS",
                        f"Units cannot be negative: {units_str}",
                    )
            except ValueError:
                add_error(
                    row_idx,
                    "units",
                    "INVALID_INTEGER",
                    f"Units must be a non-negative integer: {units_str}",
                )

            # Revenue
            if not REVENUE_REGEX.match(rev_str):
                add_error(
                    row_idx,
                    "revenue",
                    "INVALID_MONEY",
                    f"Revenue must have exactly 2 decimal digits: {rev_str}",
                )

            # Currency
            if curr_str not in ("SGD", "USD", "AUD"):
                add_error(
                    row_idx,
                    "currency",
                    "UNSUPPORTED_CURRENCY",
                    f"Unsupported currency: {curr_str}",
                )
            elif curr_str != workspace_currency:
                add_error(
                    row_idx,
                    "currency",
                    "CURRENCY_MISMATCH",
                    f"Row currency {curr_str} does not match workspace currency {workspace_currency}",
                )

            if (
                store
                and prod
                and parsed_date
                and parsed_units is not None
                and REVENUE_REGEX.match(rev_str)
                and curr_str == workspace_currency
            ):
                parsed_rows.append(
                    {
                        "store_id": store.id,
                        "store_code": store_code,
                        "sku": sku,
                        "business_date": str(parsed_date),
                        "units": parsed_units,
                        "revenue": rev_str,
                        "currency": curr_str,
                    }
                )

        elif kind == Kind2.INVENTORY:
            loc_code = row_dict["location_code"].strip()
            sku = row_dict["sku"].strip()
            obs_str = row_dict["observed_at"].strip()
            qty_str = row_dict["quantity"].strip()
            unit_str = row_dict["unit"].strip()

            # Logical key uniqueness
            key = (loc_code, sku, obs_str)
            if key in seen_keys:
                add_error(
                    row_idx,
                    "logical_key",
                    "DUPLICATE_KEY",
                    f"Duplicate inventory key (location={loc_code}, sku={sku}, observed_at={obs_str})",
                )
            else:
                seen_keys.add(key)

            # Location resolution
            location: Location | None = active_locations_by_code.get(loc_code)
            if not CODE_REGEX.match(loc_code):
                add_error(
                    row_idx,
                    "location_code",
                    "INVALID_FORMAT",
                    f"Invalid location code format: {loc_code}",
                )
            elif not location:
                add_error(
                    row_idx,
                    "location_code",
                    "UNKNOWN_LOCATION",
                    f"Active location '{loc_code}' not found in workspace",
                )

            # SKU resolution
            prod: Product | None = active_products_by_sku.get(sku)
            if not CODE_REGEX.match(sku):
                add_error(
                    row_idx, "sku", "INVALID_FORMAT", f"Invalid SKU format: {sku}"
                )
            elif not prod:
                add_error(
                    row_idx,
                    "sku",
                    "UNKNOWN_SKU",
                    f"Active product '{sku}' not found in workspace",
                )

            # Observed at
            parsed_obs: datetime | None = None
            try:
                # Handle ISO 8601 timestamps (normalize trailing Z for Python 3.11 compatibility)
                normalized_obs = (
                    obs_str.removesuffix("Z") + "+00:00"
                    if obs_str.endswith("Z")
                    else obs_str
                )
                parsed_obs = datetime.fromisoformat(normalized_obs)
                if parsed_obs.tzinfo is None:
                    parsed_obs = parsed_obs.replace(tzinfo=UTC)
                if parsed_obs > max_inventory_time:
                    add_error(
                        row_idx,
                        "observed_at",
                        "FUTURE_TIMESTAMP",
                        f"Observed timestamp {obs_str} exceeds 5-minute future tolerance",
                    )
            except ValueError:
                add_error(
                    row_idx,
                    "observed_at",
                    "INVALID_DATETIME",
                    f"Invalid datetime format: {obs_str}",
                )

            # Quantity
            parsed_qty: int | None = None
            try:
                parsed_qty = int(qty_str)
                if parsed_qty < 0:
                    add_error(
                        row_idx,
                        "quantity",
                        "NEGATIVE_QUANTITY",
                        f"Quantity cannot be negative: {qty_str}",
                    )
            except ValueError:
                add_error(
                    row_idx,
                    "quantity",
                    "INVALID_INTEGER",
                    f"Quantity must be a non-negative integer: {qty_str}",
                )

            # Unit
            if unit_str not in ("UNIT", "CASE"):
                add_error(
                    row_idx,
                    "unit",
                    "INVALID_UNIT",
                    f"Unit must be UNIT or CASE: {unit_str}",
                )

            if (
                location
                and prod
                and parsed_obs
                and parsed_qty is not None
                and unit_str in ("UNIT", "CASE")
            ):
                # Case normalization: if CASE, multiply by product.case_units
                normalized_units = (
                    parsed_qty * prod.case_units if unit_str == "CASE" else parsed_qty
                )
                parsed_rows.append(
                    {
                        "location_id": location.id,
                        "location_code": loc_code,
                        "sku": sku,
                        "observed_at": parsed_obs.isoformat(),
                        "quantity": parsed_qty,
                        "unit": unit_str,
                        "normalized_units": normalized_units,
                    }
                )

    if row_idx == 0:
        add_error(
            1,
            "file",
            "EMPTY_FILE",
            "File contains header only; at least one data row is required",
        )

    is_valid = len(errors) == 0 and row_idx > 0
    return ValidationResult(
        is_valid=is_valid,
        errors=errors,
        row_count=row_idx,
        parsed_rows=parsed_rows if is_valid else [],
    )

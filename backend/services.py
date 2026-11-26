"""Core business services: validation, GST billing, shared carts, split bills, KDS, and admin."""

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import (
    CGST_RATE_BPS,
    DEFAULT_DB_PATH,
    MENU_CATEGORIES,
    ORDER_STATUSES,
    PICKUP_SLOTS,
    SGST_RATE_BPS,
    SPICE_LEVELS,
    SPICE_PREFERENCES,
    TAKEAWAY_PACKAGING_FEE_PAISE,
    VALID_STATUS_TRANSITIONS,
)
from backend.db import db_session
from backend.events import EventBroker


class ServiceError(Exception):
    """Domain/validation exception mapped to clean JSON HTTP error responses."""

    def __init__(self, message: str, status_code: int = 400, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def calculate_bill_breakdown(subtotal_paise: int, order_mode: str) -> dict[str, int]:
    """Compute CGST (2.5%), SGST (2.5%), takeaway packaging fee, and grand total in paise."""
    if subtotal_paise < 0:
        raise ServiceError("Subtotal cannot be negative", 400)
    cgst_paise = (subtotal_paise * CGST_RATE_BPS + 5000) // 10000
    sgst_paise = (subtotal_paise * SGST_RATE_BPS + 5000) // 10000
    packaging_fee_paise = TAKEAWAY_PACKAGING_FEE_PAISE if (order_mode == "takeaway" and subtotal_paise > 0) else 0
    total_paise = subtotal_paise + cgst_paise + sgst_paise + packaging_fee_paise
    return {
        "subtotal_paise": subtotal_paise,
        "cgst_paise": cgst_paise,
        "sgst_paise": sgst_paise,
        "gst_total_paise": cgst_paise + sgst_paise,
        "packaging_fee_paise": packaging_fee_paise,
        "total_paise": total_paise,
    }


def _row_to_menu_item(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    addon_rows = conn.execute(
        """
        SELECT a.id, a.name, a.category, a.price_paise, a.is_veg, a.is_jain, a.is_vegan, a.in_stock,
               mia.is_recommended
        FROM menu_item_addons mia
        JOIN addons a ON a.id = mia.addon_id
        WHERE mia.menu_item_id = ?
        ORDER BY mia.is_recommended DESC, a.category ASC, a.price_paise ASC
        """,
        (row["id"],),
    ).fetchall()
    addons = [
        {
            "id": a["id"],
            "name": a["name"],
            "category": a["category"],
            "price_paise": a["price_paise"],
            "is_veg": bool(a["is_veg"]),
            "is_jain": bool(a["is_jain"]),
            "is_vegan": bool(a["is_vegan"]),
            "in_stock": bool(a["in_stock"]),
            "is_recommended": bool(a["is_recommended"]),
        }
        for a in addon_rows
    ]
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "description": row["description"],
        "price_paise": row["price_paise"],
        "is_veg": bool(row["is_veg"]),
        "is_jain": bool(row["is_jain"]),
        "is_vegan": bool(row["is_vegan"]),
        "spice_level": row["spice_level"],
        "prep_time_mins": row["prep_time_mins"],
        "in_stock": bool(row["in_stock"]),
        "stock_count": row["stock_count"],
        "is_active": bool(row["is_active"]),
        "image_emoji": row["image_emoji"],
        "addons": addons,
    }


def list_menu_items(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    category: str | None = None,
    search: str | None = None,
    veg_only: bool = False,
    jain_only: bool = False,
    vegan_only: bool = False,
    spice_level: str | None = None,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not include_inactive:
        clauses.append("is_active = 1")
    if category and category != "All":
        clauses.append("category = ?")
        params.append(category)
    if search:
        clauses.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ?)")
        pattern = f"%{search.strip().lower()}%"
        params.extend([pattern, pattern])
    if veg_only:
        clauses.append("is_veg = 1")
    if jain_only:
        clauses.append("is_jain = 1")
    if vegan_only:
        clauses.append("is_vegan = 1")
    if spice_level and spice_level != "All":
        if spice_level not in SPICE_LEVELS:
            raise ServiceError(f"Invalid spice_level. Allowed: {', '.join(SPICE_LEVELS)}", 400)
        clauses.append("spice_level = ?")
        params.append(spice_level)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db_session(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM menu_items {where_sql} ORDER BY category ASC, id ASC",
            params,
        ).fetchall()
        return [_row_to_menu_item(conn, r) for r in rows]


def list_all_addons(db_path: Path | str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with db_session(db_path) as conn:
        rows = conn.execute("SELECT * FROM addons ORDER BY category ASC, id ASC").fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "category": r["category"],
                "price_paise": r["price_paise"],
                "is_veg": bool(r["is_veg"]),
                "is_jain": bool(r["is_jain"]),
                "is_vegan": bool(r["is_vegan"]),
                "in_stock": bool(r["in_stock"]),
            }
            for r in rows
        ]


def _validate_menu_payload(payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    if not partial or "name" in payload:
        name = str(payload.get("name", "")).strip()
        if not name or len(name) > 100:
            raise ServiceError("Menu item name must be 1-100 characters", 400)
        cleaned["name"] = name

    if not partial or "category" in payload:
        category = str(payload.get("category", "")).strip()
        if category not in MENU_CATEGORIES:
            raise ServiceError(f"Category must be one of: {', '.join(MENU_CATEGORIES)}", 400)
        cleaned["category"] = category

    if not partial or "description" in payload:
        desc = str(payload.get("description", "")).strip()
        if not desc:
            raise ServiceError("Description is required", 400)
        cleaned["description"] = desc

    if not partial or "price_paise" in payload or "price_rupees" in payload:
        if "price_paise" in payload:
            raw_paise = payload["price_paise"]
            if not isinstance(raw_paise, int) or isinstance(raw_paise, bool) or raw_paise < 0:
                raise ServiceError("price_paise must be a non-negative integer", 400)
            cleaned["price_paise"] = raw_paise
        elif "price_rupees" in payload:
            try:
                rupees = float(payload["price_rupees"])
            except (TypeError, ValueError):
                raise ServiceError("price_rupees must be a valid number", 400) from None
            if rupees < 0:
                raise ServiceError("price_rupees cannot be negative", 400)
            cleaned["price_paise"] = round(rupees * 100)
        else:
            raise ServiceError("price_paise or price_rupees is required", 400)

    if not partial or "spice_level" in payload:
        spice = str(payload.get("spice_level", "Medium")).strip()
        if spice not in SPICE_LEVELS:
            raise ServiceError(f"spice_level must be one of: {', '.join(SPICE_LEVELS)}", 400)
        cleaned["spice_level"] = spice

    if not partial or "prep_time_mins" in payload:
        prep = payload.get("prep_time_mins", 15)
        if not isinstance(prep, int) or isinstance(prep, bool) or prep <= 0 or prep > 180:
            raise ServiceError("prep_time_mins must be between 1 and 180", 400)
        cleaned["prep_time_mins"] = prep

    if not partial or "stock_count" in payload:
        stock = payload.get("stock_count", 30)
        if not isinstance(stock, int) or isinstance(stock, bool) or stock < 0:
            raise ServiceError("stock_count must be a non-negative integer", 400)
        cleaned["stock_count"] = stock

    for flag in ("is_veg", "is_jain", "is_vegan", "in_stock", "is_active"):
        if flag in payload:
            cleaned[flag] = 1 if bool(payload[flag]) else 0
        elif not partial:
            cleaned[flag] = 1 if flag in ("is_veg", "in_stock", "is_active") else 0

    if "image_emoji" in payload:
        emoji = str(payload["image_emoji"]).strip() or "🍽️"
        cleaned["image_emoji"] = emoji[:8]
    elif not partial:
        cleaned["image_emoji"] = "🍽️"

    return cleaned


def create_menu_item(
    payload: dict[str, Any],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    broker: EventBroker | None = None,
) -> dict[str, Any]:
    data = _validate_menu_payload(payload, partial=False)
    now = utc_now()
    with db_session(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO menu_items (
                name, category, description, price_paise, is_veg, is_jain, is_vegan,
                spice_level, prep_time_mins, in_stock, stock_count, is_active, image_emoji, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"],
                data["category"],
                data["description"],
                data["price_paise"],
                data["is_veg"],
                data["is_jain"],
                data["is_vegan"],
                data["spice_level"],
                data["prep_time_mins"],
                data["in_stock"] if data["stock_count"] > 0 else 0,
                data["stock_count"],
                data["is_active"],
                data["image_emoji"],
                now,
            ),
        )
        item_id = int(cur.lastrowid)
        # Attach default customisations/recommendations matching category
        addons = conn.execute("SELECT id, category FROM addons").fetchall()
        for a in addons:
            rec = 1 if a["category"] == "smart_addon" else 0
            conn.execute(
                "INSERT OR IGNORE INTO menu_item_addons (menu_item_id, addon_id, is_recommended) VALUES (?, ?, ?)",
                (item_id, a["id"], rec),
            )
        row = conn.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()
        created = _row_to_menu_item(conn, row)
    if broker:
        broker.publish("menu.updated", {"action": "created", "item": created})
    return created


def update_menu_item(
    item_id: int,
    payload: dict[str, Any],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    broker: EventBroker | None = None,
) -> dict[str, Any]:
    data = _validate_menu_payload(payload, partial=True)
    if not data:
        raise ServiceError("No valid fields provided for update", 400)
    if "stock_count" in data and data["stock_count"] == 0 and "in_stock" not in data:
        data["in_stock"] = 0
    elif "stock_count" in data and data["stock_count"] > 0 and "in_stock" not in data:
        data["in_stock"] = 1

    with db_session(db_path) as conn:
        existing = conn.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()
        if not existing:
            raise ServiceError(f"Menu item {item_id} not found", 404)
        assignments = ", ".join(f"{k} = ?" for k in data.keys())
        conn.execute(
            f"UPDATE menu_items SET {assignments} WHERE id = ?",
            [*data.values(), item_id],
        )
        row = conn.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()
        updated = _row_to_menu_item(conn, row)
    if broker:
        broker.publish("menu.updated", {"action": "updated", "item": updated})
    return updated


def _generate_session_code(order_mode: str, table_number: str | None) -> str:
    suffix = secrets.token_hex(2).upper()
    if order_mode == "dine_in" and table_number:
        clean_table = table_number.replace("-", "")
        return f"DINE-{clean_table}-{suffix}"
    return f"TAKE-{suffix}"


def _build_session_snapshot(conn: sqlite3.Connection, session_id: int) -> dict[str, Any]:
    sess = conn.execute("SELECT * FROM tables_sessions WHERE id = ?", (session_id,)).fetchone()
    if not sess:
        raise ServiceError("Table session not found", 404)

    participants = [
        r["participant_name"]
        for r in conn.execute(
            "SELECT participant_name FROM session_participants WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    ]

    cart_rows = conn.execute(
        """
        SELECT ci.*, m.name AS item_name, m.price_paise, m.category, m.image_emoji,
               m.is_veg, m.is_jain, m.is_vegan, m.in_stock, m.stock_count
        FROM cart_items ci
        JOIN menu_items m ON m.id = ci.menu_item_id
        WHERE ci.session_id = ?
        ORDER BY ci.id ASC
        """,
        (session_id,),
    ).fetchall()

    items: list[dict[str, Any]] = []
    subtotal_paise = 0
    cart_menu_ids = set()
    cart_categories = set()

    for r in cart_rows:
        addons = json.loads(r["selected_addons_json"] or "[]")
        addons_total = sum(int(a.get("price_paise", 0)) for a in addons)
        unit_total = r["price_paise"] + addons_total
        line_total = unit_total * r["quantity"]
        subtotal_paise += line_total
        cart_menu_ids.add(r["menu_item_id"])
        cart_categories.add(r["category"])
        items.append(
            {
                "id": r["id"],
                "menu_item_id": r["menu_item_id"],
                "item_name": r["item_name"],
                "category": r["category"],
                "image_emoji": r["image_emoji"],
                "is_veg": bool(r["is_veg"]),
                "is_jain": bool(r["is_jain"]),
                "is_vegan": bool(r["is_vegan"]),
                "added_by": r["added_by"],
                "quantity": r["quantity"],
                "unit_price_paise": r["price_paise"],
                "addons_total_paise": addons_total,
                "selected_addons": addons,
                "spice_preference": r["spice_preference"],
                "notes": r["notes"],
                "line_total_paise": line_total,
                "in_stock": bool(r["in_stock"]),
            }
        )

    bill = calculate_bill_breakdown(subtotal_paise, sess["order_mode"])

    # Smart cart pairing suggestions based on items currently in the cart
    suggestions: list[dict[str, Any]] = []
    if items:
        target_categories = []
        if "Mains" in cart_categories and "Breads & Rice" not in cart_categories:
            target_categories.append("Breads & Rice")
        if "Beverages" not in cart_categories:
            target_categories.append("Beverages")
        if "Desserts" not in cart_categories:
            target_categories.append("Desserts")
        if not target_categories:
            target_categories = ["Beverages", "Desserts", "Starters"]

        placeholders = ",".join("?" for _ in target_categories)
        cand_rows = conn.execute(
            f"""
            SELECT id, name, category, price_paise, is_veg, is_jain, is_vegan, spice_level, image_emoji
            FROM menu_items
            WHERE is_active = 1 AND in_stock = 1 AND stock_count > 0 AND category IN ({placeholders})
            ORDER BY id ASC
            LIMIT 6
            """,
            target_categories,
        ).fetchall()
        for c in cand_rows:
            if c["id"] not in cart_menu_ids:
                suggestions.append(
                    {
                        "id": c["id"],
                        "name": c["name"],
                        "category": c["category"],
                        "price_paise": c["price_paise"],
                        "is_veg": bool(c["is_veg"]),
                        "is_jain": bool(c["is_jain"]),
                        "is_vegan": bool(c["is_vegan"]),
                        "spice_level": c["spice_level"],
                        "image_emoji": c["image_emoji"],
                        "reason": f"Pairs well with {', '.join(sorted(cart_categories))}",
                    }
                )
            if len(suggestions) >= 3:
                break

    return {
        "id": sess["id"],
        "table_number": sess["table_number"],
        "session_code": sess["session_code"],
        "order_mode": sess["order_mode"],
        "pickup_slot": sess["pickup_slot"],
        "host_name": sess["host_name"],
        "status": sess["status"],
        "created_at": sess["created_at"],
        "participants": participants,
        "cart_items": items,
        "item_count": sum(i["quantity"] for i in items),
        "bill": bill,
        "smart_suggestions": suggestions,
    }


def list_active_sessions(db_path: Path | str = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with db_session(db_path) as conn:
        rows = conn.execute(
            "SELECT id FROM tables_sessions WHERE status = 'active' ORDER BY id DESC"
        ).fetchall()
        return [_build_session_snapshot(conn, r["id"]) for r in rows]


def create_or_join_session(
    payload: dict[str, Any],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    broker: EventBroker | None = None,
) -> dict[str, Any]:
    participant = str(payload.get("participant_name", "")).strip() or "Guest"
    if len(participant) > 50:
        raise ServiceError("participant_name must be 50 characters or fewer", 400)

    session_code = str(payload.get("session_code", "")).strip().upper()
    now = utc_now()

    with db_session(db_path) as conn:
        if session_code:
            sess = conn.execute(
                "SELECT * FROM tables_sessions WHERE UPPER(session_code) = ? AND status = 'active'",
                (session_code,),
            ).fetchone()
            if not sess:
                raise ServiceError(f"Active table session '{session_code}' not found", 404)
            session_id = int(sess["id"])
        else:
            order_mode = str(payload.get("order_mode", "dine_in")).strip()
            if order_mode not in ("dine_in", "takeaway"):
                raise ServiceError("order_mode must be 'dine_in' or 'takeaway'", 400)

            table_number = str(payload.get("table_number", "")).strip().upper() if order_mode == "dine_in" else "TAKEAWAY"
            pickup_slot = str(payload.get("pickup_slot", "")).strip() if order_mode == "takeaway" else None

            if order_mode == "dine_in" and not table_number:
                raise ServiceError("table_number is required for Dine-In", 400)
            if order_mode == "takeaway":
                if not pickup_slot:
                    pickup_slot = PICKUP_SLOTS[0]

            # If joining an existing active dine-in table directly by table_number when reuse_table=True
            if order_mode == "dine_in" and payload.get("reuse_existing", True):
                existing_table = conn.execute(
                    "SELECT id FROM tables_sessions WHERE table_number = ? AND order_mode = 'dine_in' AND status = 'active' ORDER BY id DESC LIMIT 1",
                    (table_number,),
                ).fetchone()
                if existing_table:
                    session_id = int(existing_table["id"])
                else:
                    code = _generate_session_code(order_mode, table_number)
                    cur = conn.execute(
                        """
                        INSERT INTO tables_sessions (table_number, session_code, order_mode, pickup_slot, host_name, status, created_at)
                        VALUES (?, ?, ?, ?, ?, 'active', ?)
                        """,
                        (table_number, code, order_mode, pickup_slot, participant, now),
                    )
                    session_id = int(cur.lastrowid)
            else:
                code = _generate_session_code(order_mode, table_number)
                cur = conn.execute(
                    """
                    INSERT INTO tables_sessions (table_number, session_code, order_mode, pickup_slot, host_name, status, created_at)
                    VALUES (?, ?, ?, ?, ?, 'active', ?)
                    """,
                    (table_number, code, order_mode, pickup_slot, participant, now),
                )
                session_id = int(cur.lastrowid)

        conn.execute(
            "INSERT OR IGNORE INTO session_participants (session_id, participant_name, joined_at) VALUES (?, ?, ?)",
            (session_id, participant, now),
        )
        snapshot = _build_session_snapshot(conn, session_id)

    if broker:
        broker.publish("session.updated", snapshot)
    return snapshot


def get_session(session_id: int, *, db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, Any]:
    with db_session(db_path) as conn:
        return _build_session_snapshot(conn, session_id)


def update_session_mode(
    session_id: int,
    payload: dict[str, Any],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    broker: EventBroker | None = None,
) -> dict[str, Any]:
    order_mode = str(payload.get("order_mode", "")).strip()
    if order_mode not in ("dine_in", "takeaway"):
        raise ServiceError("order_mode must be 'dine_in' or 'takeaway'", 400)
    table_number = str(payload.get("table_number", "")).strip().upper()
    pickup_slot = str(payload.get("pickup_slot", "")).strip()

    if order_mode == "dine_in":
        if not table_number or table_number == "TAKEAWAY":
            raise ServiceError("Please select or enter a valid table number for Dine-In", 400)
        pickup_slot_val = None
    else:
        table_number = "TAKEAWAY"
        pickup_slot_val = pickup_slot or PICKUP_SLOTS[0]

    with db_session(db_path) as conn:
        sess = conn.execute("SELECT status FROM tables_sessions WHERE id = ?", (session_id,)).fetchone()
        if not sess:
            raise ServiceError("Table session not found", 404)
        if sess["status"] != "active":
            raise ServiceError("Cannot modify a closed or checked-out session", 409)
        conn.execute(
            "UPDATE tables_sessions SET order_mode = ?, table_number = ?, pickup_slot = ? WHERE id = ?",
            (order_mode, table_number, pickup_slot_val, session_id),
        )
        snapshot = _build_session_snapshot(conn, session_id)

    if broker:
        broker.publish("session.updated", snapshot)
    return snapshot


def add_cart_item(
    session_id: int,
    payload: dict[str, Any],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    broker: EventBroker | None = None,
) -> dict[str, Any]:
    menu_item_id = payload.get("menu_item_id")
    if not isinstance(menu_item_id, int) or isinstance(menu_item_id, bool):
        raise ServiceError("menu_item_id must be an integer", 400)

    quantity = payload.get("quantity", 1)
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0 or quantity > 50:
        raise ServiceError("quantity must be between 1 and 50", 400)

    added_by = str(payload.get("added_by", "")).strip() or "Guest"
    spice_pref = str(payload.get("spice_preference", "Regular")).strip()
    if spice_pref not in SPICE_PREFERENCES:
        raise ServiceError(f"spice_preference must be one of: {', '.join(SPICE_PREFERENCES)}", 400)
    notes = str(payload.get("notes", "")).strip()[:200]

    addon_ids_raw = payload.get("addon_ids", [])
    if not isinstance(addon_ids_raw, list) or any(not isinstance(x, int) or isinstance(x, bool) for x in addon_ids_raw):
        raise ServiceError("addon_ids must be an array of integer IDs", 400)
    unique_addon_ids = sorted(set(addon_ids_raw))

    now = utc_now()
    with db_session(db_path) as conn:
        sess = conn.execute("SELECT id, status FROM tables_sessions WHERE id = ?", (session_id,)).fetchone()
        if not sess:
            raise ServiceError("Table session not found", 404)
        if sess["status"] != "active":
            raise ServiceError("This table session is no longer active", 409)

        item = conn.execute("SELECT * FROM menu_items WHERE id = ?", (menu_item_id,)).fetchone()
        if not item or not item["is_active"]:
            raise ServiceError("Menu item not found", 404)
        if not item["in_stock"] or item["stock_count"] < quantity:
            raise ServiceError(f"'{item['name']}' is currently out of stock or insufficient quantity", 409)

        selected_addons: list[dict[str, Any]] = []
        if unique_addon_ids:
            placeholders = ",".join("?" for _ in unique_addon_ids)
            addon_rows = conn.execute(
                f"SELECT id, name, price_paise, in_stock FROM addons WHERE id IN ({placeholders})",
                unique_addon_ids,
            ).fetchall()
            if len(addon_rows) != len(unique_addon_ids):
                raise ServiceError("One or more selected add-ons do not exist", 400)
            for a in addon_rows:
                if not a["in_stock"]:
                    raise ServiceError(f"Add-on '{a['name']}' is out of stock", 409)
                selected_addons.append({"id": a["id"], "name": a["name"], "price_paise": a["price_paise"]})

        conn.execute(
            "INSERT OR IGNORE INTO session_participants (session_id, participant_name, joined_at) VALUES (?, ?, ?)",
            (session_id, added_by, now),
        )
        addons_json = json.dumps(selected_addons, sort_keys=True)

        # Merge identical cart item (same menu item, added_by, spice, addons, notes)
        existing_cart = conn.execute(
            """
            SELECT id, quantity FROM cart_items
            WHERE session_id = ? AND menu_item_id = ? AND added_by = ?
              AND spice_preference = ? AND selected_addons_json = ? AND notes = ?
            """,
            (session_id, menu_item_id, added_by, spice_pref, addons_json, notes),
        ).fetchone()
        if existing_cart:
            new_qty = existing_cart["quantity"] + quantity
            if new_qty > item["stock_count"]:
                raise ServiceError(f"Only {item['stock_count']} units of '{item['name']}' available", 409)
            conn.execute("UPDATE cart_items SET quantity = ? WHERE id = ?", (new_qty, existing_cart["id"]))
        else:
            conn.execute(
                """
                INSERT INTO cart_items (
                    session_id, menu_item_id, added_by, quantity,
                    spice_preference, selected_addons_json, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, menu_item_id, added_by, quantity, spice_pref, addons_json, notes, now),
            )

        snapshot = _build_session_snapshot(conn, session_id)

    if broker:
        broker.publish("session.updated", snapshot)
    return snapshot


def update_cart_item(
    session_id: int,
    cart_item_id: int,
    payload: dict[str, Any],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    broker: EventBroker | None = None,
) -> dict[str, Any]:
    quantity = payload.get("quantity")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0 or quantity > 50:
        raise ServiceError("quantity must be between 0 and 50", 400)

    with db_session(db_path) as conn:
        row = conn.execute(
            """
            SELECT ci.id, ci.menu_item_id, m.stock_count, m.in_stock, m.name
            FROM cart_items ci
            JOIN menu_items m ON m.id = ci.menu_item_id
            WHERE ci.id = ? AND ci.session_id = ?
            """,
            (cart_item_id, session_id),
        ).fetchone()
        if not row:
            raise ServiceError("Cart item not found in this session", 404)

        if quantity == 0:
            conn.execute("DELETE FROM cart_items WHERE id = ?", (cart_item_id,))
        else:
            if not row["in_stock"] or quantity > row["stock_count"]:
                raise ServiceError(f"Only {row['stock_count']} units of '{row['name']}' available", 409)
            conn.execute("UPDATE cart_items SET quantity = ? WHERE id = ?", (quantity, cart_item_id))

        snapshot = _build_session_snapshot(conn, session_id)

    if broker:
        broker.publish("session.updated", snapshot)
    return snapshot


def remove_cart_item(
    session_id: int,
    cart_item_id: int,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    broker: EventBroker | None = None,
) -> dict[str, Any]:
    return update_cart_item(session_id, cart_item_id, {"quantity": 0}, db_path=db_path, broker=broker)


def _compute_split_shares(
    split_mode: str,
    bill_total_paise: int,
    subtotal_paise: int,
    order_items: list[dict[str, Any]],
    split_config: dict[str, Any] | None,
    fallback_customer: str,
) -> list[dict[str, Any]]:
    if split_mode == "none":
        return []

    if split_mode == "equal":
        participants = []
        if split_config and isinstance(split_config.get("participants"), list):
            participants = [str(p).strip() for p in split_config["participants"] if str(p).strip()]
        if not participants:
            count = int((split_config or {}).get("split_count", 2))
            if count < 2 or count > 20:
                raise ServiceError("Equal split requires between 2 and 20 people", 400)
            participants = [f"Guest {i + 1}" for i in range(count)]
        if len(participants) < 2:
            raise ServiceError("Equal split requires at least 2 participants", 400)

        base, rem = divmod(bill_total_paise, len(participants))
        shares = []
        for idx, name in enumerate(participants):
            shares.append(
                {
                    "participant_name": name,
                    "amount_paise": base + (1 if idx < rem else 0),
                    "assigned_items": [],
                }
            )
        return shares

    if split_mode == "item_wise":
        # Allocate each order item line_total (and proportional GST/packaging) to its assigned owner
        assignments = (split_config or {}).get("assignments") or {}
        if not isinstance(assignments, dict):
            raise ServiceError("item_wise split requires an 'assignments' mapping", 400)

        owner_subtotals: dict[str, int] = {}
        owner_items: dict[str, list[dict[str, Any]]] = {}
        for item in order_items:
            # Support keying by cart_item_id (pre-order) or order_item id or item index
            key_candidates = [str(item.get("cart_item_id", "")), str(item.get("id", ""))]
            owner = None
            for k in key_candidates:
                if k and k in assignments and str(assignments[k]).strip():
                    owner = str(assignments[k]).strip()
                    break
            if not owner:
                owner = item["added_by"] or fallback_customer
            owner_subtotals[owner] = owner_subtotals.get(owner, 0) + item["line_total_paise"]
            owner_items.setdefault(owner, []).append(
                {"item_name": item["item_name"], "quantity": item["quantity"], "line_total_paise": item["line_total_paise"]}
            )

        names = list(owner_subtotals.keys())
        if not names:
            raise ServiceError("No items available to split", 400)

        extra_charges = bill_total_paise - subtotal_paise
        shares = []
        allocated_extra = 0
        for idx, name in enumerate(names):
            part_sub = owner_subtotals[name]
            if idx == len(names) - 1:
                part_extra = extra_charges - allocated_extra
            else:
                part_extra = (extra_charges * part_sub) // subtotal_paise if subtotal_paise > 0 else 0
                allocated_extra += part_extra
            shares.append(
                {
                    "participant_name": name,
                    "amount_paise": part_sub + part_extra,
                    "assigned_items": owner_items[name],
                }
            )
        return shares

    raise ServiceError("split_mode must be 'none', 'equal', or 'item_wise'", 400)


def _fetch_order_dict(conn: sqlite3.Connection, order_id: int) -> dict[str, Any]:
    o = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not o:
        raise ServiceError("Order not found", 404)

    items_rows = conn.execute(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY id ASC",
        (order_id,),
    ).fetchall()
    shares_rows = conn.execute(
        "SELECT * FROM split_shares WHERE order_id = ? ORDER BY id ASC",
        (order_id,),
    ).fetchall()

    items = [
        {
            "id": r["id"],
            "menu_item_id": r["menu_item_id"],
            "item_name": r["item_name"],
            "added_by": r["added_by"],
            "quantity": r["quantity"],
            "unit_price_paise": r["unit_price_paise"],
            "addons_total_paise": r["addons_total_paise"],
            "selected_addons": json.loads(r["selected_addons_json"] or "[]"),
            "spice_preference": r["spice_preference"],
            "notes": r["notes"],
            "line_total_paise": r["line_total_paise"],
        }
        for r in items_rows
    ]
    shares = [
        {
            "id": s["id"],
            "participant_name": s["participant_name"],
            "amount_paise": s["amount_paise"],
            "assigned_items": json.loads(s["assigned_items_json"] or "[]"),
            "is_paid": bool(s["is_paid"]),
            "paid_at": s["paid_at"],
        }
        for s in shares_rows
    ]
    return {
        "id": o["id"],
        "order_number": o["order_number"],
        "session_id": o["session_id"],
        "order_mode": o["order_mode"],
        "table_number": o["table_number"],
        "pickup_slot": o["pickup_slot"],
        "customer_name": o["customer_name"],
        "status": o["status"],
        "subtotal_paise": o["subtotal_paise"],
        "cgst_paise": o["cgst_paise"],
        "sgst_paise": o["sgst_paise"],
        "gst_total_paise": o["cgst_paise"] + o["sgst_paise"],
        "packaging_fee_paise": o["packaging_fee_paise"],
        "total_paise": o["total_paise"],
        "split_mode": o["split_mode"],
        "special_instructions": o["special_instructions"],
        "created_at": o["created_at"],
        "updated_at": o["updated_at"],
        "items": items,
        "split_shares": shares,
    }


def checkout_session(
    session_id: int,
    payload: dict[str, Any],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    broker: EventBroker | None = None,
) -> dict[str, Any]:
    split_mode = str(payload.get("split_mode", "none")).strip()
    if split_mode not in ("none", "equal", "item_wise"):
        raise ServiceError("split_mode must be 'none', 'equal', or 'item_wise'", 400)

    special_instructions = str(payload.get("special_instructions", "")).strip()[:300]
    customer_name = str(payload.get("customer_name", "")).strip()
    split_config = payload.get("split_config")
    now = utc_now()

    with db_session(db_path) as conn:
        snapshot = _build_session_snapshot(conn, session_id)
        if snapshot["status"] != "active":
            raise ServiceError("Session has already been checked out", 409)
        if not snapshot["cart_items"]:
            raise ServiceError("Cannot place order with an empty cart", 400)

        # Verify stock before committing and deduct stock atomically
        for ci in snapshot["cart_items"]:
            m_row = conn.execute(
                "SELECT id, name, in_stock, stock_count FROM menu_items WHERE id = ?",
                (ci["menu_item_id"],),
            ).fetchone()
            if not m_row or not m_row["in_stock"] or m_row["stock_count"] < ci["quantity"]:
                raise ServiceError(f"Insufficient stock for '{ci['item_name']}'", 409)

        for ci in snapshot["cart_items"]:
            conn.execute(
                """
                UPDATE menu_items
                SET stock_count = stock_count - ?,
                    in_stock = CASE WHEN (stock_count - ?) <= 0 THEN 0 ELSE in_stock END
                WHERE id = ?
                """,
                (ci["quantity"], ci["quantity"], ci["menu_item_id"]),
            )

        final_customer = customer_name or ", ".join(snapshot["participants"]) or snapshot["host_name"]
        bill = snapshot["bill"]

        # Generate readable sequential order number
        max_id_row = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM orders").fetchone()
        order_number = f"ORD-{1001 + int(max_id_row['max_id'])}"

        shares = _compute_split_shares(
            split_mode,
            bill["total_paise"],
            bill["subtotal_paise"],
            [
                {
                    "cart_item_id": ci["id"],
                    "item_name": ci["item_name"],
                    "quantity": ci["quantity"],
                    "added_by": ci["added_by"],
                    "line_total_paise": ci["line_total_paise"],
                }
                for ci in snapshot["cart_items"]
            ],
            split_config,
            final_customer,
        )

        cur = conn.execute(
            """
            INSERT INTO orders (
                order_number, session_id, order_mode, table_number, pickup_slot,
                customer_name, status, subtotal_paise, cgst_paise, sgst_paise,
                packaging_fee_paise, total_paise, split_mode, special_instructions,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'Queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_number,
                session_id,
                snapshot["order_mode"],
                snapshot["table_number"] if snapshot["order_mode"] == "dine_in" else None,
                snapshot["pickup_slot"] if snapshot["order_mode"] == "takeaway" else None,
                final_customer,
                bill["subtotal_paise"],
                bill["cgst_paise"],
                bill["sgst_paise"],
                bill["packaging_fee_paise"],
                bill["total_paise"],
                split_mode,
                special_instructions,
                now,
                now,
            ),
        )
        order_id = int(cur.lastrowid)

        for ci in snapshot["cart_items"]:
            conn.execute(
                """
                INSERT INTO order_items (
                    order_id, menu_item_id, item_name, added_by, quantity,
                    unit_price_paise, addons_total_paise, selected_addons_json,
                    spice_preference, notes, line_total_paise
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    ci["menu_item_id"],
                    ci["item_name"],
                    ci["added_by"],
                    ci["quantity"],
                    ci["unit_price_paise"],
                    ci["addons_total_paise"],
                    json.dumps(ci["selected_addons"]),
                    ci["spice_preference"],
                    ci["notes"],
                    ci["line_total_paise"],
                ),
            )

        for s in shares:
            conn.execute(
                """
                INSERT INTO split_shares (order_id, participant_name, amount_paise, assigned_items_json, is_paid, paid_at)
                VALUES (?, ?, ?, ?, 0, NULL)
                """,
                (order_id, s["participant_name"], s["amount_paise"], json.dumps(s["assigned_items"])),
            )

        # Clear cart items and create fresh empty cart or mark session checked out
        # Keeping session checked_out allows user to track order and start a fresh round if needed
        conn.execute("DELETE FROM cart_items WHERE session_id = ?", (session_id,))
        conn.execute("UPDATE tables_sessions SET status = 'checked_out' WHERE id = ?", (session_id,))

        order_dict = _fetch_order_dict(conn, order_id)

    if broker:
        broker.publish("order.created", order_dict)
        broker.publish("session.checked_out", {"session_id": session_id, "order": order_dict})
    return order_dict


def list_orders(
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    status: str | None = None,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status and status != "All":
        if status not in ORDER_STATUSES:
            raise ServiceError(f"Invalid status. Allowed: {', '.join(ORDER_STATUSES)}", 400)
        clauses.append("status = ?")
        params.append(status)
    elif active_only:
        clauses.append("status IN ('Queued', 'Preparing', 'Ready')")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db_session(db_path) as conn:
        rows = conn.execute(
            f"SELECT id FROM orders {where_sql} ORDER BY id DESC",
            params,
        ).fetchall()
        return [_fetch_order_dict(conn, r["id"]) for r in rows]


def get_order(order_id: int, *, db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, Any]:
    with db_session(db_path) as conn:
        return _fetch_order_dict(conn, order_id)


def update_order_status(
    order_id: int,
    new_status: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    broker: EventBroker | None = None,
) -> dict[str, Any]:
    if new_status not in ORDER_STATUSES:
        raise ServiceError(f"Invalid status '{new_status}'", 400)
    now = utc_now()
    with db_session(db_path) as conn:
        row = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            raise ServiceError("Order not found", 404)
        current_status = row["status"]
        allowed = VALID_STATUS_TRANSITIONS.get(current_status, ())
        if new_status not in allowed:
            raise ServiceError(
                f"Cannot transition order from '{current_status}' to '{new_status}'. Allowed: {', '.join(allowed) or 'none'}",
                409,
            )
        conn.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, order_id),
        )
        updated = _fetch_order_dict(conn, order_id)

    if broker:
        broker.publish("order.updated", updated)
    return updated


def split_existing_order(
    order_id: int,
    payload: dict[str, Any],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    broker: EventBroker | None = None,
) -> dict[str, Any]:
    split_mode = str(payload.get("split_mode", "equal")).strip()
    if split_mode not in ("equal", "item_wise"):
        raise ServiceError("split_mode must be 'equal' or 'item_wise'", 400)
    split_config = payload.get("split_config") or {}

    with db_session(db_path) as conn:
        order = _fetch_order_dict(conn, order_id)
        if order["status"] == "Cancelled":
            raise ServiceError("Cannot split a cancelled order", 409)

        shares = _compute_split_shares(
            split_mode,
            order["total_paise"],
            order["subtotal_paise"],
            order["items"],
            split_config,
            order["customer_name"],
        )
        conn.execute("DELETE FROM split_shares WHERE order_id = ?", (order_id,))
        for s in shares:
            conn.execute(
                """
                INSERT INTO split_shares (order_id, participant_name, amount_paise, assigned_items_json, is_paid, paid_at)
                VALUES (?, ?, ?, ?, 0, NULL)
                """,
                (order_id, s["participant_name"], s["amount_paise"], json.dumps(s["assigned_items"])),
            )
        conn.execute(
            "UPDATE orders SET split_mode = ?, updated_at = ? WHERE id = ?",
            (split_mode, utc_now(), order_id),
        )
        updated = _fetch_order_dict(conn, order_id)

    if broker:
        broker.publish("order.updated", updated)
    return updated


def toggle_split_share_paid(
    order_id: int,
    share_id: int,
    is_paid: bool,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    broker: EventBroker | None = None,
) -> dict[str, Any]:
    now = utc_now() if is_paid else None
    with db_session(db_path) as conn:
        share = conn.execute(
            "SELECT id FROM split_shares WHERE id = ? AND order_id = ?",
            (share_id, order_id),
        ).fetchone()
        if not share:
            raise ServiceError("Split share not found for this order", 404)
        conn.execute(
            "UPDATE split_shares SET is_paid = ?, paid_at = ? WHERE id = ?",
            (1 if is_paid else 0, now, share_id),
        )
        updated = _fetch_order_dict(conn, order_id)

    if broker:
        broker.publish("order.updated", updated)
    return updated


def get_admin_metrics(db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, Any]:
    with db_session(db_path) as conn:
        summary = conn.execute(
            """
            SELECT
                COUNT(*) AS total_orders,
                COALESCE(SUM(CASE WHEN status != 'Cancelled' THEN total_paise ELSE 0 END), 0) AS total_revenue_paise,
                COALESCE(SUM(CASE WHEN status IN ('Queued', 'Preparing', 'Ready') THEN 1 ELSE 0 END), 0) AS active_kitchen_orders,
                COALESCE(SUM(CASE WHEN order_mode = 'dine_in' AND status != 'Cancelled' THEN 1 ELSE 0 END), 0) AS dine_in_orders,
                COALESCE(SUM(CASE WHEN order_mode = 'takeaway' AND status != 'Cancelled' THEN 1 ELSE 0 END), 0) AS takeaway_orders
            FROM orders
            """
        ).fetchone()

        active_sessions = conn.execute(
            "SELECT COUNT(*) FROM tables_sessions WHERE status = 'active'"
        ).fetchone()[0]

        low_stock_count = conn.execute(
            "SELECT COUNT(*) FROM menu_items WHERE is_active = 1 AND (in_stock = 0 OR stock_count <= 5)"
        ).fetchone()[0]

        top_dishes_rows = conn.execute(
            """
            SELECT oi.item_name,
                   SUM(oi.quantity) AS units_sold,
                   SUM(oi.line_total_paise) AS revenue_paise
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE o.status != 'Cancelled'
            GROUP BY oi.item_name
            ORDER BY units_sold DESC, revenue_paise DESC
            LIMIT 6
            """
        ).fetchall()

        total_orders = int(summary["total_orders"])
        total_revenue = int(summary["total_revenue_paise"])
        avg_order_value = (total_revenue // total_orders) if total_orders > 0 else 0

        return {
            "total_orders": total_orders,
            "total_revenue_paise": total_revenue,
            "avg_order_value_paise": avg_order_value,
            "active_kitchen_orders": int(summary["active_kitchen_orders"]),
            "active_sessions": int(active_sessions),
            "dine_in_orders": int(summary["dine_in_orders"]),
            "takeaway_orders": int(summary["takeaway_orders"]),
            "low_stock_count": int(low_stock_count),
            "top_dishes": [
                {
                    "item_name": r["item_name"],
                    "units_sold": int(r["units_sold"]),
                    "revenue_paise": int(r["revenue_paise"]),
                }
                for r in top_dishes_rows
            ],
        }

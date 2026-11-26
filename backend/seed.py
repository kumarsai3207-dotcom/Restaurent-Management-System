"""Seed data for the Restaurant Ordering System (Indian menu, add-ons, sessions, orders)."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import DEFAULT_DB_PATH
from backend.db import db_session, init_schema

USERS_SEED = [
    ("Aarav Sharma", "customer", None),
    ("Priya Nair", "customer", None),
    ("Chef Vikram", "kitchen", "1234"),
    ("Meera Kapoor", "admin", "9999"),
]

# (name, category, price_paise, is_veg, is_jain, is_vegan, spice_level, prep_time_mins, stock_count, emoji, description)
MENU_SEED = [
    (
        "Paneer Tikka Angara",
        "Starters",
        32000,
        1,
        0,
        0,
        "Hot",
        16,
        35,
        "🧀",
        "Char-grilled cottage cheese marinated in hung curd, Kashmiri chilli, and roasted ajwain.",
    ),
    (
        "Crispy Corn & Pepper Salt",
        "Starters",
        24000,
        1,
        1,
        1,
        "Medium",
        12,
        40,
        "🌽",
        "Golden wok-tossed sweet corn kernels with crushed black pepper, curry leaves, and lime (Jain-friendly).",
    ),
    (
        "Hara Bhara Kebab",
        "Starters",
        26000,
        1,
        1,
        1,
        "Mild",
        14,
        30,
        "🥬",
        "Spinach, green peas, and roasted chana patties served with mint-coriander chutney.",
    ),
    (
        "Tandoori Chicken Half",
        "Starters",
        38000,
        0,
        0,
        0,
        "Hot",
        20,
        24,
        "🍗",
        "Bone-in chicken marinated overnight in spiced yogurt and roasted in a clay tandoor.",
    ),
    (
        "Dal Tadka Dhaba Style",
        "Mains",
        27000,
        1,
        1,
        1,
        "Mild",
        14,
        50,
        "🍲",
        "Slow-simmered yellow toor & moong lentils finished with cumin, hing, and tomato tempering.",
    ),
    (
        "Paneer Butter Masala",
        "Mains",
        36000,
        1,
        0,
        0,
        "Mild",
        18,
        38,
        "🍛",
        "Soft paneer cubes in velvety tomato-cashew makhani gravy with kasuri methi.",
    ),
    (
        "Jain Kadai Paneer",
        "Mains",
        37000,
        1,
        1,
        0,
        "Medium",
        18,
        28,
        "🫑",
        "No onion, no garlic paneer tossed with bell peppers and freshly pounded kadai spices.",
    ),
    (
        "Chana Masala Amritsari",
        "Mains",
        29000,
        1,
        0,
        1,
        "Medium",
        15,
        35,
        "🫘",
        "Hearty chickpeas simmered in roasted pomegranate-anardana and ginger-coriander masala.",
    ),
    (
        "Butter Chicken Classic",
        "Mains",
        42000,
        0,
        0,
        0,
        "Mild",
        20,
        30,
        "🍖",
        "Smoky tandoori chicken tikka folded into rich spiced tomato-butter gravy.",
    ),
    (
        "Kolhapuri Veg Handi",
        "Mains",
        33000,
        1,
        0,
        1,
        "Extra Hot",
        18,
        25,
        "🌶️",
        "Seasonal vegetables cooked in fiery roasted coconut, sesame, and Lavangi chilli masala.",
    ),
    (
        "Garlic Butter Naan",
        "Breads & Rice",
        8500,
        1,
        0,
        0,
        "None",
        8,
        80,
        "🫓",
        "Crisp-chewy tandoor-baked flatbread brushed with roasted garlic and cultured butter.",
    ),
    (
        "Tandoori Roti (Whole Wheat)",
        "Breads & Rice",
        4500,
        1,
        1,
        1,
        "None",
        6,
        100,
        "🫓",
        "100% whole wheat tandoori roti baked crisp without dairy or onion/garlic.",
    ),
    (
        "Subz Dum Biryani",
        "Breads & Rice",
        35000,
        1,
        0,
        1,
        "Medium",
        22,
        26,
        "🍚",
        "Aged basmati rice layered with saffron, mint, fried onions, and spiced vegetables.",
    ),
    (
        "Hyderabadi Chicken Dum Biryani",
        "Breads & Rice",
        44000,
        0,
        0,
        0,
        "Hot",
        24,
        22,
        "🍛",
        "Kacchi-style basmati dum biryani sealed with caramelized onions, saffron, and mint.",
    ),
    (
        "Masala Chaas",
        "Beverages",
        9000,
        1,
        1,
        0,
        "Mild",
        5,
        60,
        "🥛",
        "Chilled churned buttermilk spiced with roasted cumin, black salt, and fresh coriander.",
    ),
    (
        "Fresh Nimbu Soda (Sweet & Salted)",
        "Beverages",
        8000,
        1,
        1,
        1,
        "None",
        4,
        60,
        "🍋",
        "Sparkling chilled lime cooler with rock salt and cane sugar syrup.",
    ),
    (
        "Mango Lassi",
        "Beverages",
        14000,
        1,
        1,
        0,
        "None",
        5,
        40,
        "🥭",
        "Thick Alphonso mango yogurt smoothie topped with cardamom and pistachios.",
    ),
    (
        "Warm Gulab Jamun (2 pcs)",
        "Desserts",
        13000,
        1,
        1,
        0,
        "None",
        6,
        45,
        "🍡",
        "Golden khoya dumplings steeped in warm rose-cardamom sugar syrup.",
    ),
    (
        "Kesar Pista Kulfi",
        "Desserts",
        16000,
        1,
        1,
        0,
        "None",
        5,
        32,
        "🍨",
        "Traditional slow-reduced saffron and pistachio matka kulfi.",
    ),
]

# (name, category, price_paise, is_veg, is_jain, is_vegan)
ADDONS_SEED = [
    ("Jain Prep (No Onion / Garlic)", "customisation", 0, 1, 1, 1),
    ("Extra Desi Ghee Drizzle", "customisation", 3500, 1, 1, 0),
    ("Extra Paneer / Protein Portion", "customisation", 7500, 1, 1, 0),
    ("Less Oil & Mild Seasoning", "customisation", 0, 1, 1, 1),
    ("Mint-Coriander Chutney Dip", "smart_addon", 2500, 1, 1, 1),
    ("Boondi Raita Bowl", "smart_addon", 7000, 1, 1, 0),
    ("Masala Papad (Roasted)", "smart_addon", 4500, 1, 1, 1),
    ("Single Garlic Naan Pairing", "smart_addon", 8000, 1, 0, 0),
    ("Masala Chaas Glass", "smart_addon", 8500, 1, 1, 0),
    ("Warm Gulab Jamun (1 pc)", "smart_addon", 6500, 1, 1, 0),
]

CATEGORY_RECOMMENDATIONS = {
    "Starters": ["Mint-Coriander Chutney Dip", "Masala Papad (Roasted)", "Masala Chaas Glass"],
    "Mains": ["Single Garlic Naan Pairing", "Boondi Raita Bowl", "Extra Desi Ghee Drizzle", "Masala Chaas Glass"],
    "Breads & Rice": ["Boondi Raita Bowl", "Masala Papad (Roasted)", "Warm Gulab Jamun (1 pc)"],
    "Beverages": ["Masala Papad (Roasted)", "Warm Gulab Jamun (1 pc)"],
    "Desserts": ["Masala Chaas Glass"],
}


def seed_database(db_path: Path | str = DEFAULT_DB_PATH, force: bool = False) -> bool:
    """Populate initial restaurant data if empty (or wipe and reseed when force=True)."""
    init_schema(db_path)
    now = datetime.now(timezone.utc)

    with db_session(db_path) as conn:
        if force:
            for tbl in (
                "split_shares",
                "order_items",
                "orders",
                "cart_items",
                "menu_item_addons",
                "addons",
                "menu_items",
                "session_participants",
                "tables_sessions",
                "users",
            ):
                conn.execute(f"DELETE FROM {tbl}")
            conn.execute("DELETE FROM sqlite_sequence")

        existing_menu = conn.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
        if existing_menu > 0 and not force:
            return False

        for name, role, pin in USERS_SEED:
            conn.execute(
                "INSERT INTO users (name, role, pin_code, created_at) VALUES (?, ?, ?, ?)",
                (name, role, pin, now.isoformat()),
            )

        menu_ids: dict[str, tuple[int, str, int]] = {}
        for item in MENU_SEED:
            (
                name,
                category,
                price_paise,
                is_veg,
                is_jain,
                is_vegan,
                spice_level,
                prep_mins,
                stock,
                emoji,
                desc,
            ) = item
            cur = conn.execute(
                """
                INSERT INTO menu_items (
                    name, category, description, price_paise, is_veg, is_jain, is_vegan,
                    spice_level, prep_time_mins, in_stock, stock_count, is_active, image_emoji, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1, ?, ?)
                """,
                (
                    name,
                    category,
                    desc,
                    price_paise,
                    is_veg,
                    is_jain,
                    is_vegan,
                    spice_level,
                    prep_mins,
                    stock,
                    emoji,
                    now.isoformat(),
                ),
            )
            menu_ids[name] = (int(cur.lastrowid), category, price_paise)

        addon_ids: dict[str, int] = {}
        for name, cat, price_paise, is_veg, is_jain, is_vegan in ADDONS_SEED:
            cur = conn.execute(
                """
                INSERT INTO addons (name, category, price_paise, is_veg, is_jain, is_vegan, in_stock)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (name, cat, price_paise, is_veg, is_jain, is_vegan),
            )
            addon_ids[name] = int(cur.lastrowid)

        # Link customisations + recommended smart add-ons per menu item
        customisation_names = [a[0] for a in ADDONS_SEED if a[1] == "customisation"]
        for item_name, (m_id, category, _) in menu_ids.items():
            for c_name in customisation_names:
                if category in ("Beverages", "Desserts") and c_name in (
                    "Jain Prep (No Onion / Garlic)",
                    "Extra Paneer / Protein Portion",
                    "Less Oil & Mild Seasoning",
                ):
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO menu_item_addons (menu_item_id, addon_id, is_recommended) VALUES (?, ?, 0)",
                    (m_id, addon_ids[c_name]),
                )
            for rec_name in CATEGORY_RECOMMENDATIONS.get(category, []):
                conn.execute(
                    "INSERT OR IGNORE INTO menu_item_addons (menu_item_id, addon_id, is_recommended) VALUES (?, ?, 1)",
                    (m_id, addon_ids[rec_name]),
                )

        # Create sample active shared table session (T-04) with 2 participants and shared cart items
        t4_cur = conn.execute(
            """
            INSERT INTO tables_sessions (table_number, session_code, order_mode, pickup_slot, host_name, status, created_at)
            VALUES ('T-04', 'DINE-T04', 'dine_in', NULL, 'Aarav', 'active', ?)
            """,
            ((now - timedelta(minutes=18)).isoformat(),),
        )
        t4_id = int(t4_cur.lastrowid)
        for participant in ("Aarav", "Riya"):
            conn.execute(
                "INSERT INTO session_participants (session_id, participant_name, joined_at) VALUES (?, ?, ?)",
                (t4_id, participant, (now - timedelta(minutes=16)).isoformat()),
            )

        # Pre-populate shared cart on T-04 so joining DINE-T04 immediately demonstrates shared cart
        paneer_id, _, _ = menu_ids["Paneer Butter Masala"]
        naan_id, _, _ = menu_ids["Garlic Butter Naan"]
        raita_addon_id = addon_ids["Boondi Raita Bowl"]
        conn.execute(
            """
            INSERT INTO cart_items (session_id, menu_item_id, added_by, quantity, spice_preference, selected_addons_json, notes, created_at)
            VALUES (?, ?, 'Aarav', 1, 'Regular', ?, 'Medium rich gravy', ?)
            """,
            (
                t4_id,
                paneer_id,
                json.dumps([{"id": raita_addon_id, "name": "Boondi Raita Bowl", "price_paise": 7000}]),
                (now - timedelta(minutes=10)).isoformat(),
            ),
        )
        conn.execute(
            """
            INSERT INTO cart_items (session_id, menu_item_id, added_by, quantity, spice_preference, selected_addons_json, notes, created_at)
            VALUES (?, ?, 'Riya', 2, 'Regular', '[]', 'Extra crisp', ?)
            """,
            (t4_id, naan_id, (now - timedelta(minutes=8)).isoformat()),
        )

        # Sample historical & live orders across Queued, Preparing, Ready, Served
        sample_orders = [
            {
                "order_number": "ORD-1001",
                "order_mode": "dine_in",
                "table_number": "T-02",
                "pickup_slot": None,
                "customer_name": "Karan & Sneha",
                "status": "Served",
                "minutes_ago": 52,
                "split_mode": "equal",
                "items": [
                    ("Dal Tadka Dhaba Style", "Karan", 1, 27000, [], "Mild", ""),
                    ("Jain Kadai Paneer", "Sneha", 1, 37000, [], "No Spice / Jain", "Strictly Jain"),
                    ("Tandoori Roti (Whole Wheat)", "Karan", 4, 4500, [], "Regular", ""),
                    ("Masala Chaas", "Sneha", 2, 9000, [], "Mild", ""),
                ],
                "shares": [("Karan", 2), ("Sneha", 2)],
            },
            {
                "order_number": "ORD-1002",
                "order_mode": "takeaway",
                "table_number": None,
                "pickup_slot": "07:30 PM - 07:45 PM",
                "customer_name": "Ananya Iyer",
                "status": "Ready",
                "minutes_ago": 21,
                "split_mode": "none",
                "items": [
                    ("Hyderabadi Chicken Dum Biryani", "Ananya", 2, 44000, [{"id": raita_addon_id, "name": "Boondi Raita Bowl", "price_paise": 7000}], "Spicy", "Pack raita separately"),
                    ("Warm Gulab Jamun (2 pcs)", "Ananya", 1, 13000, [], "Regular", ""),
                ],
                "shares": [],
            },
            {
                "order_number": "ORD-1003",
                "order_mode": "dine_in",
                "table_number": "T-07",
                "pickup_slot": None,
                "customer_name": "Rohan & Friends",
                "status": "Preparing",
                "minutes_ago": 11,
                "split_mode": "item_wise",
                "items": [
                    ("Paneer Tikka Angara", "Rohan", 1, 32000, [], "Extra Spicy", "Charred well"),
                    ("Butter Chicken Classic", "Dev", 1, 42000, [], "Regular", ""),
                    ("Garlic Butter Naan", "Dev", 3, 8500, [], "Regular", ""),
                    ("Mango Lassi", "Neha", 2, 14000, [], "Regular", "Less ice"),
                ],
                "shares": [],
            },
            {
                "order_number": "ORD-1004",
                "order_mode": "dine_in",
                "table_number": "T-01",
                "pickup_slot": None,
                "customer_name": "Mehta Family",
                "status": "Queued",
                "minutes_ago": 3,
                "split_mode": "none",
                "items": [
                    ("Crispy Corn & Pepper Salt", "Mehta Family", 1, 24000, [], "No Spice / Jain", "Jain prep"),
                    ("Subz Dum Biryani", "Mehta Family", 1, 35000, [], "Mild", ""),
                    ("Fresh Nimbu Soda (Sweet & Salted)", "Mehta Family", 2, 8000, [], "Regular", ""),
                ],
                "shares": [],
            },
        ]

        for o in sample_orders:
            created = (now - timedelta(minutes=o["minutes_ago"])).isoformat()
            updated = (now - timedelta(minutes=max(1, o["minutes_ago"] - 4))).isoformat()
            subtotal = 0
            computed_items = []
            for item_name, added_by, qty, unit_price, addons, spice_pref, notes in o["items"]:
                m_id = menu_ids[item_name][0]
                addons_total = sum(a["price_paise"] for a in addons)
                line_total = (unit_price + addons_total) * qty
                subtotal += line_total
                computed_items.append(
                    (
                        m_id,
                        item_name,
                        added_by,
                        qty,
                        unit_price,
                        addons_total,
                        json.dumps(addons),
                        spice_pref,
                        notes,
                        line_total,
                    )
                )

            cgst = (subtotal * 250 + 5000) // 10000
            sgst = (subtotal * 250 + 5000) // 10000
            pkg_fee = 2000 if o["order_mode"] == "takeaway" else 0
            total = subtotal + cgst + sgst + pkg_fee

            o_cur = conn.execute(
                """
                INSERT INTO orders (
                    order_number, session_id, order_mode, table_number, pickup_slot,
                    customer_name, status, subtotal_paise, cgst_paise, sgst_paise,
                    packaging_fee_paise, total_paise, split_mode, special_instructions,
                    created_at, updated_at
                ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
                """,
                (
                    o["order_number"],
                    o["order_mode"],
                    o["table_number"],
                    o["pickup_slot"],
                    o["customer_name"],
                    o["status"],
                    subtotal,
                    cgst,
                    sgst,
                    pkg_fee,
                    total,
                    o["split_mode"],
                    created,
                    updated,
                ),
            )
            order_id = int(o_cur.lastrowid)
            for row_item in computed_items:
                conn.execute(
                    """
                    INSERT INTO order_items (
                        order_id, menu_item_id, item_name, added_by, quantity,
                        unit_price_paise, addons_total_paise, selected_addons_json,
                        spice_preference, notes, line_total_paise
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (order_id, *row_item),
                )

            if o["order_number"] == "ORD-1001":
                half = total // 2
                rem = total - half
                conn.execute(
                    "INSERT INTO split_shares (order_id, participant_name, amount_paise, assigned_items_json, is_paid, paid_at) VALUES (?, 'Karan', ?, '[]', 1, ?)",
                    (order_id, half + rem, updated),
                )
                conn.execute(
                    "INSERT INTO split_shares (order_id, participant_name, amount_paise, assigned_items_json, is_paid, paid_at) VALUES (?, 'Sneha', ?, '[]', 1, ?)",
                    (order_id, half, updated),
                )

    return True

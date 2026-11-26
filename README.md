# SpiceRoute — Full-Stack Restaurant Ordering & Live KDS System

A self-contained full-stack **Restaurant Ordering, Shared Table Cart, Bill Splitting, and Live Kitchen Display System (KDS)** built with **Python 3 (Standard Library + SQLite)** and **Vanilla HTML5/CSS3/ES6 Modules** with **Server-Sent Events (SSE)** real-time synchronization and automatic polling fallback.

---

## Features Implemented

### 1. Customer View
- **Menu Browsing & Smart Filters**: Search by dish/ingredient, filter by Category (`Starters`, `Mains`, `Breads & Rice`, `Beverages`, `Desserts`), Dietary tags (`Pure Veg`, `Jain`, `Vegan`), and `Spice Level` (`None`, `Mild`, `Medium`, `Hot`, `Extra Hot`).
- **Customisations & Smart Add-Ons**:Dish modal with quantity stepper, spice preference (`No Spice / Jain`, `Mild`, `Regular`, `Spicy`, `Extra Spicy`), customisations (`Jain Prep`, `Extra Desi Ghee`, `Extra Paneer`), dish-paired smart add-ons (`Boondi Raita`, `Single Garlic Naan`, `Masala Chaas`), and chef notes. Plus **cart-level smart pairing suggestions** based on items in the cart.
- **Dine-In & Takeaway Modes**: Switch between **Dine-In** (select/enter table `T-01`..`T-12` or custom) and **Takeaway** (choose pickup time slot + ₹20.00 eco-packaging fee).
- **Shared Group Table Cart**: Every table session generates a shareable `session_code` (e.g., seeded `DINE-T04`). Multiple diners can join the same session from different tabs/devices, see live participant badges, and track who added each dish (`added_by`).
- **Bill Splitting & Indian GST**: Automatic **₹** breakdown (`Subtotal`, `2.5% CGST`, `2.5% SGST`, Takeaway packaging fee if applicable, `Grand Total`). Split equally among N people or item-wise by diner with exact paise reconciliation and individual `Mark Paid` tracking.
- **Live Order Tracker**: Real-time stepper (`Queued` → `Preparing` → `Ready` → `Served`) synced via SSE.

### 2. Kitchen Display System (KDS) View
- High-contrast dark kitchen ticket board.
- Filter tickets by `All Active`, `Queued`, `Preparing`, `Ready`, and `Served`.
- Displays table number or takeaway pickup slot, elapsed minutes, spice badges, add-ons, and kitchen notes.
- One-click ticket progression (`Start Preparing` → `Mark Ready` → `Mark Served`) pushes live updates to Customer trackers.

### 3. Admin View
- **KPI Summary**: Total Revenue (₹), Total Orders (Dine-In vs Takeaway split), Average Order Value, Active KDS Tickets, Low/Out-of-Stock alerts, and Top Dishes leaderboard.
- **Menu & Inventory Management**: Create new dishes, edit ₹ prices & stock quantities inline, toggle `In Stock` / `Out of Stock`, and hide/show menu items.

---

## Folder Structure

```text
miniproject/
├── app.py                   # CLI entry point (--host, --port, --init-db, --reset-db)
├── requirements.txt         # Zero external dependencies (Python 3.10+ stdlib + sqlite3)
├── README.md
├── backend/
│   ├── __init__.py
│   ├── config.py            # GST rates (2.5% CGST + 2.5% SGST), statuses, slots
│   ├── db.py                # SQLite schema DDL, WAL mode, foreign keys
│   ├── events.py            # Thread-safe SSE EventBroker
│   ├── seed.py              # Seeded Indian menu, add-ons, active table DINE-T04, sample orders
│   ├── server.py            # ThreadingHTTPServer REST API + SSE + static files
│   └── services.py          # Validation, GST math, cart, split shares, KDS, admin metrics
├── frontend/
│   ├── index.html           # Customer, KDS, and Admin SPA views
│   ├── styles.css           # Responsive styling + dark KDS theme
│   └── js/
│       ├── api.js           # Fetch client, INR formatter, SSE + polling fallback
│       ├── main.js          # App state, view router, real-time event dispatcher
│       ├── customer.js      # Menu, filters, modal, shared cart, split bill, live tracker
│       ├── kds.js           # Kitchen ticket queue & one-click status updates
│       └── admin.js         # KPIs, top dishes, menu CRUD & stock toggles
└── tests/
    ├── __init__.py
    └── test_api.py          # Automated REST API, validation, split math & SSE tests
```

---

## Database Schema (SQLite)

- `users`: `id`, `name`, `role` (`customer` | `kitchen` | `admin`), `pin_code`, `created_at`
- `tables_sessions`: `id`, `table_number`, `session_code`, `order_mode` (`dine_in` | `takeaway`), `pickup_slot`, `host_name`, `status`, `created_at`
- `session_participants`: `id`, `session_id` (FK), `participant_name`, `joined_at`
- `menu_items`: `id`, `name`, `category`, `description`, `price_paise`, `is_veg`, `is_jain`, `is_vegan`, `spice_level`, `prep_time_mins`, `in_stock`, `stock_count`, `is_active`, `image_emoji`, `created_at`
- `addons`: `id`, `name`, `category` (`customisation` | `smart_addon`), `price_paise`, dietary flags, `in_stock`
- `menu_item_addons`: `(menu_item_id, addon_id)` join table with `is_recommended`
- `cart_items`: `id`, `session_id` (FK), `menu_item_id` (FK), `added_by`, `quantity`, `spice_preference`, `selected_addons_json`, `notes`, `created_at`
- `orders`: `id`, `order_number`, `session_id` (FK), `order_mode`, `table_number`, `pickup_slot`, `customer_name`, `status`, `subtotal_paise`, `cgst_paise`, `sgst_paise`, `packaging_fee_paise`, `total_paise`, `split_mode`, `special_instructions`, `created_at`, `updated_at`
- `order_items`: `id`, `order_id` (FK), `menu_item_id` (FK), `item_name`, `added_by`, `quantity`, `unit_price_paise`, `addons_total_paise`, `selected_addons_json`, `spice_preference`, `notes`, `line_total_paise`
- `split_shares`: `id`, `order_id` (FK), `participant_name`, `amount_paise`, `assigned_items_json`, `is_paid`, `paid_at`

---

## Setup, Run & Test Instructions

### Prerequisites
- **Python 3.10+** (verified on Python 3.14.6; no `pip install` or `npm install` needed).

### 1. Run the Automated Test Suite
```powershell
python3.14 -m unittest discover -s tests -v
```

### 2. Initialize / Reset Seed Database (Optional)
```powershell
python3.14 app.py --reset-db --init-db
```

### 3. Start the Full-Stack Server
```powershell
python3.14 app.py --port 8000
```
Open **http://127.0.0.1:8000** in two browser tabs to test real-time shared table cart (`DINE-T04`) and Customer ↔ KDS live order status transitions!

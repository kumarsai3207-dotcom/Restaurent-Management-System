"""Application constants and configuration for the Restaurant Ordering System."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "restaurant.db"
FRONTEND_DIR = BASE_DIR / "frontend"

# Indian Restaurant GST breakdown: 2.5% CGST + 2.5% SGST = 5% total GST
CGST_RATE_BPS = 250  # 2.50% in basis points (out of 10000)
SGST_RATE_BPS = 250  # 2.50% in basis points (out of 10000)
TAKEAWAY_PACKAGING_FEE_PAISE = 2000  # ₹20.00 eco-packaging fee for takeaway orders

ORDER_STATUSES = ("Queued", "Preparing", "Ready", "Served", "Cancelled")
VALID_STATUS_TRANSITIONS = {
    "Queued": ("Preparing", "Cancelled"),
    "Preparing": ("Ready", "Cancelled"),
    "Ready": ("Served",),
    "Served": (),
    "Cancelled": (),
}

SPICE_LEVELS = ("None", "Mild", "Medium", "Hot", "Extra Hot")
SPICE_PREFERENCES = ("No Spice / Jain", "Mild", "Regular", "Spicy", "Extra Spicy")
MENU_CATEGORIES = ("Starters", "Mains", "Breads & Rice", "Beverages", "Desserts")

TABLE_NUMBERS = [f"T-{i:02d}" for i in range(1, 13)]
PICKUP_SLOTS = (
    "ASAP (15-20 mins)",
    "12:30 PM - 12:45 PM",
    "01:00 PM - 01:15 PM",
    "01:30 PM - 01:45 PM",
    "07:00 PM - 07:15 PM",
    "07:30 PM - 07:45 PM",
    "08:00 PM - 08:15 PM",
    "08:30 PM - 08:45 PM",
    "09:00 PM - 09:15 PM",
)

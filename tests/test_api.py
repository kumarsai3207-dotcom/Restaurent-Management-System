"""Automated unit, HTTP REST API, and SSE integration tests."""

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from backend.config import FRONTEND_DIR
from backend.seed import seed_database
from backend.server import RestaurantHTTPServer


class RestaurantAPITestCase(unittest.TestCase):
    """Spins up an isolated SQLite DB and live ThreadingHTTPServer per test class/method."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp_dir.name) / "test_restaurant.db"
        seed_database(self.db_path, force=True)

        self.server = RestaurantHTTPServer(
            ("127.0.0.1", 0),
            db_path=self.db_path,
            frontend_dir=FRONTEND_DIR,
        )
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._tmp_dir.cleanup()

    def request_json(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        conn.close()
        return resp.status, json.loads(raw) if raw else {}

    def test_health_and_static_index(self) -> None:
        status, data = self.request_json("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["gst_rate_pct"], 5.0)

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/")
        resp = conn.getresponse()
        html = resp.read().decode("utf-8")
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertIn("SpiceRoute Kitchen", html)

    def test_menu_filters_and_validation(self) -> None:
        status, all_menu = self.request_json("GET", "/api/menu")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(all_menu["items"]), 15)

        status, jain_menu = self.request_json("GET", "/api/menu?jain=1")
        self.assertEqual(status, 200)
        self.assertTrue(len(jain_menu["items"]) > 0)
        self.assertTrue(all(item["is_jain"] for item in jain_menu["items"]))

        status, vegan_hot = self.request_json("GET", "/api/menu?vegan=1&spice_level=Extra%20Hot")
        self.assertEqual(status, 200)
        self.assertTrue(any("Kolhapuri" in i["name"] for i in vegan_hot["items"]))

        status, bad = self.request_json("GET", "/api/menu?spice_level=Volcanic")
        self.assertEqual(status, 400)
        self.assertIn("error", bad)

    def test_shared_table_cart_gst_and_item_wise_split(self) -> None:
        # Join seeded active table DINE-T04 as Vikram
        status, joined = self.request_json(
            "POST",
            "/api/sessions",
            {"session_code": "DINE-T04", "participant_name": "Vikram"},
        )
        self.assertEqual(status, 201)
        sess = joined["session"]
        self.assertIn("Vikram", sess["participants"])
        self.assertIn("Aarav", sess["participants"])
        self.assertGreaterEqual(len(sess["cart_items"]), 2)

        # Find a Jain starter and an add-on
        _, menu = self.request_json("GET", "/api/menu?jain=1&category=Starters")
        corn_dish = menu["items"][0]
        addon_id = corn_dish["addons"][0]["id"]

        # Vikram adds item with customisation
        status, updated = self.request_json(
            "POST",
            f"/api/sessions/{sess['id']}/cart",
            {
                "menu_item_id": corn_dish["id"],
                "quantity": 1,
                "added_by": "Vikram",
                "spice_preference": "No Spice / Jain",
                "addon_ids": [addon_id],
                "notes": "No garlic please",
            },
        )
        self.assertEqual(status, 201)
        bill = updated["session"]["bill"]
        self.assertEqual(bill["packaging_fee_paise"], 0)
        expected_cgst = (bill["subtotal_paise"] * 250 + 5000) // 10000
        self.assertEqual(bill["cgst_paise"], expected_cgst)
        self.assertEqual(bill["total_paise"], bill["subtotal_paise"] + bill["cgst_paise"] + bill["sgst_paise"])

        # Checkout with item_wise split (default by added_by)
        status, checkout = self.request_json(
            "POST",
            f"/api/sessions/{sess['id']}/checkout",
            {"split_mode": "item_wise", "customer_name": "Table 4 Group"},
        )
        self.assertEqual(status, 201)
        order = checkout["order"]
        self.assertEqual(order["status"], "Queued")
        self.assertEqual(order["split_mode"], "item_wise")
        self.assertEqual(sum(s["amount_paise"] for s in order["split_shares"]), order["total_paise"])

        # Mark first split share paid
        first_share = order["split_shares"][0]
        status, paid_res = self.request_json(
            "PATCH",
            f"/api/orders/{order['id']}/shares/{first_share['id']}",
            {"is_paid": True},
        )
        self.assertEqual(status, 200)
        self.assertTrue(paid_res["order"]["split_shares"][0]["is_paid"])

    def test_takeaway_mode_equal_split_and_kds_lifecycle(self) -> None:
        # Create new takeaway session
        status, created = self.request_json(
            "POST",
            "/api/sessions",
            {
                "order_mode": "takeaway",
                "pickup_slot": "08:00 PM - 08:15 PM",
                "participant_name": "Diya",
            },
        )
        self.assertEqual(status, 201)
        sess = created["session"]
        self.assertEqual(sess["order_mode"], "takeaway")

        # Empty cart checkout must return 400
        status, err = self.request_json("POST", f"/api/sessions/{sess['id']}/checkout", {})
        self.assertEqual(status, 400)
        self.assertIn("empty cart", err["error"].lower())

        # Add item and checkout with equal split across 3 diners
        _, menu = self.request_json("GET", "/api/menu")
        dish = menu["items"][0]
        status, added = self.request_json(
            "POST",
            f"/api/sessions/{sess['id']}/cart",
            {"menu_item_id": dish["id"], "quantity": 2, "added_by": "Diya"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(added["session"]["bill"]["packaging_fee_paise"], 2000)

        status, checked = self.request_json(
            "POST",
            f"/api/sessions/{sess['id']}/checkout",
            {
                "split_mode": "equal",
                "split_config": {"participants": ["Diya", "Kabir", "Nisha"]},
            },
        )
        self.assertEqual(status, 201)
        order = checked["order"]
        self.assertEqual(len(order["split_shares"]), 3)
        self.assertEqual(sum(s["amount_paise"] for s in order["split_shares"]), order["total_paise"])

        # KDS transitions: Queued -> Preparing -> Ready -> Served
        for next_st in ("Preparing", "Ready", "Served"):
            status, res = self.request_json(
                "PATCH",
                f"/api/orders/{order['id']}/status",
                {"status": next_st},
            )
            self.assertEqual(status, 200)
            self.assertEqual(res["order"]["status"], next_st)

        # Invalid transition from Served -> Queued must return 409
        status, bad_tr = self.request_json(
            "PATCH",
            f"/api/orders/{order['id']}/status",
            {"status": "Queued"},
        )
        self.assertEqual(status, 409)
        self.assertIn("Cannot transition", bad_tr["error"])

    def test_admin_crud_stock_guard_and_metrics(self) -> None:
        # Create new item
        status, created = self.request_json(
            "POST",
            "/api/admin/menu",
            {
                "name": "Malai Kofta",
                "category": "Mains",
                "description": "Soft cottage cheese & potato dumplings in creamy saffron gravy.",
                "price_rupees": 340,
                "spice_level": "Mild",
                "stock_count": 2,
                "prep_time_mins": 18,
                "is_veg": True,
                "is_jain": False,
                "is_vegan": False,
            },
        )
        self.assertEqual(status, 201)
        item_id = created["item"]["id"]
        self.assertEqual(created["item"]["price_paise"], 34000)

        # Toggle out of stock
        status, patched = self.request_json("PATCH", f"/api/admin/menu/{item_id}", {"in_stock": False})
        self.assertEqual(status, 200)
        self.assertFalse(patched["item"]["in_stock"])

        # Attempting to add out-of-stock item to cart must fail with 409
        _, s_res = self.request_json("POST", "/api/sessions", {"order_mode": "dine_in", "table_number": "T-09"})
        sid = s_res["session"]["id"]
        status, oos_err = self.request_json(
            "POST",
            f"/api/sessions/{sid}/cart",
            {"menu_item_id": item_id, "quantity": 1},
        )
        self.assertEqual(status, 409)

        # Metrics check
        status, metrics = self.request_json("GET", "/api/admin/metrics")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(metrics["metrics"]["total_orders"], 4)
        self.assertGreater(metrics["metrics"]["total_revenue_paise"], 0)
        self.assertTrue(len(metrics["metrics"]["top_dishes"]) > 0)

    def test_sse_realtime_stream_receives_order_update(self) -> None:
        # Open SSE stream in client connection and trigger KDS status update
        sse_conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        sse_conn.request("GET", "/api/events")
        sse_resp = sse_conn.getresponse()
        self.assertEqual(sse_resp.status, 200)

        # Read initial connected event
        first_chunk = b""
        while b"\n\n" not in first_chunk:
            first_chunk += sse_resp.read1(1024)
        self.assertIn(b"event: connected", first_chunk)

        # Trigger an order status update on seeded ORD-1004 (Queued -> Preparing)
        _, orders_res = self.request_json("GET", "/api/orders?status=Queued")
        queued_order = orders_res["orders"][0]
        status, _ = self.request_json(
            "PATCH",
            f"/api/orders/{queued_order['id']}/status",
            {"status": "Preparing"},
        )
        self.assertEqual(status, 200)

        # Read the pushed SSE frame
        event_chunk = b""
        while b"\n\n" not in event_chunk:
            event_chunk += sse_resp.read1(2048)
        sse_conn.close()

        text = event_chunk.decode("utf-8")
        self.assertIn("event: order.updated", text)
        self.assertIn("Preparing", text)


if __name__ == "__main__":
    unittest.main()

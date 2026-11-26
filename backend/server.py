"""HTTP REST API server, SSE real-time stream, and static frontend server."""

import json
import mimetypes
import queue
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from backend import services
from backend.config import (
    DEFAULT_DB_PATH,
    FRONTEND_DIR,
    MENU_CATEGORIES,
    ORDER_STATUSES,
    PICKUP_SLOTS,
    SPICE_LEVELS,
    SPICE_PREFERENCES,
    TABLE_NUMBERS,
)
from backend.events import EventBroker
from backend.services import ServiceError


class RestaurantHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer carrying DB path, static root, and SSE EventBroker."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        db_path: Path | str = DEFAULT_DB_PATH,
        frontend_dir: Path | str = FRONTEND_DIR,
        broker: EventBroker | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.frontend_dir = Path(frontend_dir)
        self.broker = broker or EventBroker()
        super().__init__(server_address, RestaurantRequestHandler)


class RestaurantRequestHandler(BaseHTTPRequestHandler):
    """Handles REST JSON endpoints, SSE event streaming, and SPA static files."""

    protocol_version = "HTTP/1.1"
    server: RestaurantHTTPServer  # type: ignore[assignment]

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy default stderr request logs during tests; uncomment for verbose debugging
        return

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        raw_len = self.headers.get("Content-Length")
        if not raw_len:
            return {}
        try:
            length = int(raw_len)
        except ValueError:
            raise ServiceError("Invalid Content-Length header", 400) from None
        if length <= 0:
            return {}
        if length > 1_048_576:
            raise ServiceError("Request payload too large (max 1MB)", 413)
        raw_bytes = self.rfile.read(length)
        try:
            parsed = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ServiceError("Malformed JSON request body", 400) from None
        if not isinstance(parsed, dict):
            raise ServiceError("JSON body must be an object", 400)
        return parsed

    def _handle_sse(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        sub_q = self.server.broker.subscribe()
        try:
            hello = json.dumps({"status": "connected", "subscribers": self.server.broker.subscriber_count})
            self.wfile.write(f"event: connected\ndata: {hello}\n\n".encode("utf-8"))
            self.wfile.flush()

            while True:
                try:
                    frame = sub_q.get(timeout=15.0)
                    self.wfile.write(frame.encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            self.server.broker.unsubscribe(sub_q)

    def _serve_static(self, raw_path: str) -> None:
        portal_entry = {
            "/customer": "customer/index.html",
            "/customer/": "customer/index.html",
            "/staff": "staff/index.html",
            "/staff/": "staff/index.html",
            "/admin": "staff/index.html",
            "/admin/": "staff/index.html",
        }.get(raw_path)
        if portal_entry:
            rel = portal_entry
        else:
            rel = raw_path.lstrip("/") or "index.html"
        target = (self.server.frontend_dir / rel).resolve()
        root = self.server.frontend_dir.resolve()

        if root not in target.parents and target != root:
            self._send_json(403, {"error": "Forbidden path"})
            return

        if target.is_dir() or not target.exists():
            if "." not in Path(rel).name:
                target = root / "index.html"
            else:
                self._send_json(404, {"error": "Static asset not found"})
                return

        if not target.exists():
            self._send_json(404, {"error": "Frontend index not found"})
            return

        content = target.read_bytes()
        mime, _ = mimetypes.guess_type(str(target))
        content_type = mime or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type = f"{content_type}; charset=utf-8"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if not path.startswith("/api/"):
            if method == "GET":
                self._serve_static(path)
            else:
                self._send_json(405, {"error": "Method not allowed"})
            return

        db_path = self.server.db_path
        broker = self.server.broker

        try:
            if method == "GET" and path == "/api/events":
                self._handle_sse()
                return

            if method == "GET" and path == "/api/health":
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "categories": list(MENU_CATEGORIES),
                        "spice_levels": list(SPICE_LEVELS),
                        "spice_preferences": list(SPICE_PREFERENCES),
                        "order_statuses": list(ORDER_STATUSES),
                        "table_numbers": TABLE_NUMBERS,
                        "pickup_slots": list(PICKUP_SLOTS),
                        "gst_rate_pct": 5.0,
                        "cgst_rate_pct": 2.5,
                        "sgst_rate_pct": 2.5,
                        "sse_subscribers": broker.subscriber_count,
                    },
                )
                return

            if method == "GET" and path == "/api/menu":
                items = services.list_menu_items(
                    db_path,
                    category=qs.get("category", [None])[0],
                    search=qs.get("search", [None])[0],
                    veg_only=qs.get("veg", ["0"])[0].lower() in ("1", "true"),
                    jain_only=qs.get("jain", ["0"])[0].lower() in ("1", "true"),
                    vegan_only=qs.get("vegan", ["0"])[0].lower() in ("1", "true"),
                    spice_level=qs.get("spice_level", [None])[0],
                    include_inactive=qs.get("include_inactive", ["0"])[0].lower() in ("1", "true"),
                )
                self._send_json(200, {"items": items})
                return

            if method == "GET" and path == "/api/addons":
                self._send_json(200, {"addons": services.list_all_addons(db_path)})
                return

            if method == "POST" and path == "/api/admin/menu":
                body = self._read_json_body()
                created = services.create_menu_item(body, db_path=db_path, broker=broker)
                self._send_json(201, {"item": created})
                return

            if m := re.fullmatch(r"/api/admin/menu/(\d+)", path):
                item_id = int(m.group(1))
                if method == "PATCH":
                    body = self._read_json_body()
                    updated = services.update_menu_item(item_id, body, db_path=db_path, broker=broker)
                    self._send_json(200, {"item": updated})
                    return

            if method == "GET" and path == "/api/admin/metrics":
                self._send_json(200, {"metrics": services.get_admin_metrics(db_path)})
                return

            if method == "GET" and path == "/api/sessions":
                self._send_json(200, {"sessions": services.list_active_sessions(db_path)})
                return

            if method == "POST" and path == "/api/sessions":
                body = self._read_json_body()
                session = services.create_or_join_session(body, db_path=db_path, broker=broker)
                self._send_json(201, {"session": session})
                return

            if m := re.fullmatch(r"/api/sessions/(\d+)", path):
                session_id = int(m.group(1))
                if method == "GET":
                    self._send_json(200, {"session": services.get_session(session_id, db_path=db_path)})
                    return

            if m := re.fullmatch(r"/api/sessions/(\d+)/mode", path):
                session_id = int(m.group(1))
                if method == "PATCH":
                    body = self._read_json_body()
                    session = services.update_session_mode(session_id, body, db_path=db_path, broker=broker)
                    self._send_json(200, {"session": session})
                    return

            if m := re.fullmatch(r"/api/sessions/(\d+)/cart", path):
                session_id = int(m.group(1))
                if method == "POST":
                    body = self._read_json_body()
                    session = services.add_cart_item(session_id, body, db_path=db_path, broker=broker)
                    self._send_json(201, {"session": session})
                    return

            if m := re.fullmatch(r"/api/sessions/(\d+)/cart/(\d+)", path):
                session_id, cart_item_id = int(m.group(1)), int(m.group(2))
                if method == "PATCH":
                    body = self._read_json_body()
                    session = services.update_cart_item(
                        session_id, cart_item_id, body, db_path=db_path, broker=broker
                    )
                    self._send_json(200, {"session": session})
                    return
                if method == "DELETE":
                    session = services.remove_cart_item(
                        session_id, cart_item_id, db_path=db_path, broker=broker
                    )
                    self._send_json(200, {"session": session})
                    return

            if m := re.fullmatch(r"/api/sessions/(\d+)/checkout", path):
                session_id = int(m.group(1))
                if method == "POST":
                    body = self._read_json_body()
                    order = services.checkout_session(session_id, body, db_path=db_path, broker=broker)
                    self._send_json(201, {"order": order})
                    return

            if method == "GET" and path == "/api/orders":
                status_filter = qs.get("status", [None])[0]
                active_only = qs.get("active_only", ["0"])[0].lower() in ("1", "true")
                orders = services.list_orders(db_path, status=status_filter, active_only=active_only)
                self._send_json(200, {"orders": orders})
                return

            if m := re.fullmatch(r"/api/orders/(\d+)", path):
                order_id = int(m.group(1))
                if method == "GET":
                    self._send_json(200, {"order": services.get_order(order_id, db_path=db_path)})
                    return

            if m := re.fullmatch(r"/api/orders/(\d+)/status", path):
                order_id = int(m.group(1))
                if method == "PATCH":
                    body = self._read_json_body()
                    new_status = str(body.get("status", "")).strip()
                    order = services.update_order_status(order_id, new_status, db_path=db_path, broker=broker)
                    self._send_json(200, {"order": order})
                    return

            if m := re.fullmatch(r"/api/orders/(\d+)/split", path):
                order_id = int(m.group(1))
                if method == "POST":
                    body = self._read_json_body()
                    order = services.split_existing_order(order_id, body, db_path=db_path, broker=broker)
                    self._send_json(200, {"order": order})
                    return

            if m := re.fullmatch(r"/api/orders/(\d+)/shares/(\d+)", path):
                order_id, share_id = int(m.group(1)), int(m.group(2))
                if method == "PATCH":
                    body = self._read_json_body()
                    if "is_paid" not in body or not isinstance(body["is_paid"], bool):
                        raise ServiceError("is_paid boolean field is required", 400)
                    order = services.toggle_split_share_paid(
                        order_id, share_id, body["is_paid"], db_path=db_path, broker=broker
                    )
                    self._send_json(200, {"order": order})
                    return

            self._send_json(404, {"error": f"Endpoint {method} {path} not found"})

        except ServiceError as exc:
            payload: dict[str, Any] = {"error": exc.message}
            if exc.details is not None:
                payload["details"] = exc.details
            self._send_json(exc.status_code, payload)
        except Exception as exc:
            self._send_json(500, {"error": "Internal server error", "details": str(exc)})

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

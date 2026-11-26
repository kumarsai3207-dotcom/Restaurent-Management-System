"""CLI entry point for the Restaurant Ordering & Live KDS System."""

import argparse
from pathlib import Path

from backend.config import DEFAULT_DB_PATH, FRONTEND_DIR
from backend.seed import seed_database
from backend.server import RestaurantHTTPServer


def main() -> None:
    parser = argparse.ArgumentParser(description="SpiceRoute Restaurant Ordering & Live KDS Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database file path")
    parser.add_argument("--init-db", action="store_true", help="Initialize and seed database, then exit")
    parser.add_argument("--reset-db", action="store_true", help="Reset and re-seed database before starting")
    args = parser.parse_args()

    seeded = seed_database(args.db, force=args.reset_db)
    if args.init_db:
        state = "seeded" if seeded else "already initialized"
        print(f"Database {state} at {args.db}")
        return

    server = RestaurantHTTPServer((args.host, args.port), db_path=args.db, frontend_dir=FRONTEND_DIR)
    print(f"SpiceRoute Restaurant System running at http://{args.host}:{args.port}")
    print(f"SQLite database: {args.db}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()

"""Owner-run, versioned MongoDB bootstrap/check without web authentication settings."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from pymongo.errors import PyMongoError

from .database import bootstrap_database, check_ready, create_client


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify topology, schema version, validators and indexes without changing data.")
    args = parser.parse_args(argv)
    try:
        direct, filename = os.getenv("MONGODB_URI"), os.getenv("MONGODB_URI_FILE")
        if direct is not None and filename:
            raise ValueError("Set MONGODB_URI or MONGODB_URI_FILE, not both.")
        uri = Path(filename).read_text(encoding="utf-8").strip() if filename else direct or ""
        if not uri.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("MONGODB_URI or MONGODB_URI_FILE must supply a MongoDB connection URI.")
        name = os.getenv("MONGODB_DATABASE", "asic_tracker").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,63}", name):
            raise ValueError("MONGODB_DATABASE must contain 1–63 letters, numbers, underscores or hyphens.")
        with create_client(uri) as client:
            result = check_ready(client[name]) if args.check else bootstrap_database(client[name])
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "ready" else 1
    except (ValueError, OSError, PyMongoError) as error:
        # Driver errors may contain host/credential-bearing URI details.
        message = str(error) if isinstance(error, ValueError) and not isinstance(error, PyMongoError) else "MongoDB schema operation failed; check owner credentials and connectivity."
        print(json.dumps({"status": "not_ready", "reason": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

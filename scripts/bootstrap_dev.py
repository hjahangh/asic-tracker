#!/usr/bin/env python3
"""Create the ignored local-development .env; never modify an existing file."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / ".env")
    args = parser.parse_args()
    # O_EXCL avoids overwriting credentials, including through a symlink.
    try:
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.exit(1, f"Already exists; left unchanged: {args.output}\n")
    with os.fdopen(descriptor, "w") as stream:
        stream.write("# Local development only; generated credentials. Do not commit.\n")
        stream.write("POSTGRES_USER=asic_tracker_dev\nPOSTGRES_DB=asic_tracker_dev\n")
        stream.write(f"POSTGRES_PASSWORD={secrets.token_urlsafe(32)}\nHTTP_PORT=8080\n")
    print(f"Created {args.output}. Start with: docker compose up --build --wait")


if __name__ == "__main__":
    main()

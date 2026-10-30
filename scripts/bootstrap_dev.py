#!/usr/bin/env python3
"""Create the ignored local-development .env; never modify an existing file."""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
import secrets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / ".env")
    args = parser.parse_args()
    keyfile = args.output.parent / "secrets" / "mongodb-keyfile"
    # O_EXCL avoids overwriting credentials, including through a symlink.
    try:
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.exit(1, f"Already exists; left unchanged: {args.output}\n")
    key_created = False
    try:
        keyfile.parent.mkdir(mode=0o700, exist_ok=True)
        key_descriptor = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        key_created = True
        with os.fdopen(key_descriptor, "w") as stream:
            stream.write(base64.b64encode(secrets.token_bytes(512)).decode("ascii") + "\n")
        with os.fdopen(descriptor, "w") as stream:
            descriptor = None
            stream.write("# Local development only; generated credentials. Do not commit.\n")
            stream.write("MONGODB_DATABASE=asic_tracker_dev\nMONGO_ROOT_USER=tracker_root\n")
            stream.write(f"MONGO_ROOT_PASSWORD={secrets.token_urlsafe(32)}\n")
            stream.write("MONGODB_OWNER_USER=tracker_owner\n")
            stream.write(f"MONGODB_OWNER_PASSWORD={secrets.token_urlsafe(32)}\n")
            stream.write("MONGODB_RUNTIME_USER=tracker_app\n")
            stream.write(f"MONGODB_RUNTIME_PASSWORD={secrets.token_urlsafe(32)}\n")
            stream.write("MONGODB_KEYFILE=./secrets/mongodb-keyfile\nHTTP_PORT=8080\n")
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        args.output.unlink(missing_ok=True)
        if key_created:
            keyfile.unlink(missing_ok=True)
        raise
    print(f"Created {args.output}. Start with: docker compose up --build --wait")


if __name__ == "__main__":
    main()

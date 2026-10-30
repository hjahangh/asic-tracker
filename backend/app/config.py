"""Explicit runtime settings; production authentication is fail-closed."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path


def _secret(name: str, default: str = "") -> str:
    value, filename = os.getenv(name), os.getenv(name + "_FILE")
    if value is not None and filename:
        raise ValueError(f"Set {name} or {name}_FILE, not both.")
    if filename:
        return Path(filename).read_text().strip()
    return value if value is not None else default


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default="", repr=False)
    auth_mode: str = "proxy"
    proxy_shared_secret: str = field(default="", repr=False)
    role_groups: dict[str, list[str]] = field(default_factory=lambda: {
        "viewer": ["asic-tracker-viewers"], "editor": ["asic-tracker-editors"], "admin": ["asic-tracker-admins"]})
    dev_user: str = "local-developer"
    dev_role: str = "admin"
    frontend_dir: Path | None = field(default_factory=lambda: Path(__file__).resolve().parents[2] / "frontend")
    enable_api_docs: bool = False
    max_body_bytes: int = 12 * 1024 * 1024
    trusted_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    require_migrations: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        default_groups = cls().role_groups
        try:
            groups = json.loads(os.getenv("ROLE_GROUPS", json.dumps(default_groups)))
        except json.JSONDecodeError as error:
            raise ValueError("ROLE_GROUPS must be a JSON object of role-to-group arrays.") from error
        frontend = os.getenv("FRONTEND_DIR")
        return cls(
            database_url=_secret("DATABASE_URL"), auth_mode=os.getenv("AUTH_MODE", "proxy").lower(),
            proxy_shared_secret=_secret("PROXY_SHARED_SECRET"), role_groups=groups,
            dev_user=os.getenv("DEV_USER", "local-developer"), dev_role=os.getenv("DEV_ROLE", "admin").lower(),
            frontend_dir=Path(frontend).resolve() if frontend else cls().frontend_dir,
            enable_api_docs=os.getenv("ENABLE_API_DOCS", "false").lower() == "true",
            max_body_bytes=int(os.getenv("MAX_BODY_BYTES", str(12 * 1024 * 1024))),
            trusted_hosts=tuple(item.strip() for item in os.getenv("TRUSTED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if item.strip()),
            require_migrations=True,
        )

    def validate(self) -> None:
        if not self.database_url:
            raise ValueError("DATABASE_URL or DATABASE_URL_FILE is required.")
        if self.auth_mode not in {"proxy", "development"}:
            raise ValueError("AUTH_MODE must be proxy or development.")
        if self.auth_mode == "proxy" and len(self.proxy_shared_secret) < 32:
            raise ValueError("Proxy authentication requires a PROXY_SHARED_SECRET of at least 32 characters.")
        if self.dev_role not in {"viewer", "editor", "admin"}:
            raise ValueError("DEV_ROLE must be viewer, editor or admin.")
        if not isinstance(self.role_groups, dict) or any(role not in {"viewer", "editor", "admin"} for role in self.role_groups):
            raise ValueError("ROLE_GROUPS keys must be viewer, editor or admin.")
        if any(not isinstance(groups, list) or any(not isinstance(group, str) or not group.strip() for group in groups) for groups in self.role_groups.values()):
            raise ValueError("ROLE_GROUPS values must be arrays of nonblank group names.")
        if not self.trusted_hosts or "*" in self.trusted_hosts:
            raise ValueError("TRUSTED_HOSTS must list explicit permitted hosts.")
        if not 1024 <= self.max_body_bytes <= 32 * 1024 * 1024:
            raise ValueError("MAX_BODY_BYTES must be between 1024 and 33554432.")


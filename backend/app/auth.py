"""Identity supplied by the hosting team's authenticated, trusted ingress.

The shared token authenticates the gateway, not the end user. The gateway must
authenticate the person, strip all incoming identity headers, and inject verified
subject/groups and the secret on its private upstream connection.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hmac
import json

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class Actor:
    subject: str
    display_name: str
    role: str
    auth_mode: str

    def as_dict(self) -> dict:
        return asdict(self)


def actor_for_request(request: Request) -> Actor:
    settings = request.app.state.settings
    if settings.auth_mode == "development":
        return Actor(settings.dev_user, settings.dev_user, settings.dev_role, "development")
    token = request.headers.get("X-Proxy-Token", "")
    if not token or not hmac.compare_digest(token.encode(), settings.proxy_shared_secret.encode()):
        raise HTTPException(401, detail={"code": "authentication_required", "message": "Sign in through the approved internal gateway."})
    subject = request.headers.get("X-Authenticated-User", "").strip()
    if not subject or len(subject) > 200 or any(ord(char) < 32 for char in subject):
        raise HTTPException(401, detail={"code": "invalid_identity", "message": "The gateway did not supply a valid authenticated subject."})
    raw_groups = request.headers.get("X-Authenticated-Groups", "")
    if len(raw_groups) > 8192:
        raise HTTPException(403, detail={"code": "invalid_groups", "message": "The gateway group claim is invalid."})
    raw_groups = raw_groups.strip()
    try:
        groups = json.loads(raw_groups) if raw_groups.startswith("[") else [group.strip() for group in raw_groups.split(",") if group.strip()]
    except (ValueError, RecursionError):
        groups = None
    if not isinstance(groups, list) or any(not isinstance(group, str) for group in groups):
        raise HTTPException(403, detail={"code": "invalid_groups", "message": "The gateway group claim is invalid."})
    role = next((role for role in ("admin", "editor", "viewer") if set(groups) & set(settings.role_groups.get(role, []))), None)
    if not role:
        raise HTTPException(403, detail={"code": "access_not_assigned", "message": "Your identity has no assigned tracker role."})
    name = request.headers.get("X-Authenticated-Name", subject).strip()[:500]
    return Actor(subject, name or subject, role, "proxy")


def require_editor(actor: Actor) -> None:
    if actor.role not in {"editor", "admin"}:
        raise HTTPException(403, detail={"code": "read_only", "message": "Your role is read-only."})


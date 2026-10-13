import datetime
import hashlib
import re
import secrets
from typing import Optional, Tuple

from django.db import transaction
from django.utils import timezone

from apps.developer_console.models import DeveloperApiKey, DeveloperApplication

KEY_PATTERN = re.compile(r"^(vck_live_[0-9a-fA-F]{8})_([A-Za-z0-9_-]+)$")


def hash_key(full_key: str) -> str:
    """Computes SHA-256 hex digest of the full API key."""
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()


def parse_key_prefix(full_key: str) -> Optional[str]:
    """Extracts the 17-character lookup prefix (vck_live_<8-hex>) if valid."""
    match = KEY_PATTERN.match(full_key.strip())
    if match:
        return match.group(1).lower()
    return None


def generate_api_key(
    name: str,
    application: DeveloperApplication,
    scopes: list[str],
    expires_at: Optional[datetime.datetime] = None,
) -> Tuple[DeveloperApiKey, str]:
    """Generates a new DeveloperApiKey with 256 bits of entropy.

    Returns:
        (DeveloperApiKey instance, plaintext_full_key)
    The plaintext_full_key must be displayed once and never persisted.
    """
    max_attempts = 5
    prefix = ""
    for _ in range(max_attempts):
        hex_component = secrets.token_hex(4).lower()
        candidate_prefix = f"vck_live_{hex_component}"
        if not DeveloperApiKey.objects.filter(key_prefix=candidate_prefix).exists():
            prefix = candidate_prefix
            break

    if not prefix:
        raise RuntimeError("Failed to generate unique API key prefix after multiple attempts.")

    # 32 random bytes = 256 bits of entropy -> ~43 chars URL-safe Base64
    secret = secrets.token_urlsafe(32)
    full_key = f"{prefix}_{secret}"
    hashed_secret = hash_key(full_key)

    api_key = DeveloperApiKey.objects.create(
        application=application,
        name=name,
        key_prefix=prefix,
        hashed_secret=hashed_secret,
        scopes=scopes,
        status="active",
        expires_at=expires_at,
    )
    return api_key, full_key


@transaction.atomic
def rotate_api_key(
    old_key: DeveloperApiKey,
    name: Optional[str] = None,
    expires_at: Optional[datetime.datetime] = None,
) -> Tuple[DeveloperApiKey, str]:
    """Rotates an API key atomically.

    Revokes old_key and creates a replacement key with identical scopes and application.
    """
    now = timezone.now()
    old_key.status = "revoked"
    old_key.revoked_at = now
    old_key.save(update_fields=["status", "revoked_at"])

    new_name = name or f"{old_key.name} (Rotated)"
    new_expires_at = expires_at if expires_at is not None else old_key.expires_at

    new_key, new_full_key = generate_api_key(
        name=new_name,
        application=old_key.application,
        scopes=list(old_key.scopes),
        expires_at=new_expires_at,
    )
    return new_key, new_full_key


def revoke_api_key(key: DeveloperApiKey) -> DeveloperApiKey:
    """Revokes an API key immediately."""
    key.status = "revoked"
    key.revoked_at = timezone.now()
    key.save(update_fields=["status", "revoked_at"])
    return key

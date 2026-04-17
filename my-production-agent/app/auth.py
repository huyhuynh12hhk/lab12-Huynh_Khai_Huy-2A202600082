"""
API Key Authentication

Clients must send a valid API key in the X-API-Key request header.

Flow:
  Client → X-API-Key: <secret>  →  FastAPI dependency verify_api_key()
  [V]  Key matches → returns user_id (used for rate-limiting & cost-guard)
  [X]  Key missing / wrong → HTTP 401 Unauthorized

User ID derivation:
  In this demo there is a single shared key whose user_id is "default".
  In a real system you would look the key up in a database and return
  the corresponding user identifier.
"""
import hashlib

from fastapi import Header, HTTPException

from .config import settings


def verify_api_key(x_api_key: str = Header(...)) -> str:
    """
    FastAPI dependency — validates the X-API-Key header.

    Returns:
        user_id (str): Identifier derived from the API key.
    Raises:
        HTTPException 401: When the key is missing or does not match.
    """
    if x_api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    # Derive a stable user_id from the key without exposing the raw secret.
    # Using a short SHA-256 prefix is enough for rate-limiting namespacing.
    user_id = "user-" + hashlib.sha256(x_api_key.encode()).hexdigest()[:12]
    return user_id

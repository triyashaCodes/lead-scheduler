import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, Any

import cachecontrol
import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# (token, expected audience) -> verified claims; raises ValueError if invalid.
TokenVerifier = Callable[[str, str], dict[str, Any]]

_bearer = HTTPBearer(auto_error=False)


def make_google_verifier(request: google_requests.Request) -> TokenVerifier:
    """Build a verifier that checks signature, expiry, issuer and audience."""

    def verify(token: str, audience: str) -> dict[str, Any]:
        return id_token.verify_oauth2_token(token, request, audience)

    return verify


@lru_cache
def get_token_verifier() -> TokenVerifier:
    # Google's signing certificates are cached according to their cache
    # headers, so this does not call Google on every request.
    session = cachecontrol.CacheControl(requests.Session())
    return make_google_verifier(google_requests.Request(session=session))


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_attorney(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verify_token: Annotated[TokenVerifier, Depends(get_token_verifier)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Return the authenticated attorney's email, lowercased.

    The identity comes only from the verified Google ID token in the
    Authorization header, never from a request body. A missing, invalid or
    expired token is a 401; a valid login that is not on the attorney
    allowlist is a 403.
    """
    if credentials is None:
        raise _unauthorized("Not authenticated")

    try:
        claims = verify_token(credentials.credentials, settings.google_client_id)
    except google_exceptions.TransportError as exc:
        # We could not fetch Google's certificates: not the caller's fault.
        logger.error("Could not reach Google to verify a token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable",
        ) from exc
    except (ValueError, google_exceptions.GoogleAuthError) as exc:
        logger.info("Rejected ID token: %s", exc)
        raise _unauthorized("Invalid or expired token") from exc

    email = claims.get("email")
    if claims.get("email_verified") is not True or not isinstance(email, str) or not email:
        raise _unauthorized("A verified email is required")

    email = email.strip().lower()
    allowed = {entry.lower() for entry in settings.attorney_email_list}
    if email not in allowed:
        logger.warning("Valid login rejected: not on the attorney allowlist")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized"
        )
    return email

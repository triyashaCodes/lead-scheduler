from fastapi import HTTPException, status


def get_current_attorney() -> str:
    """Return the authenticated attorney's email.

    Placeholder: real Google SSO verification does not exist yet, so every
    request is rejected. Tests override this dependency. The identity always
    comes from here, never from a request body.
    """
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

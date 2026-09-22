from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests
from google.oauth2 import id_token

from .config import GOOGLE_CLIENT_ID

security = HTTPBearer()

def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    try:
        payload = id_token.verify_oauth2_token(
            credentials.credentials,
            requests.Request(),
            GOOGLE_CLIENT_ID
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, details="Invalid Google token") from exc

    if payload.get("iss") not in {
        "accounts.google.com",
        "https://accounts.google.com"
    }:
        raise HTTPException(status_code=401, details="Invalid token issuer")

    return payload
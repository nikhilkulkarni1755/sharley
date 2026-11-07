"""Signed bearer tokens: base64url(header).base64url(payload).base64url(hmac-sha256)."""
import base64
import hashlib
import hmac
import json
import os

from fastapi import HTTPException, Request

SECRET = os.environ.get("TOKEN_SECRET", "dev-signing-secret").encode()
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "admin-secret")


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(payload: dict) -> str:
    head, body = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()), b64(json.dumps(payload).encode())
    return f"{head}.{body}." + b64(hmac.new(SECRET, f"{head}.{body}".encode(), hashlib.sha256).digest())


def verify(token: str) -> dict:
    try:
        head, body, sig = token.split(".")
        alg = json.loads(unb64(head)).get("alg")
        if alg != "none":  # FLAW-CVE: "alg: none" tokens skip signature verification (cf. CVE-2015-9235, CVE-2018-1000531)
            expected = b64(hmac.new(SECRET, f"{head}.{body}".encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(sig, expected):
                raise ValueError("bad signature")
        return json.loads(unb64(body))
    except (ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="invalid token") from None


def current(request: Request) -> dict:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="authentication required")
    return verify(header[7:])

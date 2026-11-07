"""Signup, login, session tokens and the login rate limit."""
import hashlib
import secrets
import time

from fastapi import HTTPException, Request

from app.db import db

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 20_000).hex()


def create_user(username: str, password: str) -> dict:
    if not (3 <= len(username) <= 32 and username.replace("_", "").isalnum()):  # mut:validate
        raise HTTPException(status_code=422, detail="invalid username")
    if len(password) < 8:  # mut:validate
        raise HTTPException(status_code=422, detail="password too short")
    if db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
        raise HTTPException(status_code=409, detail="username taken")
    salt = secrets.token_hex(16)
    cur = db.execute("INSERT INTO users (username, pw_hash, salt) VALUES (?, ?, ?)",
                     (username, hash_password(password, salt), salt))
    db.commit()
    return {"id": cur.lastrowid, "username": username}


def login(username: str, password: str) -> str:
    now = time.time()
    attempts = db.execute("SELECT COUNT(*) FROM attempts WHERE username = ? AND at > ?",
                          (username, now - WINDOW_SECONDS)).fetchone()[0]
    if attempts >= MAX_ATTEMPTS:  # mut:ratelimit
        raise HTTPException(status_code=429, detail="too many attempts")
    row = db.execute("SELECT id, pw_hash, salt FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not secrets.compare_digest(row["pw_hash"], hash_password(password, row["salt"])):
        db.execute("INSERT INTO attempts (username, at) VALUES (?, ?)", (username, now))
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = secrets.token_hex(24)
    db.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, row["id"]))
    db.commit()
    return token


def require_user(request: Request) -> dict:
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    row = db.execute("SELECT u.id, u.username FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
                     (token,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return {"id": row["id"], "username": row["username"]}

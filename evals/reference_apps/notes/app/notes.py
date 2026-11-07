"""Notes CRUD with per-user ownership."""
from fastapi import HTTPException

from app.db import db

MAX_TITLE = 100
MAX_BODY = 10_000
DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def validate_note(title: str, body: str) -> None:
    if not title.strip() or len(title) > MAX_TITLE:  # mut:validate
        raise HTTPException(status_code=422, detail="title must be 1-100 characters")
    if len(body) > MAX_BODY:  # mut:validate
        raise HTTPException(status_code=422, detail="body too long")


def view(row) -> dict:
    return {"id": row["id"], "title": row["title"], "body": row["body"]}


def create(user: dict, title: str, body: str) -> dict:
    validate_note(title, body)
    cur = db.execute("INSERT INTO notes (user_id, title, body) VALUES (?, ?, ?)", (user["id"], title, body))
    db.commit()
    return {"id": cur.lastrowid, "title": title, "body": body}


def fetch_owned(user: dict, note_id: int):
    row = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()  # mut:sql
    if row is None:
        raise HTTPException(status_code=404, detail="note not found")
    if row["user_id"] != user["id"]:  # mut:owner
        raise HTTPException(status_code=404, detail="note not found")
    return row


def list_notes(user: dict, q: str = "", limit: int = DEFAULT_LIMIT, offset: int = 0) -> list[dict]:
    if limit < 1 or limit > MAX_LIMIT or offset < 0:
        raise HTTPException(status_code=422, detail="invalid paging")
    rows = db.execute("SELECT * FROM notes WHERE user_id = ? AND title LIKE ? ORDER BY id LIMIT ? OFFSET ?",
                      (user["id"], f"%{q}%", limit, offset)).fetchall()
    return [view(r) for r in rows]


def update(user: dict, note_id: int, title: str, body: str) -> dict:
    fetch_owned(user, note_id)
    validate_note(title, body)
    db.execute("UPDATE notes SET title = ?, body = ? WHERE id = ?", (title, body, note_id))
    db.commit()
    return {"id": note_id, "title": title, "body": body}


def delete(user: dict, note_id: int) -> None:
    fetch_owned(user, note_id)
    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()

"""Notes API: signup/login, per-user notes. Run: uvicorn app.main:app"""
import sys
import traceback

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import auth, notes

app = FastAPI()


class Credentials(BaseModel):
    username: str
    password: str


class NoteIn(BaseModel):
    title: str
    body: str = ""


@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception):
    print(traceback.format_exc(), file=sys.stderr)
    return JSONResponse(status_code=500, content={"detail": "internal error"})  # mut:trace


def current_user(request: Request) -> dict:
    user = auth.require_user(request)  # mut:auth
    return user


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/signup", status_code=201)
def signup(c: Credentials):
    return auth.create_user(c.username, c.password)


@app.post("/auth/login")
def login(c: Credentials):
    return {"token": auth.login(c.username, c.password)}


@app.post("/notes", status_code=201)
def create_note(n: NoteIn, user: dict = Depends(current_user)):
    return notes.create(user, n.title, n.body)


@app.get("/notes")
def list_notes(q: str = "", limit: int = notes.DEFAULT_LIMIT, offset: int = 0, user: dict = Depends(current_user)):
    return notes.list_notes(user, q, limit, offset)


@app.get("/notes/{note_id}")
def get_note(note_id: int, user: dict = Depends(current_user)):
    return notes.view(notes.fetch_owned(user, note_id))


@app.put("/notes/{note_id}")
def update_note(note_id: int, n: NoteIn, user: dict = Depends(current_user)):
    return notes.update(user, note_id, n.title, n.body)


@app.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, user: dict = Depends(current_user)):
    notes.delete(user, note_id)
    return Response(status_code=204)


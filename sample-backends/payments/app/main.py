"""Payments API for users and AI agents. Run: uvicorn app.main:app"""
import secrets

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import auth
from app.db import db

app = FastAPI()
db.execute("INSERT OR IGNORE INTO principals (id, name, kind, secret) VALUES (1, 'admin', 'admin', ?)", (auth.ADMIN_SECRET,))
db.execute("INSERT OR IGNORE INTO accounts (id, principal_id, balance) VALUES (1, 1, 0)")
db.commit()


class NewPrincipal(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    kind: str = Field(pattern="^(user|agent)$")
    per_payment_limit: int | None = Field(default=None, gt=0)


class Login(BaseModel):
    principal_id: int
    secret: str


class Deposit(BaseModel):
    amount: int = Field(gt=0, le=10_000_000)


class Pay(BaseModel):
    from_account: int
    to_account: int
    amount: int = Field(gt=0, le=10_000_000)
    idempotency_key: str = Field(min_length=1, max_length=64)


def account(account_id: int):
    row = db.execute("SELECT a.*, p.kind, p.owner_id, p.per_payment_limit FROM accounts a JOIN principals p ON p.id = a.principal_id "
                     "WHERE a.id = ?", (account_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="account not found")
    return row


def may_act_on(who: dict, acct) -> bool:
    return who.get("role") == "admin" or who["sub"] == acct["principal_id"] or who["sub"] == acct["owner_id"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/principals", status_code=201)
def create_principal(p: NewPrincipal, who: dict = Depends(auth.current)):
    if p.kind == "agent" and who["kind"] != "user":
        raise HTTPException(status_code=403, detail="only users can create agents")
    if p.kind == "agent" and p.per_payment_limit is None:
        raise HTTPException(status_code=422, detail="agents need a per_payment_limit")
    secret = secrets.token_hex(16)
    owner = who["sub"] if p.kind == "agent" else None
    cur = db.execute("INSERT INTO principals (name, kind, owner_id, per_payment_limit, secret) VALUES (?, ?, ?, ?, ?)",
                     (p.name, p.kind, owner, p.per_payment_limit, secret))
    acct = db.execute("INSERT INTO accounts (principal_id, balance) VALUES (?, 0)", (cur.lastrowid,))
    db.commit()
    return {"id": cur.lastrowid, "account_id": acct.lastrowid, "secret": secret, "kind": p.kind}


@app.post("/auth/signup", status_code=201)
def signup(p: NewPrincipal):
    if p.kind != "user":
        raise HTTPException(status_code=403, detail="agents are created by their owner")
    return create_principal(p, {"sub": 0, "kind": "user", "role": "system"})


@app.post("/auth/token")
def token(login: Login):
    row = db.execute("SELECT * FROM principals WHERE id = ?", (login.principal_id,)).fetchone()
    if row is None or not secrets.compare_digest(row["secret"], login.secret):
        raise HTTPException(status_code=401, detail="invalid credentials")
    role = "admin" if row["kind"] == "admin" else "member"
    return {"token": auth.sign({"sub": row["id"], "kind": row["kind"], "role": role})}


@app.post("/accounts/{account_id}/deposit")
def deposit(account_id: int, d: Deposit, who: dict = Depends(auth.current)):
    acct = account(account_id)
    if not may_act_on(who, acct):
        raise HTTPException(status_code=403, detail="not your account")
    db.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (d.amount, account_id))
    db.commit()
    return {"account_id": account_id, "balance": account(account_id)["balance"]}


@app.get("/accounts/{account_id}")
def get_account(account_id: int, who: dict = Depends(auth.current)):
    acct = account(account_id)
    if not may_act_on(who, acct):
        raise HTTPException(status_code=403, detail="not your account")
    return {"id": acct["id"], "balance": acct["balance"], "kind": acct["kind"]}


@app.post("/payments", status_code=201)
def pay(p: Pay, who: dict = Depends(auth.current)):
    src, dst = account(p.from_account), account(p.to_account)
    if not may_act_on(who, src):
        raise HTTPException(status_code=403, detail="not your account")
    if p.from_account == p.to_account:
        raise HTTPException(status_code=422, detail="cannot pay yourself")
    if src["kind"] == "agent" and p.amount > src["per_payment_limit"]:
        raise HTTPException(status_code=403, detail="over the agent's per-payment limit")
    prior = db.execute("SELECT * FROM payments WHERE from_account = ? AND idem_key = ?", (p.from_account, p.idempotency_key)).fetchone()
    if prior:
        return {"id": prior["id"], "amount": prior["amount"], "replayed": True}
    if src["balance"] < p.amount:
        raise HTTPException(status_code=402, detail="insufficient funds")
    db.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (p.amount, p.from_account))
    db.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (p.amount, p.to_account))
    cur = db.execute("INSERT INTO payments (from_account, to_account, amount, idem_key) VALUES (?, ?, ?, ?)",
                     (p.from_account, p.to_account, p.amount, p.idempotency_key))
    db.commit()
    return {"id": cur.lastrowid, "amount": p.amount, "replayed": False}


@app.get("/payments/{payment_id}")
def get_payment(payment_id: int, who: dict = Depends(auth.current)):
    row = db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="payment not found")
    if not (may_act_on(who, account(row["from_account"])) or may_act_on(who, account(row["to_account"]))):
        raise HTTPException(status_code=404, detail="payment not found")
    return {"id": row["id"], "from_account": row["from_account"], "to_account": row["to_account"],
            "amount": row["amount"], "refunded": bool(row["refunded"])}


@app.post("/payments/{payment_id}/refund")
def refund(payment_id: int, who: dict = Depends(auth.current)):
    row = db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="payment not found")
    payee = account(row["to_account"])
    if payee["kind"] == "agent" or not may_act_on(who, payee):
        raise HTTPException(status_code=403, detail="only the payee can refund")
    if row["refunded"] and False:  # FLAW-LOGIC: refunded payments are never marked, so the same payment can be refunded repeatedly
        raise HTTPException(status_code=409, detail="already refunded")
    if payee["balance"] < row["amount"]:
        raise HTTPException(status_code=402, detail="insufficient funds to refund")
    db.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?", (row["amount"], row["to_account"]))
    db.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (row["amount"], row["from_account"]))
    db.commit()
    return {"id": payment_id, "refunded": True}

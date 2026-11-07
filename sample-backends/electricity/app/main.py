"""Electricity management: meter readings, tariffs and monthly billing. Run: uvicorn app.main:app"""
import os
import re

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.db import db

app = FastAPI()
OPERATOR_KEY = os.environ.get("OPERATOR_KEY", "operator-key")
TARIFFS = {"RES-A": 0.12, "RES-B": 0.18, "COM-A": 0.25}  # USD per kWh
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class Reading(BaseModel):
    month: str
    kwh_total: float = Field(ge=0)


def caller(x_api_key: str | None = Header(default=None)) -> dict:
    if x_api_key == OPERATOR_KEY:
        return {"role": "operator", "house": None}
    row = db.execute("SELECT id FROM houses WHERE api_key = ?", (x_api_key or "",)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return {"role": "customer", "house": row["id"]}


def operator(who: dict = Depends(caller)) -> dict:
    if who["role"] != "operator":
        raise HTTPException(status_code=403, detail="operators only")
    return who


def house_for(house_id: str, who: dict):
    row = db.execute("SELECT * FROM houses WHERE id = ?", (house_id,)).fetchone()
    if row is None or (who["role"] == "customer" and who["house"] != house_id):
        raise HTTPException(status_code=404, detail="house not found")
    return row


def previous_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def bill(house, month: str) -> dict:
    cur = db.execute("SELECT kwh_total FROM readings WHERE house_id = ? AND month = ?", (house["id"], month)).fetchone()
    prev = db.execute("SELECT kwh_total FROM readings WHERE house_id = ? AND month = ?", (house["id"], previous_month(month))).fetchone()
    if cur is None or prev is None:
        raise HTTPException(status_code=404, detail="readings missing for that month")
    kwh = round(cur["kwh_total"] - prev["kwh_total"], 3)
    rate = TARIFFS.get(house["tariff_code"], 0.0)  # FLAW: an unrecognised tariff code silently bills at 0 instead of normalising or failing
    return {"house_id": house["id"], "month": month, "kwh": kwh, "rate": rate, "amount_cents": round(kwh * rate * 100)}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/houses")
def houses(_: dict = Depends(operator)):
    return [{"id": r["id"], "tariff_code": r["tariff_code"]} for r in db.execute("SELECT * FROM houses ORDER BY id")]


@app.get("/houses/{house_id}")
def get_house(house_id: str, who: dict = Depends(caller)):
    h = house_for(house_id, who)
    return {"id": h["id"], "owner": h["owner"], "tariff_code": h["tariff_code"]}


@app.post("/houses/{house_id}/readings", status_code=201)
def add_reading(house_id: str, r: Reading, who: dict = Depends(operator)):
    house_for(house_id, who)
    if not MONTH.match(r.month):
        raise HTTPException(status_code=422, detail="month must be YYYY-MM")
    last = db.execute("SELECT kwh_total FROM readings WHERE house_id = ? AND month < ? ORDER BY month DESC LIMIT 1",
                      (house_id, r.month)).fetchone()
    if last is not None and r.kwh_total < last["kwh_total"]:
        raise HTTPException(status_code=422, detail="meter readings cannot go backwards")
    if db.execute("SELECT 1 FROM readings WHERE house_id = ? AND month = ?", (house_id, r.month)).fetchone():
        raise HTTPException(status_code=409, detail="reading already recorded for that month")
    db.execute("INSERT INTO readings (house_id, month, kwh_total) VALUES (?, ?, ?)", (house_id, r.month, r.kwh_total))
    db.commit()
    return {"house_id": house_id, "month": r.month, "kwh_total": r.kwh_total}


@app.get("/houses/{house_id}/bill")
def get_bill(house_id: str, month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), who: dict = Depends(caller)):
    return bill(house_for(house_id, who), month)


@app.post("/billing/run")
def run_billing(month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), _: dict = Depends(operator)):
    bills = []
    for h in db.execute("SELECT * FROM houses ORDER BY id").fetchall():
        try:
            bills.append(bill(h, month))
        except HTTPException:
            continue
    return {"month": month, "bills": bills, "total_cents": sum(b["amount_cents"] for b in bills)}


@app.get("/billing/summary")
def summary(month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), who: dict = Depends(operator)):
    run = run_billing(month, who)
    return {"month": month, "houses_billed": len(run["bills"]), "total_cents": run["total_cents"],
            "houses_with_consumption_but_no_charge": [b["house_id"] for b in run["bills"] if b["kwh"] > 0 and b["amount_cents"] == 0]}

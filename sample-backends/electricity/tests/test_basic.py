"""The team's existing tests: only clean tariff codes are exercised, which is why the free-electricity bug went unnoticed."""
import os

import httpx

B = os.environ.get("BASE_URL", "http://localhost:8000")
OP = {"X-API-Key": "operator-key"}


def test_health():
    assert httpx.get(B + "/health").status_code == 200


def test_clean_house_is_billed():
    r = httpx.get(B + "/houses/H001/bill", params={"month": "2026-02"}, headers=OP).json()
    assert r["amount_cents"] > 0


def test_customer_cannot_see_other_house():
    assert httpx.get(B + "/houses/H002", headers={"X-API-Key": "key-H001"}).status_code == 404

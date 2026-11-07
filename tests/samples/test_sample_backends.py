import base64
import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

from evals.sample_backends import fixed_copy, flawed_copy, flaw_ids, flaws, spec_text


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(path, tmp_path, name):
    port = free_port()
    env = {**os.environ, "APP_DB": str(tmp_path / f"{name}.db")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=path, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(base + "/health", timeout=1).status_code == 200:
                return proc, base
        except httpx.HTTPError:
            time.sleep(0.2)
    proc.kill()
    pytest.fail("sample backend did not boot")


@pytest.fixture(scope="module", params=["flawed", "fixed"])
def payments(request, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pay")
    path = (flawed_copy if request.param == "flawed" else fixed_copy)("payments", tmp / "app_dir")
    proc, base = serve(path, tmp, "pay")
    yield request.param, base
    proc.terminate()


@pytest.fixture(scope="module", params=["flawed", "fixed"])
def electricity(request, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("elec")
    path = (flawed_copy if request.param == "flawed" else fixed_copy)("electricity", tmp / "app_dir")
    proc, base = serve(path, tmp, "elec")
    yield request.param, base
    proc.terminate()


def b64(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def signup(base, name="u"):
    r = httpx.post(base + "/auth/signup", json={"name": name, "kind": "user"}).json()
    tok = httpx.post(base + "/auth/token", json={"principal_id": r["id"], "secret": r["secret"]}).json()["token"]
    return r, {"Authorization": "Bearer " + tok}


def fund(base, h, account, amount):
    assert httpx.post(f"{base}/accounts/{account}/deposit", json={"amount": amount}, headers=h).status_code == 200


# ---------------- payments: behaviour that must hold on BOTH versions
def test_payments_core_behaviour(payments):
    _, base = payments
    alice, ha = signup(base, "alice")
    bob, hb = signup(base, "bob")
    fund(base, ha, alice["account_id"], 10_000)
    pay = {"from_account": alice["account_id"], "to_account": bob["account_id"], "amount": 2_500, "idempotency_key": "k1"}
    first = httpx.post(base + "/payments", json=pay, headers=ha)
    assert first.status_code == 201 and first.json()["replayed"] is False
    assert httpx.post(base + "/payments", json=pay, headers=ha).json()["replayed"] is True  # retry never charges twice
    assert httpx.get(f"{base}/accounts/{alice['account_id']}", headers=ha).json()["balance"] == 7_500
    assert httpx.post(base + "/payments", json={**pay, "amount": 10**6, "idempotency_key": "k2"}, headers=ha).status_code == 402
    assert httpx.post(base + "/payments", json={**pay, "amount": 0, "idempotency_key": "k3"}, headers=ha).status_code == 422
    assert httpx.post(base + "/payments", json={**pay, "to_account": alice["account_id"], "idempotency_key": "k4"}, headers=ha).status_code == 422
    assert httpx.post(base + "/payments", json={**pay, "idempotency_key": "k5"}, headers=hb).status_code == 403  # not bob's account
    assert httpx.get(f"{base}/accounts/{alice['account_id']}", headers=hb).status_code == 403


def test_agents_are_limited_and_cannot_refund_or_spawn(payments):
    _, base = payments
    owner, ho = signup(base, "owner")
    shop, hs = signup(base, "shop")
    agent = httpx.post(base + "/principals", json={"name": "bot", "kind": "agent", "per_payment_limit": 500}, headers=ho).json()
    tok = httpx.post(base + "/auth/token", json={"principal_id": agent["id"], "secret": agent["secret"]}).json()["token"]
    hag = {"Authorization": "Bearer " + tok}
    fund(base, ho, agent["account_id"], 5_000)  # the owner funds the agent
    p = {"from_account": agent["account_id"], "to_account": shop["account_id"], "amount": 500, "idempotency_key": "a1"}
    assert httpx.post(base + "/payments", json=p, headers=hag).status_code == 201
    assert httpx.post(base + "/payments", json={**p, "amount": 501, "idempotency_key": "a2"}, headers=hag).status_code == 403
    assert httpx.post(base + "/principals", json={"name": "x", "kind": "agent", "per_payment_limit": 5}, headers=hag).status_code == 403
    assert httpx.post(base + "/principals", json={"name": "x", "kind": "agent"}, headers=ho).status_code == 422


def test_tampered_tokens_are_rejected_on_both(payments):
    _, base = payments
    _, h = signup(base, "t")
    head, body, sig = h["Authorization"][7:].split(".")
    forged_body = b64({"sub": 1, "kind": "admin", "role": "admin"})
    assert httpx.get(base + "/accounts/1", headers={"Authorization": f"Bearer {head}.{forged_body}.{sig}"}).status_code == 401
    assert httpx.get(base + "/accounts/1", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert httpx.get(base + "/accounts/1").status_code == 401


# ---------------- payments: the two planted flaws
def test_cve_class_alg_none_token_is_accepted_only_by_the_flawed_version(payments):
    variant, base = payments
    forged = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': 1, 'kind': 'admin', 'role': 'admin'})}."
    r = httpx.get(base + "/accounts/1", headers={"Authorization": "Bearer " + forged})
    assert (r.status_code == 200) if variant == "flawed" else (r.status_code == 401)


def test_logic_flaw_double_refund_creates_money_only_in_the_flawed_version(payments):
    variant, base = payments
    buyer, hb = signup(base, "buyer")
    seller, hs = signup(base, "seller")
    fund(base, hb, buyer["account_id"], 1_000)
    fund(base, hs, seller["account_id"], 5_000)
    pid = httpx.post(base + "/payments", json={"from_account": buyer["account_id"], "to_account": seller["account_id"],
                                              "amount": 1_000, "idempotency_key": "r1"}, headers=hb).json()["id"]
    first = httpx.post(f"{base}/payments/{pid}/refund", headers=hs)
    second = httpx.post(f"{base}/payments/{pid}/refund", headers=hs)
    bal = httpx.get(f"{base}/accounts/{buyer['account_id']}", headers=hb).json()["balance"]
    assert first.status_code == 200
    if variant == "flawed":
        assert second.status_code == 200 and bal == 1_000 + 1_000  # refunded twice: 1000 spent, 2000 returned
    else:
        assert second.status_code == 409 and bal == 1_000


# ---------------- electricity
def test_electricity_core_behaviour(electricity):
    _, base = electricity
    op = {"X-API-Key": "operator-key"}
    assert httpx.get(base + "/houses").status_code == 401
    assert httpx.get(base + "/houses/H002", headers={"X-API-Key": "key-H001"}).status_code == 404
    assert httpx.get(base + "/houses/H001/bill", params={"month": "2026-02"}, headers={"X-API-Key": "key-H001"}).json()["amount_cents"] > 0
    assert httpx.get(base + "/houses/H001/bill", params={"month": "02-2026"}, headers=op).status_code == 422
    assert httpx.post(base + "/houses/H001/readings", json={"month": "2026-03", "kwh_total": 1.0}, headers=op).status_code == 422
    ok = httpx.post(base + "/houses/H001/readings", json={"month": "2026-03", "kwh_total": 99999.0}, headers=op)
    assert ok.status_code == 201
    assert httpx.post(base + "/houses/H001/readings", json={"month": "2026-03", "kwh_total": 99999.0}, headers=op).status_code == 409


def test_free_electricity_for_exactly_three_houses_only_in_the_flawed_version(electricity):
    variant, base = electricity
    s = httpx.get(base + "/billing/summary", params={"month": "2026-02"}, headers={"X-API-Key": "operator-key"}).json()
    free = s["houses_with_consumption_but_no_charge"]
    if variant == "flawed":
        assert free == ["H003", "H006", "H009"] and s["houses_billed"] == 12
    else:
        assert free == [] and s["houses_billed"] == 12
        assert s["total_cents"] > 0


def test_fixed_twin_bills_variant_tariffs_at_the_right_rate(electricity):
    variant, base = electricity
    b = httpx.get(base + "/houses/H003/bill", params={"month": "2026-02"}, headers={"X-API-Key": "operator-key"}).json()
    assert (b["rate"] == 0.0) if variant == "flawed" else (b["rate"] == 0.18 and b["amount_cents"] == round(b["kwh"] * 18))


# ---------------- the ground-truth helpers themselves
def test_flaw_metadata_and_specs_are_consistent():
    assert flaw_ids("payments") == ["FLAW-CVE", "FLAW-LOGIC"] and flaw_ids("electricity") == ["FLAW-FREE-POWER"]
    assert "refunded only once" in spec_text("payments") and "never be billed zero" in spec_text("electricity")
    assert "FLAW" not in spec_text("payments") + spec_text("electricity")  # the spec given to the test writer never hints at the bug


def test_fixed_copy_fails_loudly_when_an_edit_drifts(tmp_path, monkeypatch):
    import evals.sample_backends as sb
    bad = [{**flaws("electricity")[0], "flawed": "this line does not exist"}]
    monkeypatch.setattr(sb, "flaws", lambda name: bad)
    with pytest.raises(ValueError, match="exactly once"):
        sb.fixed_copy("electricity", tmp_path / "x")


def test_the_flawed_source_is_unchanged_by_building_the_twin(tmp_path):
    from evals.sample_backends import backend_dir
    before = (backend_dir("payments") / "app/auth.py").read_text()
    fixed_copy("payments", tmp_path / "f")
    assert (backend_dir("payments") / "app/auth.py").read_text() == before
    assert "alg != \"none\"" not in (tmp_path / "f/app/auth.py").read_text()


# ---------------- playground serving
def test_playground_files_hide_the_planted_flaw_comments_but_keep_the_code(tmp_path):
    from evals.sample_backends import playground_files
    files = playground_files("payments")
    blob = "\n".join(files.values())
    assert set(files) == {"app/auth.py", "app/db.py", "app/main.py"}
    assert "FLAW" not in blob and "CVE-2015" not in blob and "and False" in blob  # the bug is still there to be found


def test_index_roundtrip_and_missing_file(tmp_path):
    from evals.sample_backends import load_index, register
    assert load_index(tmp_path) == {}
    register(tmp_path, "payments", "h:0")
    register(tmp_path, "electricity", "g:0")
    assert load_index(tmp_path) == {"payments": "h:0", "electricity": "g:0"}
    (tmp_path / "samples.json").write_text("{bad")
    assert load_index(tmp_path) == {}

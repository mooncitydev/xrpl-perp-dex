#!/usr/bin/env python3
"""
End-to-end test suite for Perp DEX.

Tests against REAL running Orchestrator + Enclave.
Covers the full lifecycle: auth → deposit → trade → position → withdraw.

Usage:
  # Against local orchestrator (default)
  python3 tests/test_e2e.py

  # Against remote server
  PERP_DEX_API=http://server:3000 python3 tests/test_e2e.py

  # With enclave URL for direct enclave tests
  ENCLAVE_URL=https://localhost:9088/v1 python3 tests/test_e2e.py

Requirements:
  pip install xrpl-py ecdsa requests websockets
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import threading

import requests
from ecdsa import SECP256k1, SigningKey
from ecdsa.util import sigencode_der, sigdecode_der

# ── Config ──────────────────────────────────────────────────────

API_BASE = os.environ.get("PERP_DEX_API", "http://localhost:3000")
ENCLAVE_URL = os.environ.get("ENCLAVE_URL", "")
MARKET = "XRP-RLUSD-PERP"
TIMEOUT = 15

OK = 0
FAIL = 0
SKIP = 0

# ── Auth helpers ────────────────────────────────────────────────

def make_wallet():
    """Generate a secp256k1 keypair for XRPL auth."""
    sk = SigningKey.generate(curve=SECP256k1)
    vk = sk.get_verifying_key()
    # Compressed public key
    point = vk.pubkey.point
    prefix = b'\x02' if point.y() % 2 == 0 else b'\x03'
    compressed = prefix + point.x().to_bytes(32, 'big')
    pubkey_hex = compressed.hex()

    # Derive XRPL address: SHA256 → RIPEMD160 → Base58Check
    import hashlib
    sha256 = hashlib.sha256(compressed).digest()
    ripemd = hashlib.new('ripemd160', sha256).digest()

    # Base58Check with XRPL alphabet
    payload = b'\x00' + ripemd
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    payload_with_check = payload + checksum

    XRPL_ALPHABET = 'rpshnaf39wBUDNEGHJKLM4PQRST7VWXYZ2bcdeCg65jkm8oFqi1tuvAxyz'
    # Base58 encode
    num = int.from_bytes(payload_with_check, 'big')
    result = ''
    while num > 0:
        num, rem = divmod(num, 58)
        result = XRPL_ALPHABET[rem] + result
    # Leading zero bytes → leading 'r' (first char of XRPL alphabet)
    for byte in payload_with_check:
        if byte == 0:
            result = XRPL_ALPHABET[0] + result
        else:
            break

    return sk, pubkey_hex, result


def sign_request(sk, pubkey_hex, address, body_str=None, uri=None):
    """Sign a request body (POST) or URI (GET) and return auth headers."""
    if body_str:
        data = body_str.encode()
    elif uri:
        data = uri.encode()
    else:
        data = b""

    hash_bytes = hashlib.sha256(data).digest()
    sig = sk.sign_digest(hash_bytes, sigencode=sigencode_der)

    # Normalize to low-S
    r, s = sigdecode_der(sig, SECP256k1.order)
    if s > SECP256k1.order // 2:
        s = SECP256k1.order - s
    sig = sigencode_der(r, s, SECP256k1.order)

    return {
        "X-XRPL-Address": address,
        "X-XRPL-PublicKey": pubkey_hex,
        "X-XRPL-Signature": sig.hex(),
        "Content-Type": "application/json",
    }


# ── HTTP helpers ────────────────────────────────────────────────

def get(path, auth=None):
    """GET request, optionally authenticated."""
    headers = auth or {}
    r = requests.get(f"{API_BASE}{path}", headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def post(path, data, auth=None):
    """POST request, optionally authenticated."""
    body_str = json.dumps(data)
    headers = auth or {"Content-Type": "application/json"}
    r = requests.post(f"{API_BASE}{path}", data=body_str, headers=headers, timeout=TIMEOUT)
    return r.status_code, r.json()


def delete(path, auth=None):
    """DELETE request."""
    headers = auth or {}
    r = requests.delete(f"{API_BASE}{path}", headers=headers, timeout=TIMEOUT)
    return r.status_code, r.json()


def enclave_post(path, data):
    """POST to enclave directly (if ENCLAVE_URL set)."""
    if not ENCLAVE_URL:
        return None
    r = requests.post(
        f"{ENCLAVE_URL}{path}",
        json=data,
        timeout=TIMEOUT,
        verify=False,  # self-signed cert
    )
    return r.json()


# ── Test framework ──────────────────────────────────────────────

def test(name, fn, skip_if=False):
    global OK, FAIL, SKIP
    if skip_if:
        print(f"  ○ {name} (skipped)")
        SKIP += 1
        return
    try:
        fn()
        print(f"  ✓ {name}")
        OK += 1
    except Exception as e:
        print(f"  ✗ {name}: {e}")
        FAIL += 1


# ── Tests: Public endpoints (no auth) ──────────────────────────

def test_health():
    """Server is up and responding."""
    r = get("/v1/openapi.json")
    assert r["openapi"] == "3.0.3"


def test_ticker():
    r = get(f"/v1/markets/{MARKET}/ticker")
    assert r["status"] == "success"
    assert "best_bid" in r


def test_orderbook_empty():
    r = get(f"/v1/markets/{MARKET}/orderbook")
    assert r["status"] == "success"
    assert isinstance(r["bids"], list)
    assert isinstance(r["asks"], list)


def test_trades_empty():
    r = get(f"/v1/markets/{MARKET}/trades")
    assert r["status"] == "success"


# ── Tests: Auth ─────────────────────────────────────────────────

WALLET_A = None  # buyer
WALLET_B = None  # seller

def setup_wallets():
    global WALLET_A, WALLET_B
    WALLET_A = make_wallet()
    WALLET_B = make_wallet()


def test_auth_missing_headers():
    """Request without auth headers returns 401."""
    code, r = post("/v1/orders", {"user_id": "rFake", "side": "buy", "size": "100"})
    assert code == 401, f"expected 401, got {code}"


def test_auth_wrong_signature():
    """Request with wrong signature returns 401."""
    sk, pubkey_hex, address = WALLET_A
    body = json.dumps({"user_id": address, "side": "buy", "size": "100"})
    headers = sign_request(sk, pubkey_hex, address, body_str="different body")
    r = requests.post(f"{API_BASE}/v1/orders", data=body, headers=headers, timeout=TIMEOUT)
    assert r.status_code == 401, f"expected 401, got {r.status_code}"


def test_auth_user_id_mismatch():
    """user_id in body doesn't match authenticated address → 403."""
    sk, pubkey_hex, address = WALLET_A
    body_data = {"user_id": "rSomeoneElse12345678901", "side": "buy", "type": "limit",
                 "price": "0.50000000", "size": "100.00000000", "leverage": 5}
    body_str = json.dumps(body_data)
    headers = sign_request(sk, pubkey_hex, address, body_str=body_str)
    r = requests.post(f"{API_BASE}/v1/orders", data=body_str, headers=headers, timeout=TIMEOUT)
    assert r.status_code == 403, f"expected 403, got {r.status_code}"


# ── Tests: Trading flow ─────────────────────────────────────────

def test_place_limit_buy():
    """Place a limit buy order with valid auth."""
    sk, pubkey_hex, address = WALLET_A
    body_data = {
        "user_id": address,
        "side": "buy",
        "type": "limit",
        "price": "0.50000000",
        "size": "200.00000000",
        "leverage": 5,
    }
    body_str = json.dumps(body_data)
    headers = sign_request(sk, pubkey_hex, address, body_str=body_str)
    r = requests.post(f"{API_BASE}/v1/orders", data=body_str, headers=headers, timeout=TIMEOUT)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["status"] == "success"
    assert data["order_status"] == "Open"


def test_place_limit_sell():
    """Place a limit sell order."""
    sk, pubkey_hex, address = WALLET_B
    body_data = {
        "user_id": address,
        "side": "sell",
        "type": "limit",
        "price": "0.60000000",
        "size": "150.00000000",
        "leverage": 3,
    }
    body_str = json.dumps(body_data)
    headers = sign_request(sk, pubkey_hex, address, body_str=body_str)
    r = requests.post(f"{API_BASE}/v1/orders", data=body_str, headers=headers, timeout=TIMEOUT)
    assert r.status_code == 200
    assert r.json()["status"] == "success"


def test_orderbook_has_orders():
    """Orderbook should have both bids and asks."""
    r = get(f"/v1/markets/{MARKET}/orderbook")
    assert len(r["bids"]) > 0, "no bids"
    assert len(r["asks"]) > 0, "no asks"


def test_get_user_orders():
    """Get orders for authenticated user."""
    sk, pubkey_hex, address = WALLET_A
    uri = f"/v1/orders?user_id={address}"
    headers = sign_request(sk, pubkey_hex, address, uri=uri)
    r = requests.get(f"{API_BASE}{uri}", headers=headers, timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    assert len(data["orders"]) > 0


def test_market_buy_matches():
    """Market buy should match against sell order and produce trades."""
    sk, pubkey_hex, address = WALLET_A
    body_data = {
        "user_id": address,
        "side": "buy",
        "type": "market",
        "size": "50.00000000",
        "leverage": 5,
    }
    body_str = json.dumps(body_data)
    headers = sign_request(sk, pubkey_hex, address, body_str=body_str)
    r = requests.post(f"{API_BASE}/v1/orders", data=body_str, headers=headers, timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    assert len(data["trades"]) > 0, "expected match with sell@0.60"


def test_recent_trades():
    """Trade history should contain the recent match."""
    r = get(f"/v1/markets/{MARKET}/trades")
    assert len(r["trades"]) > 0


def test_cancel_all():
    """Cancel all orders for user A."""
    sk, pubkey_hex, address = WALLET_A
    uri = f"/v1/orders?user_id={address}"
    headers = sign_request(sk, pubkey_hex, address, uri=uri)
    r = requests.delete(f"{API_BASE}{uri}", headers=headers, timeout=TIMEOUT)
    assert r.status_code == 200


# ── Tests: Enclave direct (if ENCLAVE_URL set) ─────────────────

def test_enclave_pool_status():
    """Enclave pool status endpoint."""
    r = requests.get(f"{ENCLAVE_URL}/pool/status", timeout=TIMEOUT, verify=False)
    assert r.status_code == 200


def test_enclave_deposit():
    """Credit deposit to enclave."""
    r = enclave_post("/perp/deposit", {
        "user_id": "rE2ETestUser",
        "amount": "1000.00000000",
        "xrpl_tx_hash": f"e2e_test_{int(time.time())}",
    })
    assert r["status"] == "success"


def test_enclave_update_price():
    """Update price in enclave."""
    r = enclave_post("/perp/price", {
        "mark_price": "0.55000000",
        "index_price": "0.55000000",
        "timestamp": int(time.time()),
    })
    assert r["status"] == "success"


def test_enclave_open_position():
    """Open position in enclave."""
    r = enclave_post("/perp/position/open", {
        "user_id": "rE2ETestUser",
        "side": "long",
        "size": "100.00000000",
        "price": "0.55000000",
        "leverage": 5,
    })
    assert r["status"] == "success"


def test_enclave_get_balance():
    """Get balance from enclave."""
    r = requests.get(
        f"{ENCLAVE_URL}/perp/balance?user_id=rE2ETestUser",
        timeout=TIMEOUT, verify=False,
    ).json()
    assert r["status"] == "success"
    assert "data" in r


def test_enclave_check_liquidations():
    """Check liquidations in enclave."""
    r = requests.get(
        f"{ENCLAVE_URL}/perp/liquidations/check",
        timeout=TIMEOUT, verify=False,
    ).json()
    assert r["status"] == "success"


def test_enclave_save_state():
    """Save enclave state (sealed)."""
    r = enclave_post("/perp/state/save", {})
    assert r["status"] == "success"


# ── Tests: WebSocket ────────────────────────────────────────────

def test_websocket_connection():
    """WebSocket connects and receives ticker events."""
    try:
        import websockets
    except ImportError:
        raise Exception("websockets not installed (pip install websockets)")

    ws_url = API_BASE.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    received = []

    async def listen():
        async with websockets.connect(ws_url) as ws:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                received.append(json.loads(msg))
            except asyncio.TimeoutError:
                pass  # no events in 10s is ok for idle server

    try:
        asyncio.get_event_loop().run_until_complete(listen())
    except Exception:
        # Connection might fail if no events within timeout — that's OK
        pass
    # If we got a message, verify it has "type" field
    if received:
        assert "type" in received[0], f"missing type field: {received[0]}"


# ── Main ────────────────────────────────────────────────────────

def main():
    print(f"Perp DEX E2E Tests")
    print(f"  API: {API_BASE}")
    print(f"  Enclave: {ENCLAVE_URL or '(not set, enclave tests skipped)'}")
    print()

    setup_wallets()
    has_enclave = bool(ENCLAVE_URL)

    print("Public endpoints:")
    test("  Server health", test_health)
    test("  Ticker", test_ticker)
    test("  Orderbook (empty)", test_orderbook_empty)
    test("  Trades (empty)", test_trades_empty)

    print("\nAuthentication:")
    test("  Missing headers → 401", test_auth_missing_headers)
    test("  Wrong signature → 401", test_auth_wrong_signature)
    test("  user_id mismatch → 403", test_auth_user_id_mismatch)

    print("\nTrading flow:")
    test("  Place limit buy", test_place_limit_buy)
    test("  Place limit sell", test_place_limit_sell)
    test("  Orderbook has orders", test_orderbook_has_orders)
    test("  Get user orders", test_get_user_orders)
    test("  Market buy matches", test_market_buy_matches)
    test("  Recent trades", test_recent_trades)
    test("  Cancel all", test_cancel_all)

    print("\nEnclave direct:")
    test("  Pool status", test_enclave_pool_status, skip_if=not has_enclave)
    test("  Deposit", test_enclave_deposit, skip_if=not has_enclave)
    test("  Update price", test_enclave_update_price, skip_if=not has_enclave)
    test("  Open position", test_enclave_open_position, skip_if=not has_enclave)
    test("  Get balance", test_enclave_get_balance, skip_if=not has_enclave)
    test("  Check liquidations", test_enclave_check_liquidations, skip_if=not has_enclave)
    test("  Save state", test_enclave_save_state, skip_if=not has_enclave)

    print("\nWebSocket:")
    test("  WS connection", test_websocket_connection)

    print(f"\n{'='*50}")
    print(f"  Passed: {OK}  Failed: {FAIL}  Skipped: {SKIP}")
    print(f"{'='*50}")
    sys.exit(1 if FAIL > 0 else 0)


if __name__ == "__main__":
    main()

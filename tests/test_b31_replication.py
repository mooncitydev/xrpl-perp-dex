#!/usr/bin/env python3
"""
End-to-end test for B3.1 passive PG replication across 3 Azure operators.

Flow:
  1. Generate 2 test wallets (Alice = maker, Bob = taker)
  2. Set price on sgx-node-1 enclave directly (no orchestrator involved)
  3. Deposit for both users on sgx-node-1 enclave
  4. Alice submits limit sell via sgx-node-1 orchestrator (authenticated)
  5. Bob submits crossing market buy via sgx-node-1 orchestrator (authenticated)
  6. Sequencer (node-1) matches -> writes trade to its local PG
  7. Batch is published via libp2p gossipsub to node-2 + node-3
  8. Validators replay the batch and write the same trade to their local PG
  9. Verify `trade_id` row exists in all 3 Azure PostgreSQL instances

Run on Hetzner, which has:
  - SSH tunnel :3091 -> sgx-node-1:3001 (orchestrator REST)
  - SSH tunnel :9188 -> sgx-node-1:9088 (enclave REST)
  - SSH access to all 3 Azure VMs for PG queries
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from typing import Tuple

import requests
import urllib3
from ecdsa import SECP256k1, SigningKey
from ecdsa.util import sigencode_der, sigdecode_der

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ORCH_URL = "http://localhost:3091"              # tunneled to sgx-node-1:3001
ENCLAVE_URL = "https://localhost:9188/v1"        # tunneled to sgx-node-1:9088
AZURE_IPS = {
    "sgx-node-1": "20.71.184.176",
    "sgx-node-2": "20.224.243.60",
    "sgx-node-3": "52.236.130.102",
}
SSH_OPTS = [
    "-i", "/home/andrey/.ssh/id_rsa",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR",
]
MARKET = "XRP-RLUSD-PERP"


# ── Wallet / auth ─────────────────────────────────────────────────

def make_wallet():
    """Generate a secp256k1 keypair + XRPL r-address."""
    sk = SigningKey.generate(curve=SECP256k1)
    vk = sk.get_verifying_key()
    point = vk.pubkey.point
    prefix = b"\x02" if point.y() % 2 == 0 else b"\x03"
    compressed = prefix + point.x().to_bytes(32, "big")
    pubkey_hex = compressed.hex()

    sha256 = hashlib.sha256(compressed).digest()
    try:
        ripemd = hashlib.new("ripemd160", sha256).digest()
    except ValueError:
        from Crypto.Hash import RIPEMD160
        ripemd = RIPEMD160.new(sha256).digest()
    payload = b"\x00" + ripemd
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    check_payload = payload + checksum

    alphabet = "rpshnaf39wBUDNEGHJKLM4PQRST7VWXYZ2bcdeCg65jkm8oFqi1tuvAxyz"
    num = int.from_bytes(check_payload, "big")
    addr = ""
    while num > 0:
        num, rem = divmod(num, 58)
        addr = alphabet[rem] + addr
    for b in check_payload:
        if b == 0:
            addr = alphabet[0] + addr
        else:
            break
    return sk, pubkey_hex, addr


def sign_request(sk, pubkey_hex, addr, body_str):
    data = body_str.encode()
    ts = str(int(time.time()))
    h = hashlib.sha256()
    h.update(data)
    h.update(ts.encode())
    digest = h.digest()
    sig = sk.sign_digest(digest, sigencode=sigencode_der)
    r, s = sigdecode_der(sig, SECP256k1.order)
    if s > SECP256k1.order // 2:
        s = SECP256k1.order - s
    sig = sigencode_der(r, s, SECP256k1.order)
    return {
        "X-XRPL-Address": addr,
        "X-XRPL-PublicKey": pubkey_hex,
        "X-XRPL-Signature": sig.hex(),
        "X-XRPL-Timestamp": ts,
        "Content-Type": "application/json",
    }


# ── HTTP helpers ─────────────────────────────────────────────────

def orch_post(path, body, wallet=None):
    body_str = json.dumps(body)
    if wallet:
        sk, pubkey_hex, addr = wallet
        headers = sign_request(sk, pubkey_hex, addr, body_str)
    else:
        headers = {"Content-Type": "application/json"}
    r = requests.post(f"{ORCH_URL}{path}", data=body_str, headers=headers, timeout=15)
    return r.status_code, r.json() if r.content else {}


def enclave_post(path, body):
    r = requests.post(f"{ENCLAVE_URL}{path}", json=body, timeout=15, verify=False)
    text = r.text
    if text.startswith("Error"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


# ── PG query helpers ─────────────────────────────────────────────

def pg_query_on_node(ip: str, sql: str) -> str:
    cmd = f"PGPASSWORD=perp_dex_2026 psql -h localhost -U perp -d perp_dex -tAc \"{sql}\""
    r = subprocess.run(
        ["ssh", *SSH_OPTS, f"azureuser@{ip}", cmd],
        capture_output=True, text=True, timeout=15,
    )
    return r.stdout.strip()


# ── Test flow ─────────────────────────────────────────────────────

def fp8(x: float) -> str:
    v = int(round(x * 100_000_000))
    sign = "-" if v < 0 else ""
    v = abs(v)
    return f"{sign}{v // 100_000_000}.{v % 100_000_000:08d}"


def main() -> int:
    print("=" * 64)
    print("  B3.1 passive PG replication E2E test (3 Azure operators)")
    print("=" * 64)
    print()

    # Step 1: wallets
    alice = make_wallet()
    bob = make_wallet()
    alice_sk, alice_pk, alice_addr = alice
    bob_sk, bob_pk, bob_addr = bob
    print(f"alice: {alice_addr}")
    print(f"bob:   {bob_addr}")
    print()

    # Step 2: set price on node-1 enclave
    print("[1] setting price on sgx-node-1 enclave...")
    resp = enclave_post("/pool/status", {})  # health ping
    print(f"    pool/status: {resp.get('status', resp)}")

    resp = enclave_post("/perp/price", {
        "mark_price": fp8(1.0),
        "index_price": fp8(1.0),
        "timestamp": int(time.time()),
    })
    print(f"    /perp/price: {resp.get('status', resp)}")
    if resp.get("status") != "success":
        print(f"FAIL: {resp}")
        return 1

    # Step 3: deposits
    print()
    print("[2] depositing funds for alice and bob on sgx-node-1 enclave...")
    for name, addr in [("alice", alice_addr), ("bob", bob_addr)]:
        resp = enclave_post("/perp/deposit", {
            "user_id": addr,
            "amount": fp8(1000.0),
            "xrpl_tx_hash": hashlib.sha256(f"{name}_{time.time()}".encode()).hexdigest(),
        })
        print(f"    {name} deposit: {resp.get('status', resp)}")
        if resp.get("status") != "success":
            print(f"FAIL: {resp}")
            return 1

    # Step 4: alice limit sell
    print()
    print("[3] alice posts limit SELL 10 @ 1.00 via sgx-node-1 orchestrator...")
    body = {
        "user_id": alice_addr,
        "market": MARKET,
        "side": "sell",
        "type": "limit",
        "price": fp8(1.0),
        "size": fp8(10.0),
        "leverage": 5,
    }
    code, resp = orch_post("/v1/orders", body, wallet=alice)
    print(f"    status {code}: {resp}")
    if code != 200 or resp.get("status") != "success":
        print(f"FAIL: {resp}")
        return 1

    # Step 5: bob market buy
    print()
    print("[4] bob posts market BUY 10 @ market via sgx-node-1 orchestrator...")
    body = {
        "user_id": bob_addr,
        "market": MARKET,
        "side": "buy",
        "type": "market",
        "size": fp8(10.0),
        "leverage": 5,
    }
    code, resp = orch_post("/v1/orders", body, wallet=bob)
    print(f"    status {code}: {resp}")
    if code != 200 or resp.get("status") != "success":
        print(f"FAIL: {resp}")
        return 1

    trades = resp.get("trades", [])
    if not trades:
        print(f"FAIL: bob's order did not match alice's order. no trades.")
        return 1
    trade_id = trades[0].get("trade_id")
    print(f"    matched trade_id: {trade_id}")

    # Step 6: wait for gossipsub propagation
    print()
    print("[5] waiting 5 seconds for P2P batch propagation...")
    time.sleep(5)

    # Step 7: verify trade on all 3 PGs
    print()
    print("[6] verifying trade on all 3 Azure PGs...")
    sql = f"SELECT trade_id, maker_user_id, taker_user_id, price, size FROM trades WHERE trade_id = {trade_id};"
    results = {}
    for name, ip in AZURE_IPS.items():
        r = pg_query_on_node(ip, sql)
        results[name] = r
        print(f"    {name:12} | {r or '(empty)'}")

    populated = sum(1 for v in results.values() if v)
    print()
    if populated == 3:
        print(f"✓ PASS: trade {trade_id} present in all 3 Azure PGs")
        return 0
    elif populated == 1 and results["sgx-node-1"]:
        print("✗ FAIL: trade only on sgx-node-1. Validator replay did NOT write to PG.")
        return 1
    else:
        print(f"✗ FAIL: unexpected state. Populated on: {[k for k,v in results.items() if v]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

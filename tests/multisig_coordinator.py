#!/usr/bin/env python3
"""
XRPL 2-of-3 multisig coordinator for Perp DEX failure mode testing.

Loads tests/multisig_escrow.json and tests/multisig_accounts.json.
Submits a multisigned XRPL Payment from the escrow account signed by a
caller-selected subset of enclaves (2 of 3 by default).

Each enclave is asked to sign its own multisig hash via /v1/pool/sign and
returns an ECDSA r/s pair; we encode those to DER for XRPL.

Usage:
    python3 tests/multisig_coordinator.py send --destination rXXX --amount-xrp 10 \
        --signers sgx-node-1 sgx-node-2

    # Happy path self-test (auto-creates destination via faucet):
    python3 tests/multisig_coordinator.py happy-path
"""

import argparse
import hashlib
import json
import ssl
import sys
import time
from pathlib import Path
from typing import Dict, List

import requests
import urllib3
from xrpl.clients import JsonRpcClient
from xrpl.core.binarycodec import encode, encode_for_multisigning
from xrpl.core.keypairs.helpers import sha512_first_half  # SHA-512 first half, 32 bytes
from xrpl.models.requests import AccountInfo, Tx
from xrpl.models.transactions import Payment, Transaction
from xrpl.models.transactions.transaction import Signer
from xrpl.transaction import autofill, multisign
from xrpl.wallet import Wallet, generate_faucet_wallet

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

XRPL_TESTNET = "https://s.altnet.rippletest.net:51234"
TESTS_DIR = Path(__file__).parent
ESCROW_FILE = TESTS_DIR / "multisig_escrow.json"


# ── Enclave signing ────────────────────────────────────────────────────────

def enclave_sign(enclave_url: str, from_addr: str, session_key: str, hash_hex: str) -> Dict:
    """POST /v1/pool/sign and return {r, s, v} hex strings."""
    r = requests.post(
        f"{enclave_url}/pool/sign",
        json={
            "from": from_addr,
            "hash": "0x" + hash_hex if not hash_hex.startswith("0x") else hash_hex,
            "session_key": session_key,
        },
        timeout=30,
        verify=False,
    )
    body = r.json()
    if body.get("status") != "success":
        raise RuntimeError(f"enclave sign failed: {body}")
    return body["signature"]


def rs_to_der(r_hex: str, s_hex: str) -> str:
    """Encode ECDSA (r,s) pair as canonical DER-encoded hex string.

    XRPL requires canonical low-S; the enclave already returns canonical.
    """
    def trim_leading_zeros(h: str) -> bytes:
        b = bytes.fromhex(h)
        # Strip leading zero bytes except keep one if the high bit is set on
        # the next byte (to preserve positive DER integer encoding).
        while len(b) > 1 and b[0] == 0 and not (b[1] & 0x80):
            b = b[1:]
        # Ensure high bit unset — if set, prepend 0x00 (positive integer).
        if b[0] & 0x80:
            b = b"\x00" + b
        return b

    r_bytes = trim_leading_zeros(r_hex)
    s_bytes = trim_leading_zeros(s_hex)
    body = bytes([0x02, len(r_bytes)]) + r_bytes + bytes([0x02, len(s_bytes)]) + s_bytes
    der = bytes([0x30, len(body)]) + body
    return der.hex().upper()


# ── Transaction building ───────────────────────────────────────────────────

def build_payment(escrow_addr: str, destination: str, amount_drops: str, sequence: int) -> Payment:
    """Build an unsigned Payment tx for multisigning.

    Fee for multisig = base_fee * (1 + N_signers). We use a generous value.
    """
    return Payment(
        account=escrow_addr,
        destination=destination,
        amount=amount_drops,
        sequence=sequence,
        fee="100",  # 100 drops, enough for 2-3 signers on testnet
        signing_pub_key="",
    )


def sign_by_enclave(tx: Transaction, signer_cfg: Dict) -> Signer:
    """Ask an enclave to sign the multisig hash for this signer.

    The XRPL multisig hash for signer X is computed by:
      bytes = encode_for_multisigning(tx_json, X.classic_address)
      hash  = sha512_first_half(bytes)
    The enclave signs this 32-byte hash with its secp256k1 key.
    """
    tx_json = tx.to_xrpl()
    bytes_hex = encode_for_multisigning(tx_json, signer_cfg["xrpl_address"])
    msg = bytes.fromhex(bytes_hex)
    signing_hash = sha512_first_half(msg)  # 32 bytes

    sig = enclave_sign(
        signer_cfg["enclave_url"],
        signer_cfg["address"],
        signer_cfg["session_key"],
        signing_hash.hex(),
    )
    der_hex = rs_to_der(sig["r"], sig["s"])

    return Signer(
        account=signer_cfg["xrpl_address"],
        signing_pub_key=signer_cfg["compressed_pubkey"].upper(),
        txn_signature=der_hex,
    )


def submit_multisigned(client: JsonRpcClient, tx: Transaction, signers: List[Signer]) -> Dict:
    """Assemble Signers, sort canonically, and submit via SubmitMultisigned."""
    from xrpl.core.addresscodec import decode_classic_address
    from xrpl.models.requests import SubmitMultisigned

    tx_dict = tx.to_dict()
    signers_sorted = sorted(signers, key=lambda s: decode_classic_address(s.account))
    tx_dict["signers"] = signers_sorted
    combined = Transaction.from_dict(tx_dict)

    req = SubmitMultisigned(tx_json=combined)
    resp = client.request(req)
    return resp.result


# ── Commands ───────────────────────────────────────────────────────────────

def cmd_send(args):
    with open(ESCROW_FILE) as f:
        cfg = json.load(f)

    escrow_addr = cfg["escrow_address"]
    signers_map = {s["name"]: s for s in cfg["signers"]}

    chosen = args.signers
    if len(chosen) < cfg["quorum"]:
        print(f"ERROR: need at least {cfg['quorum']} signers, got {len(chosen)}")
        sys.exit(1)

    for name in chosen:
        if name not in signers_map:
            print(f"ERROR: unknown signer {name}. Available: {list(signers_map)}")
            sys.exit(1)

    client = JsonRpcClient(XRPL_TESTNET)

    # Fetch sequence
    info = client.request(AccountInfo(account=escrow_addr, ledger_index="current"))
    if "account_data" not in info.result:
        print(f"ERROR: escrow not found on testnet: {info.result}")
        sys.exit(1)
    sequence = info.result["account_data"]["Sequence"]

    amount_drops = str(int(float(args.amount_xrp) * 1_000_000))
    tx = build_payment(escrow_addr, args.destination, amount_drops, sequence)

    print(f"Escrow:      {escrow_addr}")
    print(f"Destination: {args.destination}")
    print(f"Amount:      {args.amount_xrp} XRP ({amount_drops} drops)")
    print(f"Sequence:    {sequence}")
    print(f"Signers:     {', '.join(chosen)}")
    print()

    sigs: List[Signer] = []
    for name in chosen:
        print(f"  → asking {name} to sign...")
        try:
            s = sign_by_enclave(tx, signers_map[name])
            sigs.append(s)
            print(f"    got sig from {s.account[:10]}... ({len(s.txn_signature)//2} bytes DER)")
        except Exception as e:
            print(f"    FAIL: {e}")
            sys.exit(1)
    print()

    print("Submitting multisigned tx to testnet...")
    result = submit_multisigned(client, tx, sigs)
    code = result.get("engine_result", "?")
    msg = result.get("engine_result_message", "")
    tx_hash = result.get("tx_json", {}).get("hash") or result.get("tx_blob", "")[:16]
    print(f"  engine_result: {code}")
    print(f"  message:       {msg}")
    if "tx_json" in result and "hash" in result["tx_json"]:
        h = result["tx_json"]["hash"]
        print(f"  tx_hash:       {h}")
        print(f"  explorer:      https://testnet.xrpl.org/transactions/{h}")

    if code == "tesSUCCESS":
        print("\n✓ Multisig withdrawal succeeded")
        return 0
    else:
        print(f"\n✗ Failed: {code}")
        return 1


def cmd_happy_path(args):
    """Full happy path: create destination wallet, send 10 XRP from escrow with 2-of-3 multisig."""
    with open(ESCROW_FILE) as f:
        cfg = json.load(f)

    client = JsonRpcClient(XRPL_TESTNET)

    # Fund escrow if balance low
    escrow_addr = cfg["escrow_address"]
    info = client.request(AccountInfo(account=escrow_addr, ledger_index="current"))
    balance = int(info.result["account_data"]["Balance"]) / 1_000_000
    print(f"Escrow balance: {balance} XRP")
    if balance < 20:
        print("Balance low, requesting faucet top-up...")
        # testnet faucet allows repeat funding by address via /accounts/
        import urllib.request
        req = urllib.request.Request(
            "https://faucet.altnet.rippletest.net/accounts",
            data=json.dumps({"destination": escrow_addr}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=30).read()
        except Exception as e:
            print(f"  faucet request: {e}")
        time.sleep(5)

    # Create destination wallet
    print("Creating destination wallet via faucet...")
    dest = generate_faucet_wallet(client, debug=False)
    print(f"  destination: {dest.classic_address}")
    dest_info = client.request(AccountInfo(account=dest.classic_address, ledger_index="current"))
    dest_bal_before = int(dest_info.result["account_data"]["Balance"]) / 1_000_000
    print(f"  balance before: {dest_bal_before} XRP")
    print()

    # Delegate to cmd_send
    args.destination = dest.classic_address
    args.amount_xrp = 10
    args.signers = ["sgx-node-1", "sgx-node-2"]

    rc = cmd_send(args)
    if rc != 0:
        return rc

    # Verify destination received
    time.sleep(3)
    dest_info = client.request(AccountInfo(account=dest.classic_address, ledger_index="current"))
    dest_bal_after = int(dest_info.result["account_data"]["Balance"]) / 1_000_000
    print(f"\nDestination balance: {dest_bal_before} → {dest_bal_after} XRP (+{dest_bal_after - dest_bal_before})")
    if dest_bal_after > dest_bal_before + 9:
        print("\n✓ HAPPY PATH TEST PASSED")
        return 0
    else:
        print("\n✗ HAPPY PATH TEST FAILED: destination balance did not increase")
        return 1


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    send = sub.add_parser("send", help="Send a multisigned XRP Payment")
    send.add_argument("--destination", required=True)
    send.add_argument("--amount-xrp", required=True)
    send.add_argument("--signers", nargs="+", required=True, help="Signer names (e.g. sgx-node-1 sgx-node-2)")
    send.set_defaults(func=cmd_send)

    hp = sub.add_parser("happy-path", help="Full end-to-end happy path test")
    hp.set_defaults(func=cmd_happy_path)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

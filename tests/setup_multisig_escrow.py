#!/usr/bin/env python3
"""
Set up XRPL testnet escrow account with 2-of-3 SignerListSet.

Signers are 3 SGX enclaves on Azure DCsv3 nodes (see multisig_accounts.json).
Generates a fresh escrow account on testnet via faucet, sets SignerListSet,
and saves config to tests/multisig_escrow.json for subsequent tests.
"""

import json
import sys
from pathlib import Path

from xrpl.clients import JsonRpcClient
from xrpl.wallet import generate_faucet_wallet
from xrpl.models.transactions import SignerListSet
from xrpl.models.transactions.signer_list_set import SignerEntry
from xrpl.transaction import submit_and_wait
from xrpl.models.requests import AccountObjects

XRPL_TESTNET = "https://s.altnet.rippletest.net:51234"
ACCOUNTS_FILE = Path(__file__).parent / "multisig_accounts.json"
ESCROW_FILE = Path(__file__).parent / "multisig_escrow.json"
QUORUM = 2


def main():
    with open(ACCOUNTS_FILE) as f:
        accounts = json.load(f)

    if len(accounts) != 3:
        print(f"Expected 3 accounts, got {len(accounts)}")
        sys.exit(1)

    client = JsonRpcClient(XRPL_TESTNET)

    print("=" * 60)
    print("  XRPL Testnet 2-of-3 Multisig Escrow Setup")
    print("=" * 60)
    print()
    print("Signers:")
    for a in accounts:
        print(f"  {a['name']:12} → {a['xrpl_address']}")
    print(f"  Quorum: {QUORUM}")
    print()

    print("[1/3] Creating escrow account via testnet faucet...")
    escrow_wallet = generate_faucet_wallet(client, debug=False)
    print(f"      escrow address: {escrow_wallet.classic_address}")
    print(f"      escrow seed:    {escrow_wallet.seed}")
    print()

    print("[2/3] Submitting SignerListSet...")
    signer_entries = [
        SignerEntry(account=a["xrpl_address"], signer_weight=1) for a in accounts
    ]
    sls_tx = SignerListSet(
        account=escrow_wallet.classic_address,
        signer_quorum=QUORUM,
        signer_entries=signer_entries,
    )
    response = submit_and_wait(sls_tx, client, escrow_wallet)
    tx_hash = response.result.get("hash")
    status = response.result.get("meta", {}).get("TransactionResult", "?")
    print(f"      tx_hash: {tx_hash}")
    print(f"      status:  {status}")
    if status != "tesSUCCESS":
        print(f"FAIL: SignerListSet returned {status}")
        sys.exit(1)
    print()

    print("[3/3] Verifying SignerListSet on-chain...")
    objs = client.request(
        AccountObjects(account=escrow_wallet.classic_address, type="signer_list")
    )
    signer_lists = objs.result.get("account_objects", [])
    if not signer_lists:
        print("FAIL: no signer_list found on-chain")
        sys.exit(1)
    sl = signer_lists[0]
    print(f"      SignerQuorum:   {sl['SignerQuorum']}")
    print(f"      SignerEntries:  {len(sl['SignerEntries'])}")
    for se in sl["SignerEntries"]:
        e = se["SignerEntry"]
        print(f"        {e['Account']} (weight={e['SignerWeight']})")
    print()

    escrow_config = {
        "escrow_address": escrow_wallet.classic_address,
        "escrow_seed": escrow_wallet.seed,
        "quorum": QUORUM,
        "signer_list_set_tx_hash": tx_hash,
        "signers": [
            {
                "name": a["name"],
                "ip": a["ip"],
                "enclave_url": f"https://{a['ip']}:9088/v1",
                "address": a["address"],
                "session_key": a["session_key"],
                "compressed_pubkey": a["compressed_pubkey"],
                "xrpl_address": a["xrpl_address"],
            }
            for a in accounts
        ],
    }

    with open(ESCROW_FILE, "w") as f:
        json.dump(escrow_config, f, indent=2)
    print(f"Saved to {ESCROW_FILE}")
    print()
    print("=" * 60)
    print(f"  Escrow ready: {escrow_wallet.classic_address}")
    print(f"  Explorer: https://testnet.xrpl.org/accounts/{escrow_wallet.classic_address}")
    print("=" * 60)


if __name__ == "__main__":
    main()

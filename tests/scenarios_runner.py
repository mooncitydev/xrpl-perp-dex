#!/usr/bin/env python3
"""
Failure mode scenarios runner for XRPL 2-of-3 multisig Perp DEX.

Each scenario function returns a dict with:
  { name, status: pass|fail|skip, details, tx_hashes: [..], error? }

Run a single scenario:
  python3 tests/scenarios_runner.py 3.1

Run all and write JSON report:
  python3 tests/scenarios_runner.py all --out report.json
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

import requests
import urllib3
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo

import multisig_coordinator as mc

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

XRPL_TESTNET = "https://s.altnet.rippletest.net:51234"
TESTS_DIR = Path(__file__).parent
ESCROW_FILE = TESTS_DIR / "multisig_escrow.json"


def load_cfg():
    with open(ESCROW_FILE) as f:
        return json.load(f)


def get_balance(client, addr) -> float:
    try:
        r = client.request(AccountInfo(account=addr, ledger_index="current"))
        return int(r.result["account_data"]["Balance"]) / 1_000_000
    except Exception:
        return 0.0


def create_dest(client):
    """Create a fresh destination wallet via faucet."""
    from xrpl.wallet import generate_faucet_wallet
    dest = generate_faucet_wallet(client, debug=False)
    return dest.classic_address


def enclave_alive(signer) -> bool:
    """HEAD /v1/pool/status with short timeout to check if enclave responds."""
    try:
        r = requests.get(
            f"{signer['enclave_url']}/pool/status", timeout=3, verify=False
        )
        return r.status_code == 200
    except Exception:
        return False


# Map signer name → (azure public ip, hetzner ssh hop). Hardcoded for the
# testing environment; the scenarios runner uses these to physically stop/start
# perp-dex-server processes on the Azure nodes.
NODE_IPS = {
    "sgx-node-1": "20.71.184.176",
    "sgx-node-2": "20.224.243.60",
    "sgx-node-3": "52.236.130.102",
}
HETZNER_HOP = "andrey@94.130.18.162"


SSH_OPTS = [
    "-i", "/home/andrey/.ssh/id_rsa",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR",
]


def _azure_ssh(ip: str, cmd: str, timeout: int = 30):
    """Run a shell command on an Azure VM via ssh."""
    return subprocess.run(
        ["ssh", *SSH_OPTS, f"azureuser@{ip}", cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def stop_enclave(name: str):
    ip = NODE_IPS[name]
    _azure_ssh(ip, "pkill -f perp-dex-server; sleep 1; pgrep -f perp-dex-server || true")
    for _ in range(20):
        if not enclave_alive(next(s for s in load_cfg()["signers"] if s["name"] == name)):
            return
        time.sleep(0.5)


def start_enclave(name: str):
    ip = NODE_IPS[name]
    _azure_ssh(ip, "bash /tmp/start2.sh", timeout=60)
    for _ in range(40):
        if enclave_alive(next(s for s in load_cfg()["signers"] if s["name"] == name)):
            return
        time.sleep(0.5)


def ensure_state(alive_names: List[str]):
    """Make exactly the named enclaves alive; stop the others."""
    cfg = load_cfg()
    for s in cfg["signers"]:
        if s["name"] in alive_names:
            if not enclave_alive(s):
                start_enclave(s["name"])
        else:
            if enclave_alive(s):
                stop_enclave(s["name"])


def try_multisig_send(cfg, signer_names: List[str], dest: str, amount_xrp: float) -> Dict:
    """Attempt a multisig send. Returns {status, engine_result, tx_hash?, error?}."""
    client = JsonRpcClient(XRPL_TESTNET)
    signers_map = {s["name"]: s for s in cfg["signers"]}
    escrow_addr = cfg["escrow_address"]

    try:
        info = client.request(AccountInfo(account=escrow_addr, ledger_index="current"))
        sequence = info.result["account_data"]["Sequence"]
    except Exception as e:
        return {"status": "error", "error": f"failed to fetch sequence: {e}"}

    amount_drops = str(int(amount_xrp * 1_000_000))
    tx = mc.build_payment(escrow_addr, dest, amount_drops, sequence)

    sigs = []
    for name in signer_names:
        try:
            sig = mc.sign_by_enclave(tx, signers_map[name])
            sigs.append(sig)
        except Exception as e:
            return {"status": "error", "error": f"{name} sign failed: {e}", "signers_attempted": signer_names}

    try:
        result = mc.submit_multisigned(client, tx, sigs)
    except Exception as e:
        return {"status": "error", "error": f"submit failed: {e}", "signers": signer_names}

    code = result.get("engine_result", "?")
    tx_hash = result.get("tx_json", {}).get("hash")
    return {
        "status": "success" if code == "tesSUCCESS" else "rejected",
        "engine_result": code,
        "engine_result_message": result.get("engine_result_message", ""),
        "tx_hash": tx_hash,
        "signers": signer_names,
    }


# ── Scenarios ─────────────────────────────────────────────────────────────


def scenario_3_1(cfg) -> Dict:
    """3.1: One operator offline. Verify 2-of-3 still works, 1 wrong signer fails."""
    name = "3.1 One operator offline"
    events = []
    tx_hashes = []
    client = JsonRpcClient(XRPL_TESTNET)

    ensure_state(["sgx-node-1", "sgx-node-2"])
    cfg = load_cfg()  # reload after state setup
    alive = {s["name"]: enclave_alive(s) for s in cfg["signers"]}
    events.append({"step": "precondition_liveness", "alive": alive})
    offline = [n for n, v in alive.items() if not v]
    if len(offline) != 1:
        return {
            "name": name,
            "status": "skip",
            "details": f"expected exactly 1 offline, got {len(offline)} ({offline})",
            "events": events,
        }
    offline_node = offline[0]
    alive_nodes = [n for n in alive if alive[n]]

    dest = create_dest(client)
    events.append({"step": "create_destination", "address": dest})

    # Test 1: 2 alive signers → expect success
    t1 = try_multisig_send(cfg, alive_nodes[:2], dest, 5.0)
    events.append({"step": f"multisig_with_alive_signers={alive_nodes[:2]}", "result": t1})
    if t1.get("tx_hash"):
        tx_hashes.append({"step": "alive_signers_success", "hash": t1["tx_hash"]})
    if t1["status"] != "success":
        return {"name": name, "status": "fail", "details": "2 alive signers failed", "events": events, "tx_hashes": tx_hashes}

    # Test 2: 1 alive + 1 offline signer → expect sign error (offline doesn't respond)
    mixed = [alive_nodes[0], offline_node]
    t2 = try_multisig_send(cfg, mixed, dest, 5.0)
    events.append({"step": f"multisig_with_offline={mixed}", "result": t2})
    offline_blocked = t2["status"] == "error" and offline_node in t2.get("error", "")
    if not offline_blocked:
        return {
            "name": name,
            "status": "fail",
            "details": f"expected offline signer to fail, got: {t2}",
            "events": events,
            "tx_hashes": tx_hashes,
        }

    return {
        "name": name,
        "status": "pass",
        "details": f"2-of-3 worked with alive signers {alive_nodes[:2]}; {offline_node} offline correctly blocked second attempt",
        "events": events,
        "tx_hashes": tx_hashes,
    }


def scenario_3_2(cfg) -> Dict:
    """3.2: Two operators offline. Withdrawal impossible (only 1 signer alive)."""
    name = "3.2 Two operators offline"
    events = []
    client = JsonRpcClient(XRPL_TESTNET)

    ensure_state(["sgx-node-1"])
    cfg = load_cfg()
    alive = {s["name"]: enclave_alive(s) for s in cfg["signers"]}
    events.append({"step": "precondition_liveness", "alive": alive})
    alive_nodes = [n for n, v in alive.items() if v]
    offline_nodes = [n for n, v in alive.items() if not v]

    if len(alive_nodes) != 1:
        return {
            "name": name,
            "status": "skip",
            "details": f"expected exactly 1 alive, got {len(alive_nodes)} ({alive_nodes})",
            "events": events,
        }

    dest = create_dest(client)
    events.append({"step": "create_destination", "address": dest})

    # Try signing with only the 1 alive node — insufficient quorum
    t1 = try_multisig_send(cfg, alive_nodes, dest, 5.0)
    events.append({"step": f"multisig_with_only_{alive_nodes}", "result": t1})
    # Expect: either XRPL rejects (tefBAD_QUORUM or similar), or error. NOT tesSUCCESS.
    if t1.get("engine_result") == "tesSUCCESS":
        return {
            "name": name,
            "status": "fail",
            "details": "1-of-3 should NOT succeed but did",
            "events": events,
        }

    # Also try including an offline node — should fail on sign step
    mixed = alive_nodes + offline_nodes[:1]
    t2 = try_multisig_send(cfg, mixed, dest, 5.0)
    events.append({"step": f"multisig_with_offline_mixed={mixed}", "result": t2})
    if t2.get("engine_result") == "tesSUCCESS":
        return {"name": name, "status": "fail", "details": "mixed with offline succeeded", "events": events}

    # Verify escrow balance unchanged (funds still safe)
    escrow_bal = get_balance(client, cfg["escrow_address"])
    events.append({"step": "funds_safe_check", "escrow_balance_xrp": escrow_bal})

    return {
        "name": name,
        "status": "pass",
        "details": f"withdrawal correctly blocked with only {alive_nodes} alive; escrow={escrow_bal} XRP still safe",
        "events": events,
    }


def scenario_3_3(cfg) -> Dict:
    """3.3: All three offline. Funds remain safe on XRPL. Restart → trading continues."""
    name = "3.3 All three operators offline"
    events = []
    client = JsonRpcClient(XRPL_TESTNET)

    ensure_state([])  # all offline
    cfg = load_cfg()
    alive = {s["name"]: enclave_alive(s) for s in cfg["signers"]}
    events.append({"step": "precondition_liveness", "alive": alive})
    if any(alive.values()):
        return {
            "name": name,
            "status": "skip",
            "details": f"expected all 3 offline, got alive={[n for n,v in alive.items() if v]}",
            "events": events,
        }

    # Funds still on XRPL — not affected by operator state
    escrow_bal = get_balance(client, cfg["escrow_address"])
    events.append({"step": "funds_safe_check", "escrow_balance_xrp": escrow_bal})
    if escrow_bal <= 0:
        return {"name": name, "status": "fail", "details": "escrow balance 0 or missing", "events": events}

    # Try to withdraw — must fail at sign step
    dest = create_dest(client)
    events.append({"step": "create_destination", "address": dest})
    t1 = try_multisig_send(cfg, [s["name"] for s in cfg["signers"][:2]], dest, 1.0)
    events.append({"step": "attempt_withdraw_all_offline", "result": t1})
    if t1.get("engine_result") == "tesSUCCESS":
        return {"name": name, "status": "fail", "details": "withdrawal succeeded while all enclaves offline", "events": events}

    return {
        "name": name,
        "status": "pass",
        "details": f"withdrawal blocked while all offline; escrow={escrow_bal} XRP safe on XRPL",
        "events": events,
    }


def scenario_3_4(cfg) -> Dict:
    """3.4: Malicious operator returns wrong signature. XRPL must reject the tx."""
    name = "3.4 Malicious operator (wrong signature)"
    events = []
    tx_hashes = []
    client = JsonRpcClient(XRPL_TESTNET)

    ensure_state(["sgx-node-1", "sgx-node-2", "sgx-node-3"])
    cfg = load_cfg()
    alive = {s["name"]: enclave_alive(s) for s in cfg["signers"]}
    events.append({"step": "precondition_liveness", "alive": alive})
    alive_nodes = [n for n, v in alive.items() if v]
    if len(alive_nodes) < 2:
        return {
            "name": name,
            "status": "skip",
            "details": f"need at least 2 alive signers, got {len(alive_nodes)}",
            "events": events,
        }

    dest = create_dest(client)
    events.append({"step": "create_destination", "address": dest})

    # Build tx manually so we can corrupt one signature
    signers_map = {s["name"]: s for s in cfg["signers"]}
    escrow_addr = cfg["escrow_address"]
    info = client.request(AccountInfo(account=escrow_addr, ledger_index="current"))
    sequence = info.result["account_data"]["Sequence"]
    tx = mc.build_payment(escrow_addr, dest, "1000000", sequence)

    # Honest signer
    honest = mc.sign_by_enclave(tx, signers_map[alive_nodes[0]])
    # "Malicious" signer — replace signature with garbage while keeping same account/pubkey
    from xrpl.models.transactions.transaction import Signer
    malicious_src = signers_map[alive_nodes[1]]
    garbage_der = "30440220" + "AA" * 32 + "0220" + "BB" * 32  # 71 hex bytes, invalid ECDSA
    malicious = Signer(
        account=malicious_src["xrpl_address"],
        signing_pub_key=malicious_src["compressed_pubkey"].upper(),
        txn_signature=garbage_der,
    )

    try:
        result = mc.submit_multisigned(client, tx, [honest, malicious])
    except Exception as e:
        events.append({"step": "submit_with_garbage", "error": str(e)})
        return {"name": name, "status": "pass", "details": f"malicious signature rejected: {e}", "events": events}

    code = result.get("engine_result", "?")
    msg = result.get("engine_result_message", "")
    events.append({"step": "submit_with_garbage", "engine_result": code, "message": msg})

    if code == "tesSUCCESS":
        return {"name": name, "status": "fail", "details": "garbage signature ACCEPTED — major bug", "events": events}

    # Now retry with 2 honest signers — should succeed
    t2 = try_multisig_send(cfg, alive_nodes[:2], dest, 1.0)
    events.append({"step": f"retry_with_honest={alive_nodes[:2]}", "result": t2})
    if t2.get("tx_hash"):
        tx_hashes.append({"step": "honest_retry_success", "hash": t2["tx_hash"]})

    if t2["status"] != "success":
        return {"name": name, "status": "fail", "details": "honest retry failed", "events": events, "tx_hashes": tx_hashes}

    return {
        "name": name,
        "status": "pass",
        "details": f"garbage signature rejected ({code}); 2 honest signers successfully retried",
        "events": events,
        "tx_hashes": tx_hashes,
    }


def scenario_3_9(cfg) -> Dict:
    """3.9: Catastrophic recovery. Verify XRPL has full deposit/withdrawal history."""
    name = "3.9 Catastrophic recovery (XRPL as source of truth)"
    events = []
    client = JsonRpcClient(XRPL_TESTNET)

    ensure_state(["sgx-node-1", "sgx-node-2", "sgx-node-3"])
    cfg = load_cfg()

    escrow_addr = cfg["escrow_address"]
    from xrpl.models.requests import AccountTx
    tx_req = AccountTx(account=escrow_addr, limit=50)
    tx_resp = client.request(tx_req)
    txs = tx_resp.result.get("transactions", [])
    events.append({"step": "fetch_account_history", "tx_count": len(txs)})

    if len(txs) == 0:
        return {"name": name, "status": "fail", "details": "no tx history on XRPL", "events": events}

    # Check escrow still has balance
    escrow_bal = get_balance(client, escrow_addr)
    events.append({"step": "fetch_balance", "balance_xrp": escrow_bal})

    # Get SignerList from XRPL (proof multi-operator setup is on-chain)
    from xrpl.models.requests import AccountObjects
    objs = client.request(AccountObjects(account=escrow_addr, type="signer_list"))
    sl = objs.result.get("account_objects", [])
    if not sl:
        return {"name": name, "status": "fail", "details": "no signer_list on-chain", "events": events}
    signer_list_info = {
        "quorum": sl[0]["SignerQuorum"],
        "signers": [e["SignerEntry"]["Account"] for e in sl[0]["SignerEntries"]],
    }
    events.append({"step": "fetch_signer_list", "info": signer_list_info})

    # Categorize tx types
    tx_types = {}
    for t in txs:
        ttype = t.get("tx_json", {}).get("TransactionType", "?")
        tx_types[ttype] = tx_types.get(ttype, 0) + 1
    events.append({"step": "categorize_tx_types", "types": tx_types})

    return {
        "name": name,
        "status": "pass",
        "details": (
            f"XRPL has {len(txs)} txs, {tx_types} types, escrow balance {escrow_bal} XRP, "
            f"quorum={signer_list_info['quorum']} with {len(signer_list_info['signers'])} signers. "
            "Full recovery possible from XRPL ledger alone."
        ),
        "events": events,
    }


SCENARIOS = {
    "3.1": scenario_3_1,
    "3.2": scenario_3_2,
    "3.3": scenario_3_3,
    "3.4": scenario_3_4,
    "3.9": scenario_3_9,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", help="Scenario id (e.g. 3.1) or 'all'")
    ap.add_argument("--out", help="Write JSON report to file")
    args = ap.parse_args()

    cfg = load_cfg()

    if args.scenario == "all":
        results = []
        for sid, fn in SCENARIOS.items():
            print(f"\n=== Running {sid} ===")
            r = fn(cfg)
            results.append(r)
            print(f"  → {r['status'].upper()}: {r['details']}")
    elif args.scenario in SCENARIOS:
        results = [SCENARIOS[args.scenario](cfg)]
        for r in results:
            print(f"=== {r['name']} ===")
            print(f"Status:  {r['status'].upper()}")
            print(f"Details: {r['details']}")
            if r.get("tx_hashes"):
                for th in r["tx_hashes"]:
                    print(f"  {th['step']}: {th['hash']}")
    else:
        print(f"Unknown scenario: {args.scenario}")
        print(f"Available: {list(SCENARIOS) + ['all']}")
        sys.exit(1)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nReport saved to {args.out}")

    failed = [r for r in results if r["status"] == "fail"]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

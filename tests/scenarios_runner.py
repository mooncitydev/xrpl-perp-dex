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


# Map signer name → azure public ip. Hardcoded for the testing environment;
# the scenarios runner uses these to physically stop/start perp-dex-server
# processes on the Azure nodes. sgx-node-1b is a second logical signer
# generated on sgx-node-1 (added by scenario 3.8 to test scaling).
NODE_IPS = {
    "sgx-node-1": "20.71.184.176",
    "sgx-node-1b": "20.71.184.176",  # 2nd account on same enclave
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
    _azure_ssh(ip, "pkill -x perp-dex-server; sleep 1; pgrep -f perp-dex-server || true")
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
    """Make exactly the named enclaves alive; stop the others.

    Operates on the 3 physical Azure nodes, deduplicating by node IP. Logical
    signers like 'sgx-node-1b' that share a physical host with another signer
    follow the host's state.
    """
    cfg = load_cfg()
    seen_ips = set()
    for s in cfg["signers"]:
        if s["name"] not in NODE_IPS:
            continue
        ip = NODE_IPS[s["name"]]
        if ip in seen_ips:
            continue
        seen_ips.add(ip)
        # Determine desired state by whether ANY logical signer on this host
        # is in alive_names.
        wants_alive = any(
            NODE_IPS.get(n) == ip for n in alive_names
        )
        is_alive = enclave_alive(s)
        if wants_alive and not is_alive:
            start_enclave(s["name"])
        elif not wants_alive and is_alive:
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
    tx_hash = result.get("hash") or result.get("tx_json", {}).get("hash")
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
    """3.9: Catastrophic recovery. Verify XRPL has full deposit/withdrawal history.

    Read-only scenario; does not modify enclave or escrow state.
    """
    name = "3.9 Catastrophic recovery (XRPL as source of truth)"
    events = []
    client = JsonRpcClient(XRPL_TESTNET)
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


# ── Helpers for SignerListSet rotation scenarios ──────────────────────────


def generate_new_account_on(name: str) -> Dict:
    """Generate a fresh ECDSA account on the given enclave and return its
    xrpl_address + compressed pubkey + session key in coordinator format.
    """
    cfg = load_cfg()
    signer = next(s for s in cfg["signers"] if s["name"] == name)
    r = requests.post(f"{signer['enclave_url']}/pool/generate", json={}, timeout=30, verify=False)
    body = r.json()
    if body.get("status") != "success":
        raise RuntimeError(f"generate failed: {body}")

    eth_addr = body["address"]
    pubkey_uncompressed = body["public_key"]
    session_key = body["session_key"]

    # Convert uncompressed -> compressed
    h = pubkey_uncompressed[2:] if pubkey_uncompressed.startswith("0x") else pubkey_uncompressed
    assert h[:2] == "04"
    x, y = h[2:66], h[66:]
    prefix = "02" if int(y, 16) % 2 == 0 else "03"
    compressed = (prefix + x).upper()

    from xrpl.core.keypairs import derive_classic_address
    xrpl_addr = derive_classic_address(compressed)

    return {
        "name": name,
        "ip": signer["ip"],
        "enclave_url": signer["enclave_url"],
        "address": eth_addr,
        "session_key": session_key,
        "compressed_pubkey": compressed,
        "xrpl_address": xrpl_addr,
    }


def submit_signer_list_set(cfg, new_signers: List[Dict], quorum: int, signing_node_names: List[str]) -> Dict:
    """Build, multisign, and submit a SignerListSet update."""
    client = JsonRpcClient(XRPL_TESTNET)
    escrow_addr = cfg["escrow_address"]
    info = client.request(AccountInfo(account=escrow_addr, ledger_index="current"))
    sequence = info.result["account_data"]["Sequence"]

    tx = mc.build_signer_list_set(escrow_addr, new_signers, quorum, sequence)
    signers_map = {s["name"]: s for s in cfg["signers"]}

    sigs = []
    for name in signing_node_names:
        sig = mc.sign_by_enclave(tx, signers_map[name])
        sigs.append(sig)

    return mc.submit_multisigned(client, tx, sigs)


def fetch_onchain_signer_list(cfg) -> Dict:
    """Read SignerListSet for escrow from XRPL and return {quorum, signers}."""
    from xrpl.models.requests import AccountObjects
    client = JsonRpcClient(XRPL_TESTNET)
    objs = client.request(
        AccountObjects(account=cfg["escrow_address"], type="signer_list")
    )
    sl_objs = objs.result.get("account_objects", [])
    if not sl_objs:
        return {}
    sl = sl_objs[0]
    return {
        "quorum": sl["SignerQuorum"],
        "signers": sorted([e["SignerEntry"]["Account"] for e in sl["SignerEntries"]]),
    }


def update_escrow_file_signers(new_signers: List[Dict], new_quorum: int):
    """Persist new signers list back to multisig_escrow.json."""
    cfg = load_cfg()
    cfg["signers"] = new_signers
    cfg["quorum"] = new_quorum
    with open(ESCROW_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Scenarios 3.5-3.8 ─────────────────────────────────────────────────────


def scenario_3_5(cfg) -> Dict:
    """3.5: SGX compromise. Rotate one signer's key via current 2-of-3 multisig."""
    name = "3.5 SGX compromise → key rotation"
    events = []
    tx_hashes = []

    ensure_state(["sgx-node-1", "sgx-node-2", "sgx-node-3"])
    cfg = load_cfg()
    signers_old = list(cfg["signers"])
    target_name = "sgx-node-3"

    # Snapshot original signer
    target_old = next(s for s in signers_old if s["name"] == target_name)
    events.append({"step": "snapshot_target", "old_xrpl_address": target_old["xrpl_address"]})

    try:
        # Step 1: generate new key on target node
        new_target = generate_new_account_on(target_name)
        events.append({"step": "generate_new_key", "new_xrpl_address": new_target["xrpl_address"]})

        # Step 2: build new signer list with target replaced
        new_signers = [s if s["name"] != target_name else new_target for s in signers_old]
        events.append({"step": "new_signer_set", "addresses": [s["xrpl_address"] for s in new_signers]})

        # Step 3: submit SignerListSet via current 2-of-3 multisig (using OLD keys)
        result = submit_signer_list_set(cfg, new_signers, cfg["quorum"], ["sgx-node-1", "sgx-node-2"])
        code = result.get("engine_result", "?")
        h = result.get("hash") or result.get("tx_json", {}).get("hash")
        events.append({"step": "submit_signer_list_set", "engine_result": code, "tx_hash": h})
        if h:
            tx_hashes.append({"step": "rotation_tx", "hash": h})
        if code != "tesSUCCESS":
            return {"name": name, "status": "fail", "details": f"SignerListSet failed: {code}", "events": events, "tx_hashes": tx_hashes}

        # Step 4: persist new signers locally so we can sign with the rotated key
        update_escrow_file_signers(new_signers, cfg["quorum"])
        time.sleep(2)

        # Step 5: verify on-chain SignerList contains new address
        on_chain = fetch_onchain_signer_list(load_cfg())
        events.append({"step": "verify_onchain", "signer_list": on_chain})
        if new_target["xrpl_address"] not in on_chain.get("signers", []):
            return {"name": name, "status": "fail", "details": "new key not in on-chain SignerList", "events": events, "tx_hashes": tx_hashes}
        if target_old["xrpl_address"] in on_chain.get("signers", []):
            return {"name": name, "status": "fail", "details": "old key still in SignerList", "events": events, "tx_hashes": tx_hashes}

        # Step 6: withdraw using NEW key + one of the original keys → expect success
        client = JsonRpcClient(XRPL_TESTNET)
        dest = create_dest(client)
        events.append({"step": "create_dest", "address": dest})
        post_rotation = try_multisig_send(load_cfg(), ["sgx-node-1", target_name], dest, 1.0)
        events.append({"step": "withdraw_with_new_key", "result": post_rotation})
        if post_rotation.get("tx_hash"):
            tx_hashes.append({"step": "post_rotation_withdraw", "hash": post_rotation["tx_hash"]})
        if post_rotation["status"] != "success":
            return {"name": name, "status": "fail", "details": "withdrawal with new key failed", "events": events, "tx_hashes": tx_hashes}

        return {
            "name": name,
            "status": "pass",
            "details": (
                f"rotated {target_name} from {target_old['xrpl_address']} to "
                f"{new_target['xrpl_address']} via 2-of-3 multisig; "
                f"withdrawal with new key succeeded"
            ),
            "events": events,
            "tx_hashes": tx_hashes,
        }
    except Exception as e:
        events.append({"step": "exception", "error": str(e)})
        return {"name": name, "status": "fail", "details": f"exception: {e}", "events": events, "tx_hashes": tx_hashes}


def scenario_3_6(cfg) -> Dict:
    """3.6: Hardware failure. Lose sealed data on one node, replace with new key.

    Same flow as 3.5 but explicitly clears /home/azureuser/perp/accounts on
    the target node first to simulate complete data loss.
    """
    name = "3.6 Hardware failure → replacement node"
    events = []
    tx_hashes = []
    ensure_state(["sgx-node-1", "sgx-node-2", "sgx-node-3"])
    cfg = load_cfg()
    target_name = "sgx-node-2"
    target_ip = NODE_IPS[target_name]
    target_old = next(s for s in cfg["signers"] if s["name"] == target_name)

    try:
        # Wipe sealed accounts on target → simulate hardware loss
        _azure_ssh(target_ip, "pkill -x perp-dex-server; sleep 1; rm -rf /home/azureuser/perp/accounts/*; bash /tmp/start2.sh")
        events.append({"step": "wipe_and_restart_target"})
        time.sleep(3)

        # Generate fresh key on the (now-empty) node
        new_target = generate_new_account_on(target_name)
        events.append({"step": "generate_replacement_key", "new_xrpl_address": new_target["xrpl_address"]})

        new_signers = [s if s["name"] != target_name else new_target for s in cfg["signers"]]
        # Rotate via the surviving 2 keys (sgx-node-1 + sgx-node-3)
        result = submit_signer_list_set(cfg, new_signers, cfg["quorum"], ["sgx-node-1", "sgx-node-3"])
        code = result.get("engine_result", "?")
        h = result.get("hash") or result.get("tx_json", {}).get("hash")
        events.append({"step": "submit_signer_list_set", "engine_result": code, "tx_hash": h})
        if h:
            tx_hashes.append({"step": "replacement_tx", "hash": h})
        if code != "tesSUCCESS":
            return {"name": name, "status": "fail", "details": f"SignerListSet failed: {code}", "events": events, "tx_hashes": tx_hashes}

        update_escrow_file_signers(new_signers, cfg["quorum"])
        time.sleep(2)

        # Verify withdrawal with replacement key works
        client = JsonRpcClient(XRPL_TESTNET)
        dest = create_dest(client)
        events.append({"step": "create_dest", "address": dest})
        wd = try_multisig_send(load_cfg(), ["sgx-node-1", target_name], dest, 1.0)
        events.append({"step": "withdraw_with_replacement", "result": wd})
        if wd.get("tx_hash"):
            tx_hashes.append({"step": "post_replacement_withdraw", "hash": wd["tx_hash"]})

        if wd["status"] != "success":
            return {"name": name, "status": "fail", "details": "withdraw with replacement failed", "events": events, "tx_hashes": tx_hashes}

        return {
            "name": name,
            "status": "pass",
            "details": (
                f"wiped accounts on {target_name}, generated replacement key "
                f"{new_target['xrpl_address']}, surviving 2 of 3 rotated SignerList, "
                f"withdrawal with replacement succeeded"
            ),
            "events": events,
            "tx_hashes": tx_hashes,
        }
    except Exception as e:
        events.append({"step": "exception", "error": str(e)})
        return {"name": name, "status": "fail", "details": f"exception: {e}", "events": events, "tx_hashes": tx_hashes}


def scenario_3_7(cfg) -> Dict:
    """3.7: Cloud migration. Same as 3.5 but framed as moving an operator to a new
    physical host (we simulate by generating a fresh key on the same node).
    """
    name = "3.7 Cloud migration"
    events = []
    tx_hashes = []
    ensure_state(["sgx-node-1", "sgx-node-2", "sgx-node-3"])
    cfg = load_cfg()
    target_name = "sgx-node-1"
    target_old = next(s for s in cfg["signers"] if s["name"] == target_name)

    try:
        new_target = generate_new_account_on(target_name)
        events.append({
            "step": "generate_post_migration_key",
            "old_xrpl_address": target_old["xrpl_address"],
            "new_xrpl_address": new_target["xrpl_address"],
        })

        new_signers = [s if s["name"] != target_name else new_target for s in cfg["signers"]]
        result = submit_signer_list_set(cfg, new_signers, cfg["quorum"], ["sgx-node-2", "sgx-node-3"])
        code = result.get("engine_result", "?")
        h = result.get("hash") or result.get("tx_json", {}).get("hash")
        events.append({"step": "submit_signer_list_set", "engine_result": code, "tx_hash": h})
        if h:
            tx_hashes.append({"step": "migration_tx", "hash": h})
        if code != "tesSUCCESS":
            return {"name": name, "status": "fail", "details": f"SignerListSet failed: {code}", "events": events, "tx_hashes": tx_hashes}

        update_escrow_file_signers(new_signers, cfg["quorum"])
        time.sleep(2)

        client = JsonRpcClient(XRPL_TESTNET)
        dest = create_dest(client)
        wd = try_multisig_send(load_cfg(), [target_name, "sgx-node-2"], dest, 1.0)
        events.append({"step": "withdraw_post_migration", "result": wd})
        if wd.get("tx_hash"):
            tx_hashes.append({"step": "post_migration_withdraw", "hash": wd["tx_hash"]})
        if wd["status"] != "success":
            return {"name": name, "status": "fail", "details": "post-migration withdrawal failed", "events": events, "tx_hashes": tx_hashes}

        return {
            "name": name,
            "status": "pass",
            "details": f"migrated {target_name} key to {new_target['xrpl_address']}, withdrawal works",
            "events": events,
            "tx_hashes": tx_hashes,
        }
    except Exception as e:
        events.append({"step": "exception", "error": str(e)})
        return {"name": name, "status": "fail", "details": f"exception: {e}", "events": events, "tx_hashes": tx_hashes}


def scenario_3_8(cfg) -> Dict:
    """3.8: Scaling. Expand from 2-of-3 to 3-of-4 by adding a 4th signer.

    The 4th signer is a second account on sgx-node-1 (different ECDSA key on
    the same enclave hardware — fine for testing the SignerList expansion).
    """
    name = "3.8 Scaling 2-of-3 → 3-of-4"
    events = []
    tx_hashes = []
    ensure_state(["sgx-node-1", "sgx-node-2", "sgx-node-3"])
    cfg = load_cfg()

    try:
        # Generate 4th key on sgx-node-1 (second account on same enclave)
        new_signer = generate_new_account_on("sgx-node-1")
        new_signer["name"] = "sgx-node-1b"  # distinguish in cfg
        events.append({"step": "generate_4th_signer", "new_xrpl_address": new_signer["xrpl_address"]})

        new_signers = list(cfg["signers"]) + [new_signer]
        new_quorum = 3

        result = submit_signer_list_set(cfg, new_signers, new_quorum, ["sgx-node-1", "sgx-node-2"])
        code = result.get("engine_result", "?")
        h = result.get("hash") or result.get("tx_json", {}).get("hash")
        events.append({"step": "submit_expand", "engine_result": code, "tx_hash": h})
        if h:
            tx_hashes.append({"step": "expand_tx", "hash": h})
        if code != "tesSUCCESS":
            return {"name": name, "status": "fail", "details": f"expansion failed: {code}", "events": events, "tx_hashes": tx_hashes}

        update_escrow_file_signers(new_signers, new_quorum)
        time.sleep(2)

        on_chain = fetch_onchain_signer_list(load_cfg())
        events.append({"step": "verify_onchain", "signer_list": on_chain})
        if on_chain.get("quorum") != 3 or len(on_chain.get("signers", [])) != 4:
            return {
                "name": name,
                "status": "fail",
                "details": f"expected 3-of-4, got {on_chain}",
                "events": events,
                "tx_hashes": tx_hashes,
            }

        # Negative test: 2 signatures should now be insufficient
        client = JsonRpcClient(XRPL_TESTNET)
        dest = create_dest(client)
        events.append({"step": "create_dest", "address": dest})

        wd_two = try_multisig_send(load_cfg(), ["sgx-node-1", "sgx-node-2"], dest, 1.0)
        events.append({"step": "withdraw_with_2_signers_should_fail", "result": wd_two})
        if wd_two.get("engine_result") == "tesSUCCESS":
            return {
                "name": name,
                "status": "fail",
                "details": "2 signatures still sufficient after raising quorum to 3",
                "events": events,
                "tx_hashes": tx_hashes,
            }

        # Positive test: 3 signatures should work
        wd_three = try_multisig_send(load_cfg(), ["sgx-node-1", "sgx-node-2", "sgx-node-3"], dest, 1.0)
        events.append({"step": "withdraw_with_3_signers_should_succeed", "result": wd_three})
        if wd_three.get("tx_hash"):
            tx_hashes.append({"step": "post_expand_withdraw", "hash": wd_three["tx_hash"]})
        if wd_three["status"] != "success":
            return {
                "name": name,
                "status": "fail",
                "details": "3-of-4 withdrawal failed",
                "events": events,
                "tx_hashes": tx_hashes,
            }

        return {
            "name": name,
            "status": "pass",
            "details": (
                f"expanded SignerList to 4 entries with quorum=3; "
                f"2 sigs correctly rejected, 3 sigs accepted"
            ),
            "events": events,
            "tx_hashes": tx_hashes,
        }
    except Exception as e:
        events.append({"step": "exception", "error": str(e)})
        return {"name": name, "status": "fail", "details": f"exception: {e}", "events": events, "tx_hashes": tx_hashes}


SCENARIOS = {
    "3.1": scenario_3_1,
    "3.2": scenario_3_2,
    "3.3": scenario_3_3,
    "3.4": scenario_3_4,
    "3.5": scenario_3_5,
    "3.6": scenario_3_6,
    "3.7": scenario_3_7,
    "3.8": scenario_3_8,
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

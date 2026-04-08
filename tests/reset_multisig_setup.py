#!/usr/bin/env python3
"""
Reset the entire 2-of-3 multisig test setup to a clean state.

Steps:
  1. Wipe sealed accounts on all 3 Azure nodes (kill perp-dex-server, rm
     -rf accounts/*, restart).
  2. Generate a fresh ECDSA account on each node via /v1/pool/generate.
  3. Save multisig_accounts.json with the fresh keys + xrpl addresses.
  4. Call setup_multisig_escrow.py to create a NEW XRPL testnet escrow,
     fund it via faucet, and submit a fresh SignerListSet.

Run from Hetzner where SSH tunnels to Azure enclaves are already up.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import requests
import urllib3
from xrpl.core.keypairs import derive_classic_address

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TESTS_DIR = Path(__file__).parent
ACCOUNTS_FILE = TESTS_DIR / "multisig_accounts.json"

NODES = [
    {"name": "sgx-node-1", "ip": "20.71.184.176", "tunnel_port": 9188},
    {"name": "sgx-node-2", "ip": "20.224.243.60", "tunnel_port": 9189},
    {"name": "sgx-node-3", "ip": "52.236.130.102", "tunnel_port": 9190},
]

SSH_OPTS = [
    "-i", "/home/andrey/.ssh/id_rsa",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR",
]


def azure_ssh(ip: str, cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", *SSH_OPTS, f"azureuser@{ip}", cmd],
        capture_output=True, text=True, timeout=timeout,
    )


def uncompressed_to_compressed(uncomp_hex: str) -> str:
    h = uncomp_hex[2:] if uncomp_hex.startswith("0x") else uncomp_hex
    assert h[:2] == "04"
    x, y = h[2:66], h[66:]
    prefix = "02" if int(y, 16) % 2 == 0 else "03"
    return (prefix + x).upper()


def main():
    print("=" * 60)
    print("  Reset 2-of-3 multisig test setup")
    print("=" * 60)
    print()

    fresh_accounts = []

    for node in NODES:
        print(f"[{node['name']}] wiping sealed accounts and restarting...")
        r = azure_ssh(
            node["ip"],
            "pkill -x perp-dex-server || true; sleep 1; "
            "rm -rf /home/azureuser/perp/accounts/*; "
            "bash /tmp/start2.sh"
        )
        if r.returncode != 0:
            print(f"  WARN: ssh returned {r.returncode}: {r.stderr}")
        # Wait for the local SSH-tunneled port to come back up
        for _ in range(40):
            try:
                requests.get(
                    f"https://localhost:{node['tunnel_port']}/v1/pool/status",
                    timeout=2, verify=False,
                )
                break
            except Exception:
                time.sleep(0.5)
        else:
            print(f"  ERROR: enclave on {node['name']} did not come back up")
            sys.exit(1)
        print(f"  enclave back up")

        print(f"[{node['name']}] generating fresh ECDSA account...")
        r = requests.post(
            f"https://localhost:{node['tunnel_port']}/v1/pool/generate",
            json={}, timeout=30, verify=False,
        )
        body = r.json()
        if body.get("status") != "success":
            print(f"  ERROR: generate failed: {body}")
            sys.exit(1)

        compressed = uncompressed_to_compressed(body["public_key"])
        xrpl_addr = derive_classic_address(compressed)

        acc = {
            "name": node["name"],
            "ip": node["ip"],
            "address": body["address"],
            "public_key": body["public_key"],
            "session_key": body["session_key"],
            "compressed_pubkey": compressed,
            "xrpl_address": xrpl_addr,
        }
        fresh_accounts.append(acc)
        print(f"  eth:    {acc['address']}")
        print(f"  xrpl:   {acc['xrpl_address']}")
        print()

    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(fresh_accounts, f, indent=2)
    print(f"Saved fresh accounts to {ACCOUNTS_FILE}")
    print()

    print("Now run: python3 setup_multisig_escrow.py")
    print()


if __name__ == "__main__":
    main()

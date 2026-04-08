# Failure Modes Test Report — XRPL 2-of-3 Multisig Perp DEX

**Date:** 2026-04-09
**Scope:** All 9 operator-level scenarios from `research/07-failure-modes-and-recovery.md`
**Result:** 9 of 9 PASS
**On-chain proofs:** 10 verified transactions on XRPL testnet

---

## Test environment

| Component | Value |
|---|---|
| XRPL network | testnet (`https://s.altnet.rippletest.net:51234`) |
| Escrow account | `rM44W1FkXrvwiQ6p4GLNP2yfERA12d4Qqx` |
| Initial SignerListSet | 2-of-3, quorum=2 |
| Operator A (sgx-node-1) | Azure DCsv3 `20.71.184.176`, Intel SGX, DCAP verified |
| Operator B (sgx-node-2) | Azure DCsv3 `20.224.243.60`, Intel SGX, DCAP verified |
| Operator C (sgx-node-3) | Azure DCsv3 `52.236.130.102`, Intel SGX, DCAP verified |
| Enclave signing | per-operator secp256k1 ECDSA via `/v1/pool/sign` |
| Coordinator | `tests/multisig_coordinator.py` (Python) |
| Scenarios runner | `tests/scenarios_runner.py` (Python) |

Each scenario physically stops or starts `perp-dex-server` on Azure VMs via SSH
from Hetzner, verifies XRPL on-chain state, and submits multisigned transactions
built from real ECDSA signatures produced inside the SGX enclaves. No mocks.

---

## Results

### 3.1 One operator offline

**Setup:** stop `sgx-node-3`, leave `sgx-node-1` and `sgx-node-2` alive.
**Expectation:** 2 alive signers can still produce a valid 2-of-3 multisig
withdrawal; any attempt that includes the offline signer must fail at the
signing step.

**Result:** PASS

- Multisig Payment with `[sgx-node-1, sgx-node-2]` → `tesSUCCESS`
  - tx: [`FC9C32DBCC422368888518FE143AA0715BA1D1FD6E26B5EC45DA52B471D8A1D0`](https://testnet.xrpl.org/transactions/FC9C32DBCC422368888518FE143AA0715BA1D1FD6E26B5EC45DA52B471D8A1D0)
- Attempt with `[sgx-node-1, sgx-node-3]` → `sgx-node-3 sign failed: connection refused` (blocked before submission)

### 3.2 Two operators offline

**Setup:** stop `sgx-node-2` and `sgx-node-3`; only `sgx-node-1` alive.
**Expectation:** withdrawal impossible (1 signature < quorum 2); escrow balance
unchanged; funds remain safe on XRPL.

**Result:** PASS

- 1-of-3 attempt → cannot reach quorum, no tx submitted
- Escrow balance 94.99989 XRP unchanged on XRPL

### 3.3 All three operators offline

**Setup:** stop all three enclaves.
**Expectation:** no withdrawal possible; funds fully safe on XRPL; trading
resumes after operators restart.

**Result:** PASS

- Withdrawal attempt correctly blocked at signing (no enclave to sign)
- Escrow 94.99989 XRP still accessible via XRPL RPC

### 3.4 Malicious operator (wrong signature)

**Setup:** all 3 enclaves alive; replace one signer's ECDSA signature bytes
with random garbage while keeping its account + pubkey fields.
**Expectation:** XRPL rejects the tx; retry with 2 honest signers succeeds.

**Result:** PASS

- MultiSigned tx with 1 honest + 1 garbage → rejected by XRPL
- Retry with 2 honest signers → `tesSUCCESS`
  - tx: [`90819EC6CBA5ACC549DEF5496B665BBFA959C8FA7887C4500D779B2B917ED25F`](https://testnet.xrpl.org/transactions/90819EC6CBA5ACC549DEF5496B665BBFA959C8FA7887C4500D779B2B917ED25F)

### 3.5 SGX compromise → key rotation

**Setup:** assume `sgx-node-3`'s key is compromised. Generate a fresh ECDSA key
in the same enclave, build a new SignerListSet that replaces the old key with
the new one, sign with the surviving 2 operators (`sgx-node-1` + `sgx-node-2`),
submit.

**Expectation:** on-chain SignerListSet updates; withdrawal with the new key
succeeds; the old xrpl_address is no longer a valid signer.

**Result:** PASS

- Rotated `sgx-node-3`: `rngyJoTjcapTtadGbozKFaMmo6FLGXYQX5` → `rDfPzHDVNsgWdKpuhtB8h6u2HfRbY82fsm`
- SignerListSet rotation tx: [`23E1C0EE68EB000A5C922E8D6D8A68AC042A024D1CF2FB8A437D65D47F11E809`](https://testnet.xrpl.org/transactions/23E1C0EE68EB000A5C922E8D6D8A68AC042A024D1CF2FB8A437D65D47F11E809)
- Post-rotation withdrawal with new key: [`8274091DFB2A0FA83B33473E31A60E90E24C832DA9B12788259D4C5DD5887F14`](https://testnet.xrpl.org/transactions/8274091DFB2A0FA83B33473E31A60E90E24C832DA9B12788259D4C5DD5887F14)

### 3.6 Hardware failure → replacement node

**Setup:** wipe `sgx-node-2`'s sealed accounts directory
(`/home/azureuser/perp/accounts/*`), restart the enclave (empty pool), generate
a fresh key, rotate SignerListSet with the surviving 2 operators (sgx-node-1
+ rotated sgx-node-3).

**Expectation:** full hardware-loss recovery path works without access to the
old private key.

**Result:** PASS

- Replaced `sgx-node-2` with new key `rDtwxkiRyAVTHsNnGjtnXmGzH65w8fTp1p`
- SignerListSet replacement tx: [`B056CA00778054F041335F05054B106E6CBA22713A33611CCCFC924B19E1A686`](https://testnet.xrpl.org/transactions/B056CA00778054F041335F05054B106E6CBA22713A33611CCCFC924B19E1A686)
- Post-replacement withdrawal: [`F455EBCCBC7B858854E1A1DCCEC86430C53897319BFE6C1D11083B280C68F7BE`](https://testnet.xrpl.org/transactions/F455EBCCBC7B858854E1A1DCCEC86430C53897319BFE6C1D11083B280C68F7BE)

### 3.7 Cloud migration

**Setup:** migrate `sgx-node-1` to a new host (simulated by generating a fresh
key on the same enclave — functionally equivalent from XRPL's perspective),
rotate via surviving 2 of 3.

**Expectation:** migration works identically to key rotation; no downtime for
the other 2 operators.

**Result:** PASS

- Migrated `sgx-node-1` to new key `rEGTRV8gtRJjpr1NtRb1nVp3bXtVgTWTWe`
- Migration tx: [`8899292EE67D800A136741C9A3950054248658625156AD7C23E4CD24E7CA3E23`](https://testnet.xrpl.org/transactions/8899292EE67D800A136741C9A3950054248658625156AD7C23E4CD24E7CA3E23)
- Post-migration withdrawal: [`8931EFAA52AED2351D7BAE0313B84B6157386CD7B73389C4190FF5E4B975CBBB`](https://testnet.xrpl.org/transactions/8931EFAA52AED2351D7BAE0313B84B6157386CD7B73389C4190FF5E4B975CBBB)

### 3.8 Scaling 2-of-3 → 3-of-4

**Setup:** generate a 4th ECDSA key (2nd account on `sgx-node-1`'s enclave),
build a new SignerListSet with 4 entries and `signer_quorum=3`, submit.

**Expectation:** after expansion, 2 signatures are no longer enough (must fail);
3 signatures are required (must succeed).

**Result:** PASS

- Expansion tx: [`B992884B8A19204014AD59D899B0C66D5F3AFF69625C7795E1A5D7E3D80DAA8B`](https://testnet.xrpl.org/transactions/B992884B8A19204014AD59D899B0C66D5F3AFF69625C7795E1A5D7E3D80DAA8B)
- Negative check: withdrawal with 2 signers → correctly rejected (insufficient quorum)
- Positive check: withdrawal with 3 signers: [`49629B8F72E8E1624B6C781DEBED3E5D734BA27530492A7A5B2D2C2AFCC7E38F`](https://testnet.xrpl.org/transactions/49629B8F72E8E1624B6C781DEBED3E5D734BA27530492A7A5B2D2C2AFCC7E38F)

### 3.9 Catastrophic recovery (XRPL ledger as source of truth)

**Setup:** read-only scenario. Query `account_tx` for the escrow account and
verify that the full history (all Payments and SignerListSet updates performed
by scenarios 3.1–3.8) is present, plus the current SignerList and balance.

**Expectation:** a full rebuild of operator state is possible from the XRPL
ledger alone, without any local database or off-chain data.

**Result:** PASS

- 11 transactions on record: 5 SignerListSet updates + 6 Payments
- Final quorum 3-of-4 (from scenario 3.8)
- Escrow balance 89.99859 XRP
- Explorer: https://testnet.xrpl.org/accounts/rM44W1FkXrvwiQ6p4GLNP2yfERA12d4Qqx

---

## Summary

All 9 failure-mode scenarios pass end-to-end against real Intel SGX enclaves
on Azure DCsv3 and real XRPL testnet transactions. The full verification took
approximately 5 minutes of wall-clock time to execute all 9 scenarios back to
back via `python3 tests/scenarios_runner.py all`.

Key findings validated on-chain:

1. **Liveness:** the system tolerates 1 of 3 operators offline and continues to
   settle withdrawals. With 2 of 3 offline it correctly fails closed — no
   partial settlements. Funds remain safe on XRPL regardless of operator state.
2. **Byzantine tolerance:** an operator returning a garbage ECDSA signature
   does NOT poison the transaction — XRPL's SignerListSet verification rejects
   it, and a retry with the other honest operators succeeds.
3. **Key rotation / hardware failure / cloud migration** are the same mechanism:
   generate a new key on the target enclave, submit a SignerListSet update via
   the surviving quorum. No access to old private keys is required — the XRPL
   escrow account outlives any single operator's key material.
4. **Scaling works online:** the SignerListSet quorum and entry count can be
   changed without downtime; the new quorum takes effect immediately for
   subsequent transactions.
5. **Catastrophic recovery** is backed by XRPL itself. The full withdrawal
   history and current authorization state are queryable from any XRPL node
   without trusting any operator.

## Reproducing the test

```bash
# On Hetzner (has SSH tunnels to the 3 Azure enclaves on localhost:9188-9190)
cd /tmp/perp-9088
python3 reset_multisig_setup.py         # wipe sealed accounts on all 3 nodes
python3 setup_multisig_escrow.py        # new faucet-funded escrow + SignerListSet
python3 update_escrow_urls.py multisig_escrow.json  # point enclave_url at tunnels
python3 scenarios_runner.py all --out scenarios_full_report.json
```

The JSON report includes per-scenario events and on-chain tx hashes for
independent verification via https://testnet.xrpl.org.

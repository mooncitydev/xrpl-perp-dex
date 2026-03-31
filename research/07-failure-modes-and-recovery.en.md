# Failure Modes and Recovery

**Date:** 2026-03-31
**Status:** Design
**Context:** XRPL native multisig 2-of-3 (SignerListSet), 3 SGX operators, XRPL mainnet settlement

---

## Base Model

```
Operator A (Hetzner)     Operator B (Azure)      Operator C (OVH)
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│ SGX Enclave  │         │ SGX Enclave  │         │ SGX Enclave  │
│ ECDSA Key A  │         │ ECDSA Key B  │         │ ECDSA Key C  │
│ Sealed State │         │ Sealed State │         │ Sealed State │
└──────────────┘         └──────────────┘         └──────────────┘
```

- **Escrow account** on XRPL: SignerListSet = [rA, rB, rC], quorum=2, master key disabled
- **Signing threshold**: 2 out of 3 operators are sufficient for multisig signing
- **State**: sealed inside each enclave (MRENCLAVE-bound)
- **Funds**: RLUSD on XRPL mainnet, controlled by SignerListSet multisig

---

## 1. One Operator Offline

### Scenario
Operator C loses connectivity (server crash, network outage, maintenance).

### Impact
| Function | Status | Explanation |
|----------|--------|-------------|
| Trading | ✅ Works | Order book in orchestrator, not in enclave |
| Deposits | ✅ Works | XRPL monitoring by any live operator |
| Withdrawals | ✅ Works | Multisig 2-of-3: A+B sign without C |
| Liquidations | ✅ Works | Any live operator executes |
| Funding | ✅ Works | Any live operator applies |
| State persistence | ✅ Works | Each instance saves its own state |

### Actions
- None. The system continues operating.
- Alert operator C to restore service.

### Recovery of C
1. C restarts the server
2. Enclave loads sealed state from disk (`ecall_perp_load_state`)
3. C replicates missed state updates from A or B
4. C returns to rotation

**User downtime: 0**

---

## 2. Two Operators Offline

### Scenario
Only Operator A is alive. B and C are unreachable.

### Impact
| Function | Status | Explanation |
|----------|--------|-------------|
| Trading | ✅ Works | Order book in orchestrator A |
| Deposits | ✅ Works | A monitors XRPL |
| **Withdrawals** | ❌ **Blocked** | Multisig requires 2-of-3, A alone cannot sign |
| Liquidations | ⚠️ Partial | Internal liquidations work, but margin withdrawal does not |
| Funding | ✅ Works | |
| State persistence | ✅ Works | |

### Actions
- Trading continues, but withdrawals are suspended
- Funds are safe on XRPL escrow (A cannot withdraw alone)
- Wait for at least one of B/C to recover

### Criticality
- **Funds are not lost** — escrow on XRPL, key inside SGX
- **Withdrawal queue** — withdrawal requests accumulate, executed after recovery
- **Max downtime risk**: if the situation persists, users cannot withdraw funds

**Time without withdrawals: until one of B/C recovers**

---

## 3. All Three Operators Offline

### Scenario
All servers are simultaneously unreachable (disaster, coordinated attack, error).

### Impact
| Function | Status |
|----------|--------|
| Everything | ❌ Stopped |

### Fund Safety
- **RLUSD on XRPL escrow** — funds are on-chain, not on servers
- **Nobody can withdraw** — neither operators nor attacker (no 2-of-3 multisig signature)
- **XRPL ledger** — immutable, funds are publicly visible

### Recovery
1. **Scenario A: servers come back** — each enclave loads sealed state, system restarts
2. **Scenario B: hardware destroyed** — Shamir backup recovery (see section 9)

---

## 4. One Malicious Operator

### Scenario
Operator B attempts to steal funds or manipulate trading.

### What B Can Do
| Action | Possible? | Why |
|--------|-----------|-----|
| Steal funds | ❌ No | Requires 2-of-3 ECDSA signatures (multisig), B has only 1 key |
| Sign a fake withdrawal | ❌ No | A and C will not sign an invalid transaction |
| Stop withdrawals | ⚠️ Partially | If B = one of two live operators, can refuse to sign. But A+C still = 2-of-3 |
| Manipulate price | ⚠️ Limited | If B = sequencer, can delay orders. Mitigation: sequencer rotation |
| See orders | ❌ No | Orders are encrypted for TEE (anti-MEV) |
| Extract key from SGX | ❌ No* | SGX hardware protection. *Theoretical side-channel attacks |

### Actions
- A and C detect anomaly (e.g., B refuses to sign valid withdrawals)
- A+C together = 2-of-3 → continue operating without B
- B is excluded from rotation

---

## 5. SGX Compromise (Side-Channel Attack)

### Scenario
Attacker extracts an ECDSA key from one enclave via a side-channel vulnerability (Spectre, Foreshadow, etc.).

### Impact
- Leak of 1 key out of 3 — **insufficient for signing** (need 2-of-3 multisig)
- Attacker needs 2 keys for multisig 2-of-3
- Compromise of one SGX does not grant access to funds

### Actions
1. Intel releases a microcode update for the vulnerability
2. Update SGX microcode on the compromised server
3. Rebuild the enclave (new MRENCLAVE)
4. **Key rotation**: each instance generates a new ECDSA keypair -> update SignerListSet -> transfer funds to new escrow
5. Old keys are useless after key rotation

### Key Rotation Protocol
```
1. All 3 instances generate new ECDSA keypairs → new XRPL addresses (rA', rB', rC')
2. Create new escrow account with SignerListSet: [rA', rB', rC'], quorum=2
3. Multisig signing (2-of-3): transfer RLUSD from old escrow to new
4. Update configuration
5. Old keys can be safely deleted
```

---

## 6. Hardware Failure (SGX CPU)

### Scenario
The CPU with SGX on server B has physically failed. Sealed data on disk cannot be decrypted (bound to MRENCLAVE + CPU key).

### Impact
- ECDSA key B is lost
- A + C = 2-of-3 multisig → **system continues operating**
- But there is no redundancy now — losing one more operator = loss of signing capability

### Actions
1. **Immediately**: A+C continue operating (withdrawals, trading — all OK)
2. **Urgently**: key rotation — D generates a new ECDSA key -> update SignerListSet to [A, D, C]
3. Transfer funds to new escrow
4. Old escrow is empty, can be discarded

### Recovery Time
- If D is already prepared (standby): ~5 minutes (keygen + SignerListSet update + transfer)
- If D needs to be deployed: ~1-2 hours (provision Azure VM + install SGX + keygen + SignerListSet)

---

## 7. Migration: Changing Cloud Provider

### Question from 8Baller: "Can operators change cloud provider?"

### Answer: Yes, without loss of funds.

### Procedure
```
Current: A (Hetzner), B (Azure), C (OVH)
Target:  A (Hetzner), B (AWS), C (OVH)   ← B migrates Azure → AWS

1. Deploy new SGX instance D on AWS
2. D generates ECDSA keypair inside enclave → address rD
3. Update SignerListSet: [rA, rD, rC], quorum=2 (multisig signing by A+C)
4. Update configuration: D replaces B
5. Shut down B (Azure)

Migration time: ~30 minutes
Time without withdrawals: ~5 minutes (only during the transfer moment)
```

### Key Point
- **No need** to export keys from SGX
- **No need** to trust the new provider — the key is generated INSIDE the new enclave
- Funds are always on XRPL — not on servers
- Remote attestation on D confirms the code is the same (MRENCLAVE)

---

## 8. Scaling: "Books Get Too Big"

### Question from 8Baller: "Can they move to a more performant box?"

### Answer: Yes, step by step.

### Order Book
The order book lives in the **orchestrator (Rust)**, not in the enclave. No SGX limitations:
- Horizontal scaling of the orchestrator
- In-memory order book → can move to a more powerful server at any time
- No sealed state for the order book — stateless restart

### Enclave State
The enclave stores only balances + positions + margin (~25 KB for PoC, ~5 MB for production):
- On growth: partitioned sealing (seal in parts)
- On rebalancing: key rotation to a more powerful server

### Upgrade Procedure
```
1. Deploy new powerful SGX server D
2. Key rotation: SignerListSet [rA,rB,rC] → [rA,rD,rC]  (B is replaced by D)
3. Transfer funds
4. Orchestrator on D handles a larger order book
```

---

## 9. Catastrophic Recovery: All 3 Servers Destroyed

### Scenario
All three operators simultaneously lost access to sealed data (data center fire, coordinated server seizure).

### Backup: Shamir's Secret Sharing for Master Key

During initial setup (ECDSA keygen + SignerListSet):
1. Each enclave generates an **encrypted state export** encrypted with a master key
2. The master key is split via Shamir 3-of-5 among trusted custodians
3. Encrypted backups are stored outside the enclave (on USB, in a safe, in a bank)

### Recovery
```
1. 3 of 5 custodians gather and provide Shamir shares
2. Reconstruct the master key INSIDE a new attested enclave
3. Decrypt backup → restore state + ECDSA keys
4. New enclaves begin operating
5. Key rotation is recommended after recovery
```

### Alternative: XRPL as Source of Truth
Even without Shamir backup:
- All deposits are visible on the XRPL ledger
- It is possible to reconstruct who deposited how much
- Open positions are lost (off-chain state), but collateral is safe
- **Worst case**: pro-rata distribution of escrow balance based on XRPL deposit history

---

## 10. Risk Summary Table

| # | Scenario | Trading | Withdrawals | Funds | Recovery |
|---|----------|---------|-------------|-------|----------|
| 1 | 1 operator offline | ✅ | ✅ (2-of-3) | ✅ | Automatic |
| 2 | 2 operators offline | ✅ | ❌ Waiting | ✅ | Wait for 1 to recover |
| 3 | All 3 offline | ❌ | ❌ | ✅ (XRPL) | Shamir / restart |
| 4 | 1 malicious | ✅ | ✅ (2 honest) | ✅ | Exclude from rotation |
| 5 | SGX side-channel | ✅ | ✅ | ✅ (1 key not enough) | Key rotation |
| 6 | Hardware failure | ✅ | ✅ (2-of-3) | ✅ | Key rotation + SignerListSet update |
| 7 | Provider migration | ✅ | ⚠️ 5 min | ✅ | Keygen + SignerListSet update |
| 8 | Scaling | ✅ | ⚠️ 5 min | ✅ | Key rotation + SignerListSet |
| 9 | Catastrophic (all 3) | ❌ | ❌ | ✅ (XRPL) | Shamir 3-of-5 |

---

## 11. Threshold Flexibility: Not Just 2-of-3

XRPL SignerListSet supports up to 32 signers in a single SignerList. Each signer has a weight, and the quorum is set arbitrarily.

### Supported Configurations

| Scheme | Operators | To Sign | Tolerated Failures | Signing Latency | Use Case |
|---|---|---|---|---|---|
| 2-of-3 | 3 | 2 | 1 | ~100 ms | PoC, small team |
| 3-of-5 | 5 | 3 | 2 | ~150 ms | Production, good balance |
| 5-of-9 | 9 | 5 | 4 | ~200 ms | High decentralization |
| 7-of-11 | 11 | 7 | 4 | ~250 ms | Maximum decentralization |
| 16-of-32 | 32 | 16 | 16 | ~500 ms | Maximum XRPL SignerList |

### Choosing the Threshold

- **t too low** (e.g., 2-of-9): easy to sign, but easy to collude (2 malicious actors suffice)
- **t too high** (e.g., 8-of-9): secure against collusion, but 2 operators offline = withdrawals blocked
- **Recommendation**: t = ⌈n/2⌉ + 1 (simple majority + 1)

| n | Recommended t | Tolerated Failures | Collusion Requires |
|---|---|---|---|
| 3 | 2 | 1 | 2 (67%) |
| 5 | 3 | 2 | 3 (60%) |
| 7 | 4 | 3 | 4 (57%) |
| 9 | 5 | 4 | 5 (56%) |

### Setup Latency for Different n

Keygen + SignerListSet is performed **once** when creating the escrow:

| n | ECDSA keygen (parallel) | SignerListSet tx | Total | Note |
|---|---|---|---|---|
| 3 | ~10 ms | ~4 sec | ~4 sec | Current PoC |
| 5 | ~10 ms | ~4 sec | ~4 sec | |
| 9 | ~10 ms | ~4 sec | ~4 sec | |
| 32 | ~10 ms | ~4 sec | ~4 sec | Maximum XRPL, one-time operation |

**Setup latency does not affect trading** — it is a one-time operation. Unlike DKG, keygen does not require data exchange between instances.

### Signing Latency for Different t

Multisig signing: orchestrator sends tx to t instances in parallel, collects ECDSA signatures, assembles Signers array:

```
signing_latency ≈ max(round_trip_time_to_each_signer) + assembly_time
                ≈ ~100-200 ms (single network round-trip, parallel to all signers)
```

In practice for t <= 32: **< 500 ms**, negligible compared to XRPL settlement (3-5 sec).

### Multiple Escrow Accounts

Each escrow account has its own independent SignerListSet:
- Escrow 0: main escrow (RLUSD collateral)
- Escrow 1: insurance fund
- Escrow 2: protocol treasury
- Escrow 3: reserve

Each escrow can have its own quorum and set of signers (e.g., treasury = 3-of-5, trading = 2-of-3).

> **Note:** FROST/DKG remains available in the enclave for Bitcoin Taproot use cases, but is not used for XRPL operations.

---

## 12. Infrastructure Guarantees

### What Is Protected by Hardware (Intel SGX)
- Private ECDSA keys — never leave the enclave
- State in memory — isolated from OS and operator
- Sealed data — encrypted with CPU key + MRENCLAVE

### What Is Protected by Protocol (XRPL SignerListSet 2-of-3)
- No single operator can sign alone (quorum=2)
- Stealing funds requires compromising 2 out of 3 SGX enclaves
- Key rotation via SignerListSet update without service interruption

### What Is Protected by XRPL
- Funds are always on-chain (RLUSD on escrow)
- Deposit history — permanent, auditable
- Settlement — atomic, final within 3-5 seconds

### What Is NOT Protected
- Off-chain state (positions, PnL) — loss of all 3 servers = loss of state
- Order book — lives in orchestrator RAM, not persistent
- Funding rate history — computed on the fly

### Mitigations for Unprotected Items
- Periodic state sealed backups (every 5 minutes)
- Encrypted state exports (Shamir backup)
- XRPL deposit history as last-resort source of truth

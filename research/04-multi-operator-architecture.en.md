# Multi-Operator Architecture

**Date:** 2026-03-30
**Status:** Design
**Dependency:** FROST 2-of-3 (already implemented in enclave)

---

## Problem

Single operator = single point of failure:
- Operator offline → trading halted, liquidations do not work
- Malicious operator → can delay withdrawals (though cannot steal funds — keys are in SGX)
- Single server → hardware failure = downtime

---

## Solution: 2-of-3 Operators

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Operator A     │     │   Operator B     │     │   Operator C     │
│   (Sequencer)    │     │   (Validator)    │     │   (Validator)    │
│                  │     │                  │     │                  │
│ ┌──────────────┐ │     │ ┌──────────────┐ │     │ ┌──────────────┐ │
│ │SGX Enclave   │ │     │ │SGX Enclave   │ │     │ │SGX Enclave   │ │
│ │FROST Share 1 │ │     │ │FROST Share 2 │ │     │ │FROST Share 3 │ │
│ └──────────────┘ │     │ └──────────────┘ │     │ └──────────────┘ │
│ ┌──────────────┐ │     │ ┌──────────────┐ │     │ ┌──────────────┐ │
│ │Orchestrator  │ │     │ │Orchestrator  │ │     │ │Orchestrator  │ │
│ │(Sequencer)   │ │     │ │(Replica)     │ │     │ │(Replica)     │ │
│ └──────────────┘ │     │ └──────────────┘ │     │ └──────────────┘ │
│ ┌──────────────┐ │     │ ┌──────────────┐ │     │ ┌──────────────┐ │
│ │HAProxy       │ │     │ │HAProxy       │ │     │ │HAProxy       │ │
│ └──────────────┘ │     │ └──────────────┘ │     │ └──────────────┘ │
└────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
         │                        │                        │
         │    P2P gossip protocol (state + signing)        │
         └────────────────────────┼────────────────────────┘
                                  │
                                  ▼
                            XRPL Mainnet
                          (escrow account)
                      group key = FROST 2-of-3
```

---

## Roles

### Sequencer (1 operator)

- Accepts all user orders
- Builds authoritative state (positions, balances)
- Determines transaction ordering
- Broadcasts state updates to validators
- Initiates FROST signing rounds for withdrawals

### Validators (2 operators)

- Receive state updates from the sequencer
- Verify correctness (margin checks, PnL calculations)
- Participate in FROST signing (2-of-3 for withdrawals)
- Can refuse to sign if state is incorrect
- If sequencer fails → one of the validators becomes the sequencer (failover)

---

## Protocols

### 1. State Replication

```
Sequencer                    Validator B              Validator C
    │                            │                        │
    │ ── state_update(batch) ──► │                        │
    │ ── state_update(batch) ──────────────────────────► │
    │                            │                        │
    │                     verify(batch)            verify(batch)
    │                            │                        │
    │ ◄── ack/nack ──────────── │                        │
    │ ◄── ack/nack ──────────────────────────────────── │
```

**State batch** contains:
- List of operations (deposits, trades, liquidations, funding)
- Resulting state hash
- Sequencer signature

Validators replay operations deterministically and verify the state hash.

### 2. FROST Withdrawal Signing

```
User: "withdraw 50 RLUSD to rXXX"
    │
    ▼
Sequencer:
    1. Margin check → OK
    2. Build XRPL Payment tx
    3. Compute tx hash (SHA-512Half)
    4. FROST nonce gen (share 1)
    5. Request nonces from validators
    │
    ├──► Validator B: nonce gen (share 2) ──► partial sign
    ├──► Validator C: nonce gen (share 3) ──► partial sign
    │
    6. Aggregate: 2-of-3 partial sigs → final Schnorr sig
    7. Submit signed tx to XRPL
```

At least 2 of 3 operators must participate. If one is offline, the remaining 2 can still sign.

### 3. Price Consensus

```
Operator A: fetch_price() → $1.34
Operator B: fetch_price() → $1.34
Operator C: fetch_price() → $1.35
                    │
                    ▼
            median($1.34, $1.34, $1.35) = $1.34
```

Each operator fetches the price independently. The sequencer uses the median of all 3. If one operator manipulates the price, the median provides protection.

### 4. Sequencer Failover

```
Normal:     A = Sequencer,  B,C = Validators
A offline:  B = Sequencer,  C = Validator    (A rejoins as Validator)
B offline:  A = Sequencer,  C = Validator
A+B offline: C = Sequencer (degraded mode, no FROST signing possible
                             until at least one more operator rejoins)
```

Failover via heartbeat timeout:
- Sequencer sends a heartbeat every 5 seconds
- If heartbeat is missed 3 times (15 sec) → validators elect a new sequencer
- Election: by predefined priority (A > B > C)

---

## Already Implemented

| Component | Status | Location |
|-----------|--------|----------|
| FROST 2-of-3 keygen | ✅ Done | Enclave: ecall_frost_keygen |
| FROST DKG (distributed) | ✅ Done | Enclave: ecall_dkg_* |
| FROST nonce gen | ✅ Done | Enclave: ecall_frost_nonce_gen |
| FROST partial sign | ✅ Done | Enclave: ecall_frost_partial_sign |
| FROST sig aggregation | ✅ Done | Enclave: ecall_frost_partial_sig_agg |
| Sealed share export/import | ✅ Done | Enclave: ecall_frost_share_export/import |
| Margin engine | ✅ Done | Enclave: ecall_perp_* |
| Single-operator orchestrator | ✅ Done | Rust binary |

## To Be Added

| Component | Complexity | Description |
|-----------|------------|-------------|
| P2P gossip | Medium | libp2p or simple TCP mesh for state replication |
| State batch protocol | Medium | Serialization + batch signing |
| Sequencer election | Low | Priority-based with heartbeat |
| FROST signing coordinator | Medium | Orchestrator coordinates nonce exchange + partial signing |
| Price consensus | Low | Median from 3 operators |
| Deterministic state replay | Medium | Validators replay operations and verify hash |

---

## Trust Model

| Scenario | Outcome |
|----------|---------|
| 1 malicious operator | Cannot steal funds (requires 2-of-3). Can delay signing if they are one of the two. |
| 1 operator offline | System operates normally (2-of-3 signing, failover). |
| 2 operators offline | Trading continues on the remaining one (it becomes sequencer), but withdrawals are blocked (need 2 for FROST). |
| 2 operators collude | Can sign any withdrawal. Risk: collusion. Mitigation: operators are legally/geographically separated. |
| All 3 offline | Trading halted. Funds are safe in XRPL escrow. Recovery via Shamir backup keys. |

---

## Operator Hosting

For maximum decentralization — different providers with SGX:

| Operator | Provider | SGX Hardware |
|----------|----------|--------------|
| A | Hetzner (current dev server) | Intel Xeon E-2388G |
| B | Azure Confidential Computing | DCsv3 (SGX-enabled VM) |
| C | OVH / Equinix Metal | Bare metal with SGX |

Each operator:
- Runs their own enclave with identical MRENCLAVE
- Holds their own FROST share (sealed, never leaves the enclave)
- Is verified via remote attestation (users verify MRENCLAVE)

# Multi-Operator Architecture

**Date:** 2026-03-30
**Status:** Design
**Dependency:** XRPL native multisig (SignerListSet) + ECDSA keys in enclave

> **Note on signing:** XRPL uses ECDSA (secp256k1), not Schnorr. Threshold signing on XRPL is achieved via native SignerListSet (multi-signature), not FROST. Each SGX instance holds an independent ECDSA key. The enclave also supports FROST for Bitcoin Taproot operations.

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
│ │ECDSA Key A   │ │     │ │ECDSA Key B   │ │     │ │ECDSA Key C   │ │
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
                 SignerListSet: [rA, rB, rC], quorum=2
```

---

## Roles

### Sequencer (1 operator)

- Accepts all user orders
- Builds authoritative state (positions, balances)
- Determines transaction ordering
- Broadcasts state updates to validators
- Initiates multisig signing for withdrawals (collects 2 ECDSA signatures)

### Validators (2 operators)

- Receive state updates from the sequencer
- Verify correctness (margin checks, PnL calculations)
- Participate in multisig signing (2-of-3 ECDSA signatures for withdrawals)
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

### 2. Multisig Withdrawal Signing (XRPL SignerListSet)

```
User: "withdraw 50 RLUSD to rXXX"
    │
    ▼
Sequencer (orchestrator):
    1. Margin check → OK
    2. Build XRPL Payment tx
    3. Send tx to Enclave A → ECDSA sign (key A)
    4. Send tx to Enclave B → ECDSA sign (key B)
    │
    5. Assemble Signers array: [sig_A, sig_B]
    6. Submit multisig tx to XRPL
```

At least 2 of 3 operators must sign (quorum=2 in SignerListSet). If one is offline, the remaining 2 can still sign.

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
A+B offline: C = Sequencer (degraded mode, no multisig possible
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
| ECDSA keypair generation | ✅ Done | Enclave: each instance generates an independent ECDSA key |
| XRPL SignerListSet setup | ✅ Done | Orchestrator: configures multisig on escrow account |
| ECDSA signing (secp256k1) | ✅ Done | Enclave: ecall_sign (XRPL transactions) |
| FROST (for Bitcoin Taproot) | ✅ Done | Enclave: ecall_frost_* / ecall_dkg_* (not for XRPL) |
| Margin engine | ✅ Done | Enclave: ecall_perp_* |
| Single-operator orchestrator | ✅ Done | Rust binary |

## To Be Added

| Component | Complexity | Description |
|-----------|------------|-------------|
| P2P gossip | Medium | libp2p or simple TCP mesh for state replication |
| State batch protocol | Medium | Serialization + batch signing |
| Sequencer election | Low | Priority-based with heartbeat |
| Multisig signing coordinator | Medium | Orchestrator collects ECDSA signatures from 2 instances, assembles Signers array |
| Price consensus | Low | Median from 3 operators |
| Deterministic state replay | Medium | Validators replay operations and verify hash |

---

## Trust Model

| Scenario | Outcome |
|----------|---------|
| 1 malicious operator | Cannot steal funds (requires 2-of-3). Can delay signing if they are one of the two. |
| 1 operator offline | System operates normally (2-of-3 signing, failover). |
| 2 operators offline | Trading continues on the remaining one (it becomes sequencer), but withdrawals are blocked (need 2 ECDSA signatures for multisig). |
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
- Holds their own independent ECDSA key (sealed, never leaves the enclave)
- Is verified via remote attestation (users verify MRENCLAVE)

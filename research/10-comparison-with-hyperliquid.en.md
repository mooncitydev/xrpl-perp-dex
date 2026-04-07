# Comparison with Hyperliquid

**Date:** 2026-04-07
**Status:** Analysis

---

## Overview

Hyperliquid and our TEE-based Perp DEX solve the same problem — high-performance
perpetual futures trading — but with fundamentally different architectures.

| | Hyperliquid | TEE Perp DEX (XRPL) |
|---|---|---|
| **Chain** | Custom L1 (HyperL1) | XRPL mainnet |
| **Matching** | On-chain (on their L1) | Off-chain (Orchestrator CLOB) |
| **Consensus** | HyperBFT (Hotstuff derivative) | Single sequencer + priority failover |
| **Settlement** | Arbitrum bridge (USDC) | XRPL native (RLUSD) |
| **Fund custody** | Bridge multisig (validators) | XRPL escrow (SignerListSet 2-of-3) |
| **Code verifiability** | Closed-source | DCAP remote attestation (SGX) |

---

## Architecture comparison

### Hyperliquid

```
User → HyperL1 (custom blockchain)
         │
         ├── HyperBFT consensus (4+ validators)
         ├── On-chain order book + matching
         └── Arbitrum bridge for deposits/withdrawals
```

Hyperliquid built an **entire L1 blockchain** purpose-built for perp trading.
All orders, matches, and state transitions are on-chain transactions on HyperL1.
HyperBFT provides sub-second block times (~0.2s) but with a small, permissioned
validator set.

### TEE Perp DEX

```
User → nginx → Orchestrator (Rust CLOB)
                     │
                     ├── SGX Enclave (margin, signing)
                     └── XRPL mainnet (settlement)
```

We use an **existing L1** (XRPL) for settlement and custody, with TEE for
computation that XRPL can't do natively (margin engine, order matching).
No new blockchain required.

---

## Key differences

### 1. Trust model

| Aspect | Hyperliquid | TEE Perp DEX |
|--------|-------------|--------------|
| Who controls funds | HyperBFT validators (bridge multisig) | XRPL escrow (L1-native multisig) |
| Honest majority needed | Yes (BFT: ⅔ validators) | No — TEE enforces rules in hardware |
| Validator collusion risk | **High** — validators control bridge | **Low** — each operator has 1 key, need 2-of-3 |
| Censorship | Validators can censor txs | Sequencer can delay but not steal |

The Hyperliquid JELLY incident (March 2025) demonstrated this: validators unilaterally
intervened in market operations when a trader exploited the system. The validators
acted as a centralized authority, contradicting the "decentralized" narrative.

In our system, the TEE enforces margin rules regardless of operator intent. The operator
cannot override the enclave's margin check — it's hardware-enforced.

### 2. Settlement layer

| | Hyperliquid | TEE Perp DEX |
|---|---|---|
| Deposit | USDC on Arbitrum → bridge → HyperL1 | RLUSD on XRPL → escrow account |
| Withdrawal | HyperL1 → bridge → Arbitrum (validator signatures) | Enclave signs → XRPL Payment |
| Bridge risk | **Yes** — bridge is the #1 attack vector | **No bridge** — XRPL is both settlement and custody |
| Finality | HyperL1 sub-second, Arbitrum ~7 days for L1 | XRPL 3-4 seconds |

Bridges are the most attacked component in DeFi. Hyperliquid's entire TVL ($2B+) sits
behind a bridge controlled by 4 validators. Our funds sit in an XRPL escrow account
controlled by L1-native multisig — no bridge.

### 3. Verifiability

| | Hyperliquid | TEE Perp DEX |
|---|---|---|
| Matching engine code | **Closed source** | Open source (BSL 1.1) |
| Can users verify execution? | No — must trust validators | **Yes** — DCAP attestation proves enclave code |
| State proofs | None published | TEE-signed Merkle root on Ethereum (Sepolia) |

With DCAP remote attestation, anyone can cryptographically verify that the enclave
runs the exact published code. Hyperliquid provides no such guarantee — users must
trust that the validators run honest software.

### 4. Performance

| | Hyperliquid | TEE Perp DEX |
|---|---|---|
| Claimed TPS | 100,000+ orders/sec | ~200 orders/sec (single enclave) |
| Matching latency | ~0.2s (block time) | ~5ms (CLOB) + enclave call |
| Settlement | Sub-second (HyperL1) | 3-4 seconds (XRPL) |

Hyperliquid is faster — they built an entire L1 optimized for this. Our bottleneck
is XRPL settlement (3-4 seconds). However, order matching in our CLOB is ~5ms,
and most operations don't need to wait for XRPL settlement.

For the target market (XRPL ecosystem, RLUSD holders), 3-4 second settlement
is acceptable — comparable to centralized exchanges.

### 5. Custody model

| | Hyperliquid | TEE Perp DEX |
|---|---|---|
| Who can steal funds | Majority of validators (bridge multisig) | Nobody — enclave enforces margin rules, XRPL enforces multisig |
| Single point of failure | Bridge contract | None (2-of-3 operators) |
| Regulatory clarity | Unclear (custom L1, bridge) | XRPL mainnet (Ripple-regulated RLUSD) |

---

## What Hyperliquid does better

1. **Performance** — purpose-built L1 is faster than using an existing L1
2. **Ecosystem** — large trading community, $2B+ TVL
3. **Market diversity** — hundreds of perp markets
4. **Orderbook on-chain** — every order is a permanent record

## What we do better

1. **No bridge** — funds on XRPL L1, not behind a bridge
2. **Verifiable** — DCAP attestation, open source
3. **No new chain** — leverages XRPL's existing security
4. **Regulated stablecoin** — RLUSD settlement
5. **Hardware-enforced rules** — TEE prevents operator misbehavior

---

## Conclusion

Hyperliquid is the "build a new blockchain" approach. We are the "extend an existing
blockchain with TEE" approach. Both are valid — they optimize for different things.

Hyperliquid optimizes for **performance** at the cost of centralization (small validator
set, bridge custody, closed source).

We optimize for **trust minimization** at the cost of performance (XRPL settlement
latency, single-threaded enclave). Users can verify the code running in the enclave,
funds never leave XRPL, and no bridge is required.

For the XRPL ecosystem and RLUSD holders specifically, a TEE approach is more natural
than bridging to a new L1.

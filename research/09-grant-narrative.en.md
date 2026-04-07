# Grant Application: Perpetual Futures DEX on XRPL

**Project:** TEE-Secured Perpetual Futures DEX with RLUSD Settlement
**Team:** ph18.io
**Date:** 2026-04-07
**Status:** Draft — awaiting grant form

---

## Problem

XRPL has no native smart contract support. This makes it impossible to build complex DeFi
protocols — perpetual futures, options, lending — directly on the ledger. Projects either
move to sidechains (losing XRPL's security guarantees) or build centralized services
(losing trustlessness).

RLUSD, Ripple's regulated stablecoin, has no DeFi ecosystem on XRPL mainnet. Users
who hold RLUSD have nowhere to deploy it for yield or hedging — the only option is
sending it to Ethereum or Solana bridges.

---

## Solution

We replace smart contracts with **Trusted Execution Environments (Intel SGX)**. The
enclave runs the same logic a smart contract would — margin engine, position tracking,
withdrawal signing — but with hardware-enforced integrity. The XRPL ledger is used
for what it does best: settlement.

```
User → nginx (TLS) → Orchestrator (Rust) → SGX Enclave (C/C++)
                                                  │
                                                  ▼
                                            XRPL Mainnet
                                         (RLUSD settlement)
```

### Why TEE instead of smart contracts?

| Smart Contracts (Solidity, Move) | TEE (Intel SGX) |
|----------------------------------|-----------------|
| Requires chain-level support | Works with any chain, including XRPL |
| Code is public (MEV, front-running) | Code runs in encrypted memory |
| Gas costs per operation | No gas — computation is free |
| Upgrades require governance | Upgrades require attestation |
| Can be exploited via re-entrancy, flash loans | Attack surface is hardware (side-channel), not logic |

### Why XRPL?

- **RLUSD** — regulated stablecoin, institutional trust
- **3-4 second finality** — fast enough for trading
- **Native multisig** (SignerListSet) — no smart contract needed for 2-of-3 custody
- **Low fees** — < $0.001 per transaction
- **No MEV** — XRPL has no mempool front-running

---

## What we built

### Working PoC (live at api-perp.ph18.io)

| Component | Technology | Status |
|-----------|-----------|--------|
| **Margin engine** | C/C++ inside SGX enclave | ✅ Live |
| **Order book** | Rust CLOB with price-time priority | ✅ Live |
| **Price feed** | Binance XRP/USDT, 5-second updates | ✅ Live |
| **Authentication** | XRPL secp256k1 signature verification | ✅ Live |
| **XRPL deposit monitor** | Watches escrow for incoming payments | ✅ Live |
| **Withdrawal signing** | Enclave margin check + ECDSA signature | ✅ Live |
| **WebSocket feed** | Real-time trades, orderbook, ticker, liquidations | ✅ Live |
| **DCAP attestation** | Intel SGX Quote v3 on Azure DCsv3 | ✅ Verified |
| **Multi-operator P2P** | libp2p gossipsub, sequencer election | ✅ Implemented |
| **State commitment** | TEE-signed Merkle root on Sepolia (Ethereum) | ✅ Implemented |

### Unique security features

1. **Withdrawal safety:** Enclave checks margin before signing. Even if the operator
   is compromised, the enclave refuses to sign withdrawals that would leave positions
   undercollateralized.

2. **Multi-operator custody:** XRPL native multisig (SignerListSet 2-of-3). Three
   independent operators on separate servers. No single point of failure.

3. **Verifiable computation:** DCAP remote attestation proves the enclave runs
   genuine, unmodified code. Anyone can verify by requesting an attestation quote.

4. **Drift attack prevention:** Compared to Solidity DEXes (Drift lost $280M),
   TEE approach eliminates flash loan attacks, re-entrancy, and governance manipulation.
   See research doc 08 for full analysis.

---

## Technical Architecture

### Single operator (MVP — live now)

```
nginx :443 → Orchestrator :3000 → SGX Enclave :9088
                  │
                  ├── Binance price feed (5s)
                  ├── XRPL deposit monitor (1s)
                  ├── Liquidation scanner (10s)
                  ├── Funding rate (8h)
                  └── WebSocket broadcast
```

### Multi-operator (production)

```
Operator A ──┐
Operator B ──┤ P2P gossipsub + XRPL SignerListSet 2-of-3
Operator C ──┘
```

Each operator runs identical enclave code (verified via DCAP attestation).
Sequencer election via heartbeat + priority-based failover.

---

## Market: XRP-RLUSD-PERP

| Parameter | Value |
|-----------|-------|
| Settlement | RLUSD |
| Collateral | RLUSD (100% LTV) + XRP (90% LTV) |
| Max leverage | 20x |
| Taker fee | 0.05% |
| Maintenance margin | 0.5% |
| Funding interval | 8 hours |
| Liquidation penalty | 0.5% |
| XRP staking | 5 tiers (10-50% fee discount) |

---

## Deliverables & Milestones

### Milestone 1: PoC (✅ Complete)
- SGX enclave with full margin engine
- Rust orchestrator with CLOB orderbook
- XRPL deposit/withdrawal on testnet
- DCAP remote attestation on Azure DCsv3
- 111 automated tests (unit, integration, e2e, invariant)
- Live API: https://api-perp.ph18.io

### Milestone 2: Multi-operator testnet (Week 1-4)
- 3-operator deployment (Azure DCsv3)
- XRPL mainnet multisig (SignerListSet 2-of-3)
- State commitment on Ethereum (Sepolia → mainnet)
- Frontend integration (perp.ph18.io)

### Milestone 3: Mainnet beta (Week 5-8)
- RLUSD mainnet settlement
- Public DCAP attestation verification
- SDK for third-party integration
- Security audit (enclave + orchestrator)

### Milestone 4: Production launch (Week 9-12)
- Vault system (liquidation, HLP, delta-0, delta-1)
- XRP staking with fee tiers
- Additional markets (ETH-RLUSD-PERP)
- Performance optimization

---

## Budget

| Item | Cost | Notes |
|------|------|-------|
| Azure DCsv3 (3 operators × 3 months) | $X | SGX-enabled VMs |
| Development (2 engineers × 3 months) | $X | Rust + C/C++ + XRPL |
| Security audit | $X | Enclave + orchestrator |
| Infrastructure (domains, monitoring) | $X | |
| **Total** | **$X** | |

*Budget to be finalized based on grant form requirements.*

---

## Team

- **Lead architect / developer** — Full-stack: SGX enclave (C/C++), Rust orchestrator, XRPL integration, cryptography
- **PM / co-developer** — SGX infrastructure, deployment, Python tooling
- **SDK developer** — Frontend SDK, API integration, Nix/Poetry packaging

---

## Open Source

- **Code:** BSL 1.1 (Business Source License) — converts to Apache 2.0 after 4 years
- **Research:** CC BY-NC-ND 4.0
- **Repositories:**
  - `xrpl-perp-dex` — Orchestrator (Rust), research docs, API guide
  - `xrpl-perp-dex-enclave` — SGX enclave (C/C++), perp engine

---

## Research Documents

| # | Title | Topic |
|---|-------|-------|
| 01 | Feasibility Analysis | Can we build a perp DEX on XRPL? |
| 02 | TEE Perp Mechanics | Vaults, funding, collateral design |
| 03 | Production Architecture | nginx → Orchestrator → Enclave |
| 04 | Multi-Operator Architecture | XRPL multisig, sequencer election |
| 05 | TEE Rationale & API Design | Why TEE, not smart contracts |
| 06 | Latency Analysis | XRPL 3-4s finality impact |
| 07 | Failure Modes & Recovery | 19 scenarios, tested on real infra |
| 08 | TEE vs Smart Contract Security | Drift $280M hack analysis |

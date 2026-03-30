# Perp DEX on XRPL: Feasibility Analysis

**Date:** 2026-03-29
**Status:** Research
**Research deadline:** 2026-04-07
**PoC deadline:** 2026-04-15

---

## Summary

Building a perp DEX **directly on XRPL mainnet is impossible** due to the absence of smart contracts. However, the XRPL ecosystem offers **three viable paths** to implement a perp DEX using RLUSD.

---

## 1. XRPL Capabilities Analysis

### What XRPL mainnet offers
| Capability | Status |
|---|---|
| Built-in CLOB DEX (spot) | Live (since launch) |
| AMM (XLS-30) | Live (since 2024) |
| RLUSD | Live, market cap >$1.2B |
| Smart contracts | **NO** |
| Hooks | **NO** (Xahau sidechain only) |
| Derivatives | **NO** |

### Key XRPL mainnet limitations for a perp DEX
1. **No programmability** — cannot implement margin engine, liquidation, funding rate
2. **Spot trading only** — native DEX does not support synthetic assets
3. **No oracles** — no price feed mechanism
4. **3-5 sec finality** — slow for derivatives

### Adjacent solutions in the ecosystem

| Solution | Status | Smart contracts | Perp capability |
|---|---|---|---|
| XRPL Mainnet | Production | No | Impossible |
| Xahau (Hooks) | Production (Oct 2023) | Limited (WASM, 64KB stack, not Turing-complete) | Extremely difficult |
| XRPL EVM Sidechain | Production (Jun 2025) | Full (Solidity/EVM) | **Possible** |
| XLS-101d (Native WASM) | Early draft | Planned | No timeline |

---

## 2. Three viable architectures

### Variant A: GMX-style on XRPL EVM Sidechain

**Concept:** Oracle-based perp DEX entirely on EVM sidechain, RLUSD as collateral.

```
User --> XRPL EVM Sidechain
          |-- Vault (RLUSD collateral)
          |-- Position Manager
          |-- Oracle (Chainlink/Pyth)
          |-- Liquidation Keepers
          |-- Funding Rate Engine
```

**Pros:**
- Proven architecture (GMX on Arbitrum)
- Full EVM compatibility — can fork GMX
- RLUSD available via Axelar bridge
- Vertex already building derivatives on this chain
- XRP as gas token

**Cons:**
- PoA consensus (centralization)
- Dependency on Axelar bridge for RLUSD
- Thin liquidity at launch
- Competition with Vertex

**PoC complexity:** Medium (2-3 weeks to fork GMX)

---

### Variant B: TEE Coprocessor + XRPL Settlement

**Concept:** Order matching and computation in SGX enclave, settlement via XRPL mainnet.

```
Users --> [Encrypted Orders] --> SGX Enclave (TEE)
                                   |-- Order matching
                                   |-- Margin calculation
                                   |-- Funding rate calc
                                   |-- Attestation
                                   v
                              [Matched Trades + Attestation]
                                   v
                              XRPL Mainnet Settlement
                                   |-- Escrow/Payment channels
                                   |-- RLUSD transfers
                                   |-- Position tracking (off-chain DB + attestation)
```

**Pros:**
- Uses XRPL mainnet directly (grant value)
- Anti-MEV, anti-frontrunning by design
- Reference: SGX_project already exists (prediction market MVP)
- Unique architecture — no competitors on XRPL
- RLUSD settlement on L1

**Cons:**
- Position state stored off-chain (in TEE + backup)
- Dependency on Intel SGX hardware
- More complex to implement
- Limited decentralization (TEE operator = trusted party)

**PoC complexity:** High (3-4 weeks), BUT reference exists in SGX_project

---

### Variant C: Hybrid — TEE Matching + EVM Sidechain Settlement

**Concept:** Best of both worlds: TEE for order matching, EVM sidechain for settlement.

```
Users --> [Encrypted Orders] --> SGX Enclave (TEE)
                                   |-- Order matching
                                   |-- Price computation
                                   |-- Attestation
                                   v
                              XRPL EVM Sidechain
                                   |-- Verify attestation
                                   |-- Vault (RLUSD)
                                   |-- Position state
                                   |-- Liquidation
                                   |-- Funding rate
```

**Pros:**
- TEE provides anti-MEV
- EVM provides on-chain state and settlement
- RLUSD collateral in smart contract
- Most "grant-worthy" — uses multiple ecosystem components

**Cons:**
- Maximum implementation complexity
- Two systems to maintain

**PoC complexity:** Very high

---

## 3. What is RLUSD and how to use it

- **Issuer:** Ripple (through a trust company, approved by NYDFS and DFSA)
- **Backing:** 1:1 USD cash + US Treasuries
- **Chains:** XRPL mainnet + Ethereum
- **Market cap:** >$1.2B
- **XRPL issuer account:** `rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De`
- **Availability on EVM sidechain:** via Axelar bridge

**RLUSD role in perp DEX:**
1. **Collateral** — margin and position backing
2. **Settlement** — P&L settlement
3. **Insurance fund** — insurance pool
4. **LP token denomination** — for oracle-based model

---

## 4. Competitors and precedents

| Project | Chain | Type | Status |
|---|---|---|---|
| Vertex | XRPL EVM Sidechain | Derivatives | In development |
| Hyperliquid | Custom L1 | Perp CLOB | Production |
| dYdX v4 | Cosmos L1 | Perp CLOB | Production |
| GMX | Arbitrum | Perp Oracle-based | Production |
| XRPL Derivatives Sidechain | Proposal only | Options/Perps | Concept |

---

## 5. Recommendation

### For PoC by April 15: **Variant B (TEE + XRPL Settlement)**

**Rationale:**
1. **Uniqueness** — no analogues on XRPL, differentiation from Vertex
2. **Grant appeal** — uses XRPL mainnet + RLUSD directly
3. **Reference exists** — SGX_project already demonstrates TEE on XRPL
4. **Anti-MEV** — strong narrative for grant application
5. **Scalability** — can evolve into Variant C later

**PoC scope:**
- SGX enclave: simple order matching (limit orders)
- Attestation verification
- RLUSD escrow on XRPL for collateral
- Simple margin check (isolated margin, 1 market: XRP/RLUSD perp)
- Funding rate: static (simplified)

### Fallback: **Variant A (GMX fork on EVM Sidechain)**
If the TEE approach doesn't fit the timeline — fork GMX on XRPL EVM Sidechain with RLUSD as collateral. Technically simpler but less unique.

---

## 6. Open questions for further research

1. [ ] RLUSD liquidity on XRPL EVM Sidechain — sufficient for a DEX?
2. [ ] Are there oracle providers (Chainlink/Pyth) on XRPL EVM Sidechain?
3. [ ] Ripple/XRPL Foundation grant requirements — specific criteria?
4. [ ] SGX_project — what exactly is implemented, what can be reused?
5. [ ] Legal restrictions on derivatives in relevant jurisdictions
6. [ ] XRPL payment channels — can they be used for fast settlement?

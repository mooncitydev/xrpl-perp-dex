# How we differ from Arch Network

**Audience:** technical team, investor, and anyone asked "so how is this different from Arch?".
**Status:** competitive and architectural comparison. Bilingual: Russian counterpart at `comparison-arch-network-ru.md`.
**Context:** Arch Network (`book.arch.network`) is a Bitcoin-native execution platform that shipped to testnet before we did, and it is now the default point of comparison any time we describe a BTC-oriented version of our own product. This document exists to answer the "how is this different from Arch?" question precisely and honestly — not dismissively, because Arch is real and has real engineering behind it, and not defensively, because the two projects are actually doing different things.

The short version: **Arch is a platform, we are a product**. They sell infrastructure to developers who want to build Bitcoin-native DeFi applications; we sell a single hardware-attested perp DEX directly to traders. The overlap is narrow, the trust models are different, and the competitor to watch on Arch is not Arch itself but **VoltFi**, their ecosystem's derivatives project. The rest of this document unpacks that.

---

## 1. Executive summary

- **Arch Network is a general-purpose execution platform for Bitcoin.** It ships an eBPF-based VM (ArchVM), a dPoS validator set staking a native token, FROST+ROAST threshold signing for settlement to Bitcoin, and a Rust SDK for writing programs. Their ecosystem already includes a DEX (Saturn), a lending protocol (Autara), a derivatives project (**VoltFi**), and others — all as tenants on their platform.
- **We are a single-purpose hardware-attested perp DEX.** Matching, risk, and custody live inside SGX enclaves whose binary is reproducibly built and whose `MRENCLAVE` is publicly attested. Custody is FROST 2-of-3 across three named operators. There is no token, no VM, no tenants — the whole system is one auditable product.
- **The trust models are different, neither is strictly better.** Arch's security rests on a dPoS validator set with BFT guarantees (f < n/3) and economic incentives via stake slashing — a classic crypto-economic construction. Ours rests on SGX hardware attestation + FROST threshold custody + a small, named, hardware-key-gated operator set. These are different risk profiles that appeal to different users and counterparties.
- **We do not compete with Arch; we overlap with VoltFi.** Arch is infrastructure. The project on Arch that targets the same end user as us is VoltFi. That is the real competitive comparison, and it's one we are architecturally well-positioned for: smaller TCB, hardware-attested execution, no token risk, no platform dependency.
- **Arch's existence is a positive signal for our thesis.** An independent team arrived at the same primitive (FROST threshold Schnorr over Taproot for non-custodial Bitcoin settlement) that our signing stack has already shipped. The choice of FROST as the base mechanism is now market-validated.
- **Deploying our perp DEX *on* Arch is technically possible but strategically wrong.** It would trade our strongest differentiator (hardware-attested execution, minimal TCB) for a dependency we do not need (we already have FROST 2-of-3 custody of our own).

---

## 2. What Arch Network actually is

It is important to describe Arch accurately before comparing to it, because a lot of the existing "Bitcoin L2 vs. X" discourse confuses categories. Based on their official book, whitepaper, and third-party technical reviews, Arch is composed of:

- **ArchVM** — a virtual machine forked from the eBPF runtime that Solana uses, extended with custom syscalls that read and write Bitcoin UTXO state and can post transactions directly to Bitcoin. Programs are written in Rust and compiled to eBPF bytecode, then deployed to the platform. This is a general-purpose execution environment, not a single-application codebase.
- **A decentralized validator network under delegated proof-of-stake.** Validators stake the Arch native token, are selected into leader slots by stake weight, execute programs, and reach consensus. The validator set is currently permissioned — a whitelist is enforced during the DKG ceremony — with a stated roadmap toward permissionless participation.
- **FROST + ROAST threshold Schnorr signing as the settlement primitive.** FROST produces aggregated BIP340 Schnorr signatures over a t-of-n threshold of the validator set; ROAST extends FROST with asynchronous operation so that validators can join and exit between epochs without halting consensus. The threshold is configurable but their messaging cites "51%+" as the majority-honest assumption. The output on-chain is a single BIP340 Schnorr signature, indistinguishable from a key-path Taproot spend.
- **Direct Bitcoin settlement via Taproot.** Users interact with Arch programs through Taproot addresses; the validator set aggregates signatures and posts the resulting transactions to Bitcoin's mainnet. There is no bridge, no sidechain, no wrapped BTC. This is genuinely Bitcoin-native from a settlement perspective.
- **Sub-second pre-confirmations.** Before Bitcoin finalizes a transaction (ten minutes or more), Arch offers a softer "pre-confirmation" guarantee from the validator set — the validators have signed off on the result and will submit it once conditions allow.
- **A native token** used for staking, validator selection, and (presumably) gas metering of program execution. The specific token economics are not the subject of this document but they matter: Arch is economically a classic tokenized L1-on-BTC.
- **An ecosystem already in flight on testnet.** Named projects include Saturn (DEX), Autara (lending), **VoltFi (derivatives and perps)**, Ordeez (BNPL), HoneyB (RWAs), and an indexing layer called Titan for mempool tracking and Runes support.

Note what Arch **does not** use: trusted execution environments. There is no SGX, no TDX, no enclave measurement, no hardware attestation. Their entire security model is cryptographic (threshold Schnorr) plus economic (staking + slashing) plus consensus-theoretic (Byzantine fault tolerance with f < n/3). This is a legitimate and well-understood construction, and it is different from ours on a fundamental axis. Neither construction is a substitute for the other.

---

## 3. Side-by-side architecture

The following table is the clearest way to see where the two projects actually differ, without editorial spin in either direction.

| Axis | Arch Network | Our project |
|---|---|---|
| **Class of system** | General-purpose execution platform | Single-purpose perp DEX |
| **Deploy unit** | Rust → eBPF bytecode, deployed by any developer | Our own C++ code inside SGX enclave, deployed by us |
| **Trust root** | dPoS + FROST/ROAST + economic stake | SGX hardware attestation + FROST 2-of-3 + hardware-key operator ceremony |
| **Operator/validator set** | n validators, BFT under f < n/3, permissioned today, permissionless in roadmap | 3 named operators, permissioned by design |
| **Consensus** | Yes — classic BFT via ROAST over validator set | None. Matching runs in a single enclave; FROST signs only settlement transactions, not every state transition |
| **Replicated execution** | Yes (all validators execute and compare) | No (one enclave executes; attestation + FROST settlement is what holds it accountable) |
| **State storage** | Off-chain in validators, periodically anchored to Bitcoin | SGX-sealed inside the enclave, not replicated |
| **Programmability** | Open — any developer can deploy | Closed — only our own code, and that is a property, not a limitation |
| **Native token** | Yes — used for staking, gas, validator selection | None |
| **Matching latency** | Sub-second pre-confirmation, final on Bitcoin confirmation | Microseconds inside the enclave, settlement to Bitcoin on confirmation |
| **Custody mechanism for BTC** | FROST threshold Schnorr aggregated across validator set | FROST 2-of-3 Schnorr aggregated across three SGX enclaves |
| **TEE / hardware attestation** | Not used at any layer | Central element of the design |
| **Auditable binary with cryptographic proof of what's running** | No — consensus does not provide this | Yes — `MRENCLAVE` is publicly attested via DCAP |
| **Category of competitor for traders** | The DEX is Arch, but the product competing for the same trader is **VoltFi** | We compete directly with VoltFi and with centralized BTC-perp venues (BitMEX, Deribit) |
| **Category of competitor for developers** | Arch competes with Solana, Ethereum, other smart-contract platforms | We do not compete for developers — we do not host developers |
| **Platform risk for us if we used it** | We would be tenants, exposed to Arch VM bugs, validator liveness, Arch token economics, Arch governance | Zero — we own and operate the full stack |

---

## 4. Trust-model comparison — the core difference

This is the most important section for an investor conversation, because it is where the two approaches fundamentally diverge.

### 4.1 What Arch asks a user to trust

- That a majority of the validator set will remain honest. With an f < n/3 BFT assumption and n validators, a user needs n/3 or more of the stake-weighted validator set to remain honest for liveness, and n/3 or more to prevent malicious consensus. Economic stake provides the incentive: validators that misbehave lose their stake, so a rational attacker has to put more capital at risk than they can extract.
- That ArchVM correctly executes Rust programs compiled to eBPF, deterministically, across all validators. Any consensus divergence caused by VM non-determinism is a protocol-level failure.
- That the specific application on Arch (e.g. VoltFi for perps) has been implemented correctly in Rust. Application bugs are the user's risk, not Arch's.
- That the Arch team does not rug the network via validator whitelist changes or governance attacks while the network is still permissioned.
- That Bitcoin's own finality holds for anchored settlement, but this risk is the same for anyone settling to Bitcoin.

This is a **crypto-economic trust model with large anonymity set** — the user does not need to know any specific validator, only that the distribution of stake is wide and that rational incentives will keep most of it honest. It is the same construction Ethereum, Cosmos, and Solana use, applied to Bitcoin settlement.

### 4.2 What we ask a user to trust

- That Intel SGX is not catastrophically broken. "Catastrophically broken" means the master key leaks, or a remote side-channel attack is discovered that does not require physical possession of the machine. Neither has happened in the decade SGX has existed on server Xeon, and our Part 1 discussion of side-channels in `sgx-enclave-capabilities-and-limits.md` explains why published attacks require a lab or a fully-compromised host, not a remote exploit.
- That the `MRENCLAVE` we publish is in fact the measurement of the enclave binary a user interacts with. This is cryptographically verifiable via DCAP attestation. It requires no trust — it is a proof.
- That two of our three named operators do not collude to sign a fraudulent withdrawal. FROST 2-of-3 means any single operator compromise leaves funds safe; two operators colluding can sign, but they are named persons under hardware-key ceremony with audit trail. This is a small-set, identity-based trust assumption, not an anonymous one.
- That the operator deployment ceremony in `deployment-procedure.md` is followed honestly by at least two operators. The procedure is designed such that unilateral deviation is visible to the other operators.
- That our enclave code is free of bugs, or at least that bugs have been found and fixed through audit. This risk is identical for any software system including Arch/VoltFi — it is not a structural disadvantage.

This is a **hardware-rooted trust model with a small identity set** — the user knows who the operators are, can verify what code they are running, and relies on hardware guarantees from a specific CPU vendor plus threshold cryptography across named parties.

### 4.3 Which model is "better"?

Neither is strictly better. They optimize for different things:

- **Arch's model is better for users who prefer large anonymity sets and crypto-economic decentralization**. For the ideologically crypto-native user who considers "three named operators" a centralization red flag regardless of hardware attestation, Arch is the more appealing option.
- **Our model is better for users and counterparties who want auditable execution and minimal TCB**. For an institutional user, a regulator, a compliance officer, or a trader who wants to cryptographically verify that matching and risk logic is running the code they think it is, we are the more appealing option. Arch simply does not offer that guarantee because consensus does not provide it — "validators agreed" is not the same as "here is a hash of the exact binary that produced this result".
- **Arch's model has a larger long-term decentralization ceiling**. If Arch's permissionless roadmap succeeds and they reach a validator set comparable to Solana or Cosmos, their distribution of trust is genuinely larger than ours can ever be with three operators.
- **Our model has a much smaller attack surface today**. Our TCB is approximately 5,000 lines of audited C++ plus `libsecp256k1` plus the SGX SDK. Arch's TCB is ArchVM (a fork of eBPF with custom syscalls) plus the full validator node software plus the specific application running on it (e.g. VoltFi's Rust code). By line count and by number of implementation layers, our TCB is roughly an order of magnitude smaller.

These are different products serving different segments of the same market.

---

## 5. Where Arch is objectively ahead of us

Stated honestly, because this document exists to withstand scrutiny:

- **General-purpose programmability.** They run a full VM; anyone can deploy an application. We do not, and will not, unless we fundamentally change what we are.
- **Permissionless roadmap.** They have a credible path to a genuinely decentralized validator set. We do not — three enclaves is three enclaves, and there is no cryptoeconomic reason for a fourth to exist.
- **Ecosystem momentum on testnet.** Multiple named teams are already building on Arch (Saturn, Autara, VoltFi, Ordeez, HoneyB). We have exactly one product: ours.
- **No hardware-vendor dependency.** Arch does not depend on Intel or any other silicon vendor. If Intel ships a catastrophic SGX vulnerability or decides to discontinue SGX sooner than currently announced, we have a platform problem; Arch does not.
- **Token-driven growth flywheel.** They have a native token, which (for better or worse) gives them a mechanism for incentivizing validator participation, bootstrapping liquidity, and rewarding early ecosystem builders. We do not, by design, and this is a conversation to have with the investor separately.
- **Press and narrative position.** "Bitcoin programmability" is a well-formed investor narrative that Arch has already claimed. We operate in a narrower niche ("hardware-attested BTC perp DEX") that is less familiar and requires more explanation.

None of these items is a technical deficiency in our architecture. They are structural consequences of the fact that we built a single product and they built a platform, and structural consequences of the different trust models.

---

## 6. Where we are objectively ahead of Arch (specifically compared to VoltFi on Arch)

Also stated honestly:

- **Smaller TCB.** Our trusted code is our enclave binary; theirs is ArchVM plus the full validator node software plus VoltFi's Rust program. Fewer moving parts means fewer places for a vulnerability to hide and fewer auditors required to cover the system.
- **Cryptographically verifiable binary.** A user of our perp DEX can verify `MRENCLAVE` via DCAP attestation and confirm that the exchange is running exactly the version we published. A user of VoltFi on Arch cannot obtain an equivalent cryptographic proof — the best they can do is "the consensus agrees on the result", which is a statement about agreement, not about what code produced it.
- **No token risk.** No token unlock schedule, no token price collapse risk, no governance capture risk, no regulatory ambiguity about whether our token is a security. Fees are denominated in the settlement asset (RLUSD on XRPL today, BTC on Bitcoin tomorrow).
- **Matching latency lower by orders of magnitude.** Our matching engine runs at memory speed inside the enclave — microseconds per order. Arch's sub-second pre-confirmation is the validator kworum latency, which is two to three orders of magnitude slower. For maker-taker dynamics, market-making strategies, and high-frequency traders, this is meaningful and measurable.
- **Known operators under a documented ceremony.** For an institutional counterparty that requires knowing who operates the system and how releases are signed, our model provides that. An anonymous validator set does not.
- **Zero platform dependency.** We own and operate the entire stack. There is no Arch team upgrade that can brick us, no Arch governance vote that can change our fees, no Arch validator liveness problem that can halt our matching.
- **Immediate BTC-readiness of the signing layer.** Our enclave already ships the exact cryptographic primitives BTC needs (BIP340 Schnorr, MuSig2, FROST 2-of-3), independently of Arch. We did not wait for a platform to become available; we built the primitives into our own enclave, and the BTC feasibility argument (`btc-perp-dex-feasibility.md`) stands on its own without reference to Arch.

This is the genuine competitive ground against VoltFi. It is also the ground on which our pitch to traders and institutional counterparties is strongest.

---

## 7. Could we deploy our perp DEX on Arch instead of operating our own infrastructure?

This question will come up because it looks attractive on the surface — "why operate three enclaves when Arch already provides FROST custody and a deployment platform?" The honest answer has three parts.

**First, it is technically possible.** Our margin engine, liquidation logic, CLOB matching, and position state machine are mostly portable C++. Rewriting them as a Rust program targeting ArchVM is a multi-month engineering task but not a research project. We could, in principle, become a tenant on Arch alongside VoltFi.

**Second, it would cost us every technical differentiator we currently have.** We would lose:
- Hardware-attested execution (ArchVM is not SGX; there is no `MRENCLAVE` on a deployed Arch program).
- Microsecond matching latency (we would be bound to Arch validator pre-confirmation times).
- Minimal TCB (we would inherit ArchVM + validator node software + our own Rust code's TCB).
- Zero-token-dependency fee model (we would pay gas in the Arch native token, with whatever economic risk that carries).
- Independence from a platform-governance process we do not control.

In exchange, we would gain:
- Not having to run three enclaves on three machines (which we are set up to do anyway).
- Access to Arch's composability with Saturn, Autara, and other Arch-native applications (which is valuable only if we want to be an Arch-ecosystem citizen, and which adds a coupling risk).
- The permissionless-roadmap story that Arch sells to crypto-native users (which we do not currently try to sell, because our value proposition is different).

**Third, the trade is strategically wrong for us specifically.** Arch's platform value proposition to its tenants is "we provide FROST custody and a secure execution environment so you don't have to build them yourself". But *we already built them*. FROST 2-of-3, DKG, MuSig2, Schnorr, Taproot signing — all of that ships in our enclave today. Paying the cost of tenancy to receive a service we already have is a bad trade. We are exactly the kind of team for whom Arch's platform offer is least valuable, precisely because our own signing and custody infrastructure is already complete.

The correct framing for any conversation about this: **Arch is a good choice for a team that wants to build a BTC application and does not want to operate custody infrastructure. We are not that team. We have the custody infrastructure. Arch's offer is addressed to a different customer than us.**

---

## 8. Who the actual competitor is

Arch is infrastructure; VoltFi is the derivatives application on Arch. If a trader decides they want to open a BTC perp position in a non-custodial fashion tomorrow, their realistic options are:

1. A centralized exchange (BitMEX, Deribit, Binance, OKX, Bybit). Non-custodial: no.
2. A wrapped-BTC DeFi perp on Ethereum/Arbitrum/Solana (GMX, Hyperliquid, Drift). Non-custodial: yes but with bridge and wrapping risk.
3. **VoltFi on Arch.** Non-custodial: yes, via Arch's FROST+ROAST validator set and direct Bitcoin settlement. Trust: crypto-economic, large anonymity set.
4. **Us, when our BTC version ships.** Non-custodial: yes, via FROST 2-of-3 across three SGX enclaves and direct Bitcoin settlement. Trust: hardware-attested, small identity set.

Options 3 and 4 are both "decentralized, L1-native, non-custodial BTC perp DEX" — the same category. They differ on trust model, latency, and execution guarantees along the lines this document has laid out. A trader will rationally choose between them based on which trade-off matches their own preferences:

- Crypto-purist trader who values permissionlessness and does not accept any hardware-vendor trust → VoltFi.
- Institutional counterparty, high-frequency trader, or user who wants cryptographic proof of execution integrity → us.

Both are legitimate preferences. Both correspond to real market segments. The market on L1 BTC is large enough for both products to coexist and grow without directly cannibalizing each other, and neither's success precludes the other's.

This is an important positioning point for the investor conversation. **The right comparison is us vs. VoltFi, not us vs. Arch**, and it is a comparison we can make confidently on the technical axes that matter.

---

## 9. Why Arch's existence is a positive signal for our thesis

The reflex reading of "a well-funded team shipped a Bitcoin execution platform before us" is competitive threat. The correct reading is market validation. Specifically:

- **FROST over Taproot is now market-validated as the right custody primitive for non-custodial BTC applications.** Two independent teams (ours, and Arch) arrived at the same technical conclusion. Our own signing stack already ships this. The fact that Arch chose it for their platform consensus layer is confirmation that the primitive is serious and that builders trust it.
- **The category "decentralized, L1-native, non-custodial BTC perp DEX" is now a recognized category.** Before Arch + VoltFi existed, this was an argument we had to make from scratch to any investor who had never heard of it. Now it is an ecosystem narrative with named projects. Our job becomes differentiation within the category, not inventing the category.
- **The market has demonstrated willingness to fund the category.** Arch is funded, their ecosystem is funded, VoltFi is funded. This is direct evidence that the "BTC programmability for derivatives" thesis has capital backing and user interest behind it. Our fundraising conversation becomes easier, not harder, because we can point to a reference deal structure.
- **We have a different and defensible wedge.** Our TCB is smaller, our execution is hardware-attested, our matching is faster, our trust model is more legible to institutional counterparties. These are real differentiators in a category that Arch has already legitimized.

Seen this way, Arch shipping first is strictly good for us: they created the market, and we sell the premium product inside it.

---

## 10. Recommendation and positioning

For internal strategy:

- **Do not treat Arch as the competitor to reference.** Treat VoltFi as the competitor to reference. When a prospective user or investor asks about "the Arch comparison", gently correct the framing to "the VoltFi comparison" and then win on the specifics in §4 and §6.
- **Do not deploy our perp DEX on Arch.** The trade is strategically wrong for our specific team and architecture, for the reasons in §7.
- **Do keep the codebase chain-agnostic** via the `ChainAdapter` interface described in `btc-perp-dex-feasibility.md`. This leaves the BTC track open without any premature commitment.
- **Do consider limited interoperability later.** If at some point it becomes valuable to have our BTC version *also* accept deposits from users holding positions in Arch-native assets (Runes, Ordinals, etc.), that is an orchestrator-level integration — a reader for Arch state, a bridge-like adapter — that does not require becoming a tenant on Arch. This is a future option, not a near-term task.

For the investor conversation, the one-paragraph answer to "how is this different from Arch?":

> *Arch Network is a general-purpose execution platform for Bitcoin, built on a dPoS validator set with FROST threshold signing and a native token. Their ecosystem includes a derivatives project called VoltFi that competes for the same end user as us. We are not a platform; we are a single hardware-attested perp DEX. Our matching and risk engine runs inside SGX enclaves whose binary is publicly attested via MRENCLAVE, custody is FROST 2-of-3 across three named operators with documented hardware-key ceremony, and there is no token. Compared to VoltFi on Arch, our trusted computing base is roughly an order of magnitude smaller, our matching latency is two-to-three orders of magnitude lower, and we provide cryptographic proof of exactly what code is running — something no consensus-based system can provide. Arch shipping first is a positive signal for our thesis because it validates the category, and we sell the premium product inside the category they created.*

That paragraph is the shortest honest answer to the question. Everything else in this document is supporting evidence.

---

## Appendix A — Sources consulted

- [Arch Book — Introduction](https://docs.arch.network/book/introduction.html)
- [Arch Documentation — Overview](https://docs.arch.network/learn/overview)
- [Arch Book — Network Architecture](https://docs.arch.network/book/concepts/network-architecture.html)
- [Arch: Bitcoin's Execution Play — blocmates](https://www.blocmates.com/articles/arch-bitcoin-s-execution-play)
- [Arch Network Code Review — Token Metrics Research](https://research.tokenmetrics.com/p/arch-network)
- [Arch Documentation FAQ — GitBook](https://arch-network.gitbook.io/arch-documentation/developers/faq)
- [Arch Whitepaper — The Permissionless Financial Rails for a Bitcoin-denominated World](https://docs.arch.network/whitepaper.pdf)
- [What Is Arch Network? — MEXC Blog](https://blog.mexc.com/what-is-arch-network-reshape-bitcoins-native-defi/)
- [Bitcoin Programmability: The Complete Picture — Arch Network Blog](https://www.blog.arch.network/bitcoin-programmability-the-complete-picture/)

## Appendix B — Cross-references within our own documentation

- `btc-perp-dex-feasibility.md` — full BTC-portability argument for our architecture. This comparison document is the competitive layer; that one is the technical layer.
- `sgx-enclave-capabilities-and-limits.md` — the trust model we rest on, including the honest limits of SGX. Arch does not rest on this model at all; comparing trust assumptions requires understanding both.
- `deployment-procedure.md` — the operator ceremony that defines our identity-based trust set. This is the document a regulator or institutional counterparty will want to see.
- `xls-survey-for-perp-dex.md` — why we picked XRPL first rather than BTC first. The reasoning there (native programmability, fast finality, native stablecoin) predates Arch's emergence and still holds.
- `feedback_bilingual_docs.md` — bilingual policy. This document has a Russian counterpart.

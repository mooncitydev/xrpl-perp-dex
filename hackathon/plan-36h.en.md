# Hack the Block Paris — 36-Hour Plan

**Team:** Alex, Andrey, Tom
**Track:** Challenge 2 — Impact Finance
**Project:** Perpetual Futures DEX on XRPL with RLUSD settlement

---

## Positioning (what judges see)

**Public narrative:** the first perpetual futures exchange that settles
natively in RLUSD on XRPL mainnet. User funds are held in an XRPL
`SignerListSet` 2-of-3 multisig between independent operators. No
sidechain, no bridge, no custodial trust.

**What we DON'T reveal:** the secure computation backend (enclave
technology, hardware specifics, DCAP attestation internals). On stage,
it's a **working black box** — "our proprietary secure computation layer
ensures that margin checks and signing happen in a tamper-proof
environment; we'll publish the full architecture post-launch."

If judges ask "how does the signing work?":
> "Each operator runs a secure computation module that holds signing keys
> in isolated memory. The module checks margin before signing any
> withdrawal. Even if the operator's server is compromised, the signing
> module refuses to sign an undercollateralized withdrawal. We use
> industry-standard hardware security — details under NDA until mainnet."

---

## What we already have (DO NOT build during hackathon)

Everything below is **live and verified** as of April 10, 2026:

- Live API: `api-perp.ph18.io` (nginx, TLS, CORS)
- Secure computation module with margin engine, position tracking, ECDSA signing
- Rust orchestrator: CLOB orderbook, P2P gossipsub, sequencer election
- 2-of-3 multisig withdrawal via XRPL native SignerListSet — working, verified on testnet
- WebSocket with Fill/OrderUpdate/PositionChanged + channel subscriptions
- PostgreSQL trade replication across 3 operators
- Resting order persistence + failover recovery
- 16/16 E2E tests passing, 9/9 failure mode scenarios with 10 on-chain tx proofs
- Full grant application ready

**Strategy: we don't build the core at the hackathon. It's done. We build
the DEMO LAYER that makes judges go "wow, this is real and it works on
XRPL right now".**

---

## 36-Hour Timeline

### Hours 0-2: Setup & alignment (all 3)

- [ ] Connect to venue WiFi, test SSH to servers
- [ ] Verify `api-perp.ph18.io` responds from venue network
- [ ] Run smoke test: `curl markets`, `wscat wss://api-perp.ph18.io/ws`
- [ ] Align on task split (below) and commit to deliverables

### Hours 2-14: Build sprint (parallel tracks)

**Track A — Frontend trading UI (Tom, ~12h)**

Build a minimal but polished web UI at `perp.ph18.io`:
- [ ] Connect wallet (XRPL via GemWallet or Crossmark browser extension)
- [ ] Display live mark price + funding rate from REST API
- [ ] Show orderbook depth (bids/asks) from REST + WebSocket updates
- [ ] Submit limit/market orders via authenticated REST (sign with wallet)
- [ ] Show user's open orders + positions (polling /v1/orders, /v1/account/balance)
- [ ] Show real-time fills via WebSocket `user:rXXX` channel subscription
- [ ] "About" section: "settlement on XRPL, 2-of-3 operator multisig, RLUSD native"

**Stack suggestion:** React or Next.js, Tailwind CSS, lightweight. No
backend — pure API client. WebSocket for live data. API is CORS-enabled.

**Minimum viable for demo:** price display + submit order + see fills
live. The "it's actually on XRPL" moment is the wow-factor.

**Track B — Live trading demo setup (Andrey, ~4h)**

- [ ] Fund 2 test wallets on XRPL testnet
- [ ] Deposit funds to the escrow account for both wallets
- [ ] Place initial maker orders at realistic prices (spread around Binance mid)
- [ ] Set up a simple market-making bot (Python loop: quote bid/ask every 5s)
  - 50 lines using `tools/xrpl_auth.py` for signing
  - Creates liquidity so the demo looks alive, not an empty book
- [ ] Test full flow: deposit → maker quote → taker crosses → WS fill → withdraw multisig
- [ ] Record backup asciinema in case venue internet is flaky
- [ ] Prepare pre-funded wallets with saved seeds (offline backup)

**Track C — Pitch, materials, networking (Alex, ~6h)**

- [ ] Build a "how it works" landing page at `perp.ph18.io/about`:
  - Architecture diagram (User → API → Orchestrator → Secure Module → XRPL)
  - "2-of-3 operator multisig protects your funds"
  - "Operators run independent secure computation modules"
  - "All deposits and withdrawals are on XRPL — verify yourself"
  - Link to XRPL testnet explorer with escrow account
- [ ] Refine 5-minute pitch for judges:
  - Problem (no DeFi derivatives on XRPL) → Solution (off-chain matching,
    on-chain settlement) → Why XRPL (RLUSD, SignerListSet, no MEV) →
    Live demo → "funds are verifiable on XRPL right now" → Call to action
  - Practice twice with timer
- [ ] Prepare Q&A cheat sheet (top 10 expected questions + 1-sentence answers)
- [ ] 1-page project summary for networking

### Hours 14-18: Integration & polish (all 3)

- [ ] Connect frontend to live API — end-to-end from UI
- [ ] Fix CSS/UX issues
- [ ] Market-maker bot keeps book populated
- [ ] Run through full demo flow together:
  1. Open `perp.ph18.io` → show live prices
  2. Connect wallet
  3. Submit limit order → visible in orderbook
  4. Crossing order from second wallet → fill on WebSocket
  5. Show XRPL escrow on testnet explorer → "funds are here, on XRPL"
  6. Withdraw via multisig → show tx hash on explorer
- [ ] If time: record 2-minute video walkthrough as backup

### Hours 18-24: Sleep + buffer

Be realistic — 6 hours of sleep. Don't skip it.

### Hours 24-30: Final polish

- [ ] Fix bugs from overnight cooling
- [ ] Tom: responsive UI, error states, loading spinners
- [ ] Andrey: infra check — servers alive, tunnels up, orchestrator healthy
- [ ] Alex: finalize pitch deck, match demo flow order
- [ ] Practice full demo 2x (3-min and 5-min versions)
- [ ] Prepare offline backup: screenshots, recorded demo, pre-filled tx hashes

### Hours 30-34: Demo prep

- [ ] Submit project to hackathon platform
- [ ] Prep demo laptop: tabs open, wallets connected, terminal ready
- [ ] Last smoke test from venue
- [ ] Huddle: who presents what, who answers questions
  - Alex: opening + problem + solution (2 min)
  - Tom: live demo walkthrough (2 min)
  - Andrey: architecture overview + Q&A (1 min)

### Hours 34-36: Presentations & judging

- [ ] Present
- [ ] Network with judges
- [ ] Collect contacts (VCs, teams, XRPL community)

---

## What NOT to do during the hackathon

1. **Don't rewrite the backend** — it works, 16/16 E2E passing
2. **Don't touch the secure computation module** — rebuild cycle is long
3. **Don't add new trading features** (order types, markets) — scope creep
4. **Don't reveal the computation layer internals** — "proprietary secure module, details at mainnet"
5. **Don't try mainnet launch** — testnet is safe for live demo

## What to say if asked about the "secure module"

| Question | Answer |
|---|---|
| "What hardware do you use?" | "Industry-standard hardware security modules. Details under NDA until mainnet." |
| "Is this an MPC?" | "No, it's a single secure computation boundary per operator, not a multi-party protocol. The multisig is XRPL-native SignerListSet." |
| "Can the operator steal funds?" | "No. The signing module enforces margin checks in hardware. Even a compromised operator can't make the module sign an invalid withdrawal." |
| "How do users verify?" | "Deposits and withdrawals are on XRPL — anyone can check the escrow account. We'll add a public verification flow at mainnet." |
| "Is this audited?" | "52 findings in security audit, 50 fixed, 2 documented as by-design. Full audit report in the repo." |
| "Open source?" | "BSL 1.1 license — converts to Apache 2.0 in 4 years. Code is public on GitHub today." |

---

## Judging criteria (typical for Impact Finance)

- **Technical execution** (40%) — does it work? live demo?
- **Innovation** (25%) — novel for XRPL ecosystem?
- **Impact potential** (20%) — who benefits?
- **Presentation quality** (15%) — clear, confident, within time

Our pitch angle: **"This is not a prototype. This is a working product
with 12 verified transactions on XRPL testnet, 3-operator multisig
custody, and an API you can hit right now."**

---

## Emergency kit

| Problem | Fix |
|---|---|
| Servers down | Restart from Hetzner (scripts saved) |
| Tunnels dropped | Re-create SSH tunnels |
| Testnet faucet down | Pre-funded wallets (save seeds) |
| Venue WiFi blocks SSH | Phone hotspot |
| Live demo fails on stage | Recorded backup video |

---

## Key numbers for the pitch

- **$280M** — Drift Protocol loss from social engineering on human multisig (April 2026)
- **2-of-3** — XRPL native SignerListSet multisig between independent operators
- **16.5 sec** — sequencer failover time (live tested on 3-node cluster)
- **3 sec** — network partition reconvergence (live tested)
- **12** — verified multisig transactions on XRPL testnet
- **16/16** — E2E test pass rate
- **52** — security audit findings (50 fixed, 2 by-design)
- **$150K** — grant application ready for XRPL Grants Spring 2026

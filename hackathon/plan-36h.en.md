# Hack the Block Paris — 36-Hour Plan

**Team:** Alex, Andrey, Tom
**Track:** Challenge 2 — Impact Finance
**Project:** Perp DEX on XRPL via Intel SGX (TEE)

---

## What we already have (DO NOT build during hackathon)

Everything below is **live and verified** as of April 10, 2026:

- Live API: `api-perp.ph18.io` (nginx, TLS, CORS)
- SGX margin engine (C/C++ enclave) with DCAP attestation on 3 Azure DCsv3 nodes
- Rust orchestrator: CLOB orderbook, P2P gossipsub, sequencer election (split-brain tested)
- 2-of-3 multisig withdrawal via XRPL native SignerListSet — **working in Rust**, verified on testnet with real ECDSA signatures from SGX enclaves
- WebSocket with Fill/OrderUpdate/PositionChanged + channel subscriptions
- PostgreSQL trade replication across 3 operators (passive B3.1)
- Resting order persistence + failover recovery (C5.1)
- 16/16 E2E tests passing, 9/9 failure mode scenarios with 10 on-chain tx proofs
- Full grant application + proof-of-traction pack

**Strategy: we don't build the core DEX at the hackathon. It's done. We build the DEMO LAYER and INTEGRATIONS that make judges go "wow, this is real".**

---

## 36-Hour Timeline

### Hours 0-2: Setup & alignment (all 3)

- [ ] Connect to venue WiFi, test SSH to Hetzner + Azure VMs
- [ ] Verify `api-perp.ph18.io` responds from venue network
- [ ] Run smoke test: `curl markets`, `wscat wss://api-perp.ph18.io/ws`
- [ ] Verify DCAP attestation on Azure node-2 still returns 4734-byte quote
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
- [ ] One-click "Verify enclave" button that calls `/v1/attestation/quote` and shows MRENCLAVE + quote size

**Stack suggestion:** React or Next.js, Tailwind CSS, lightweight. No backend needed — pure API client. WebSocket for live data. The API is CORS-enabled already.

**Minimum viable for demo:** price display + submit order + see fills live. The "verify enclave" button is the wow-factor.

**Track B — Live trading demo setup (Andrey, ~4h)**

- [ ] Fund 2 test wallets on XRPL testnet (or mainnet if ready)
- [ ] Deposit RLUSD (or XRP) to the escrow account for both wallets
- [ ] Place initial maker orders at realistic prices (spread around Binance mid) so the book isn't empty
- [ ] Set up a simple market-making bot (Python loop: quote bid/ask around Binance price every 5s)
  - 50 lines of Python using `tools/xrpl_auth.py` for signing
  - Creates liquidity so the demo looks alive, not an empty book
- [ ] Test full flow: deposit → maker quote → taker crosses → WebSocket shows fill → withdraw via multisig
- [ ] Record backup asciinema in case venue internet is flaky

**Track C — Attestation verifier page + pitch refinement (Alex, ~6h)**

- [ ] Build a standalone page: `verify.ph18.io`
  - Input: paste DCAP quote hex (or click "fetch from live node")
  - Output: parsed quote fields (MRENCLAVE, MRSIGNER, CPUSVN, PCK cert chain)
  - Compare MRENCLAVE against published `enclave.signed.so` hash
  - Show "✅ This enclave is running the published code" or "❌ Mismatch"
  - Can be a static HTML + JS page, no backend, uses Intel's open-source quote parser
- [ ] Refine 5-minute pitch for judges:
  - Problem → Solution → Why XRPL → Live demo → Attestation proof → Call to action
  - Practice twice with timer
- [ ] Prepare Q&A cheat sheet (top 10 expected questions + 1-sentence answers)
- [ ] Print/prepare 1-page project summary handout for networking

### Hours 14-18: Integration & polish (all 3)

- [ ] Connect frontend to live API — end-to-end test from UI
- [ ] Fix any CSS/UX issues Tom found
- [ ] Andrey makes sure market-maker bot keeps book populated
- [ ] Alex tests attestation verifier against live Azure quote
- [ ] Run through the full demo flow once together:
  1. Open `perp.ph18.io` → show live prices
  2. Connect wallet
  3. Submit a limit order → see it on orderbook
  4. Submit crossing order from second wallet → fill shows on WebSocket
  5. Click "Verify Enclave" → show DCAP quote → MRENCLAVE matches
  6. Withdraw via multisig → show tx on XRPL testnet explorer
- [ ] If time: record a 2-minute video walkthrough as backup

### Hours 18-24: Sleep + buffer

Be realistic — 6 hours of sleep. Don't skip it.

### Hours 24-30: Final polish + edge cases

- [ ] Fix any bugs found during overnight cooling period
- [ ] Tom polishes UI (responsive, error states, loading spinners)
- [ ] Andrey re-checks infra: Azure VMs alive, tunnels up, orchestrator healthy
- [ ] Alex finalizes pitch deck, ensures slide order matches demo flow
- [ ] Practice full demo run twice (3-min version and 5-min version)
- [ ] Prepare offline backup: screenshots, recorded demo, pre-filled tx hashes

### Hours 30-34: Demo prep

- [ ] Submit project to hackathon platform (description, links, team)
- [ ] Prepare demo laptop: tabs open, wallets connected, terminal ready
- [ ] Last smoke test from venue
- [ ] Quick team huddle: who presents what, who answers technical questions
- [ ] Alex: opening + problem + solution (2 min)
- [ ] Tom: live demo walkthrough (2 min)
- [ ] Andrey: attestation proof + architecture deep dive if asked (1 min + Q&A)

### Hours 34-36: Presentations & judging

- [ ] Present
- [ ] Network with judges
- [ ] Collect contact info from interested parties (VCs, other teams, XRPL folks)

---

## What NOT to do during the hackathon

1. **Don't rewrite the orchestrator** — it works, 16/16 E2E passing
2. **Don't touch the SGX enclave** — rebuild cycle is long and error-prone
3. **Don't add new trading features** (new order types, new markets) — scope creep
4. **Don't optimize performance** — latency is fine for demo
5. **Don't try mainnet launch** — testnet is the safe choice for a live demo

## Judging criteria (typical for Impact Finance)

Based on past hackathons:
- **Technical execution** (40%) — does it work? can you demo live?
- **Innovation** (25%) — is this novel for the XRPL ecosystem?
- **Impact potential** (20%) — who benefits and how much?
- **Presentation quality** (15%) — clear, confident, within time

Our strengths:
- Technical execution is our biggest asset — we have a WORKING product, not a prototype
- Innovation is strong — TEE approach to DeFi on non-smart-contract chains is unique
- Impact: RLUSD utility story + institutional DeFi on XRPL
- Presentation: needs polish (Track C)

---

## Emergency kit (if things break)

| Problem | Fix |
|---|---|
| Azure VMs deallocated | `az vm start -g SGX-RG -n sgx-node-{1,2,3}` from Hetzner |
| Hetzner orchestrator dead | `cd /tmp/perp-9088 && bash start script` |
| SSH tunnels dropped | Re-create: `ssh -f -N -L 9188:localhost:9088 azureuser@20.71.184.176` |
| XRPL testnet faucet down | Use pre-funded wallets (save seeds in secure note) |
| Venue WiFi blocks SSH | Use phone hotspot as fallback |
| Live demo fails on stage | Switch to recorded backup video |

---

## Key numbers for the pitch

- **$280M** — Drift Protocol loss (April 2026, social engineering on human multisig)
- **4,734 bytes** — size of our Intel-signed DCAP attestation quote
- **16.5 seconds** — sequencer failover time (live tested)
- **3 seconds** — split-brain reconvergence (live tested)
- **10** — on-chain XRPL testnet transactions proving 9/9 failure scenarios
- **12 transactions** — total verified multisig txs on testnet (10 from scenarios + 2 from Rust withdrawal)
- **16/16** — E2E test pass rate (as of tonight)
- **$150K** — grant request amount (application ready)

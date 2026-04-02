# TEE vs Smart Contract: Why We Can't Be Robbed Like Drift

**Date:** 2026-04-02
**Context:** Drift Protocol (Solana perp DEX) lost $200M+ due to admin private key compromise

---

## What Happened to Drift

1. The attacker gained access to the **admin signer private key**
2. Prepared in advance: funded wallets a week earlier, made a test transaction
3. In a single batch of transactions drained **everything**: SOL, WETH, BTC, stablecoins
4. Converted to USDC, bridged to Ethereum
5. The protocol posted "unusual activity" when it was already too late

**Root cause:** a single private key controlled all funds. Whoever has the key has everything.

---

## Why This Is Impossible in Our Architecture

### 1. The Key Does Not Exist Outside SGX

```
Drift:                           Our architecture:
┌──────────┐                     ┌──────────────────┐
│ Admin key│ ← stored            │ SGX Enclave      │
│ in file/ │    somewhere        │ ┌──────────────┐ │
│ in HSM/  │    accessible       │ │ ECDSA Key A  │ │
│ in memory│    to operator      │ │ (sealed,     │ │
└──────────┘                     │ │  never leaves│ │
     │                           │ │  enclave)    │ │
     │ stolen →                  │ └──────────────┘ │
     │ full access               └──────────────────┘
     ▼                                    │
  $200M withdrawal               Operator CANNOT
                                  extract the key
```

In SGX the private key is **generated inside the enclave** and **never leaves** it. The operator launches the enclave but physically cannot read the enclave memory contents — this is a guarantee at the Intel CPU level.

### 2. Multisig 2-of-3 — No Single Key

```
Drift: 1 admin key → full control

Our architecture:
  Operator A (Azure): ECDSA Key A — inside SGX
  Operator B (Azure): ECDSA Key B — inside SGX
  Operator C (Azure): ECDSA Key C — inside SGX

  XRPL Escrow: SignerListSet [A, B, C], quorum=2
  Master key: DISABLED

  Any withdrawal requires 2 of 3 signatures.
  Each key is inside its own SGX enclave.
  Operators are on different servers, different providers.
```

Even if the attacker **fully compromises** one server (root access, physical access) — they only gain access to one enclave. To withdraw funds they need to compromise **two enclaves on two different servers**.

### 3. Enclave Code Defines the Rules — the Operator Cannot Bypass Them

```
Drift: admin key can do anything
       (transfer all funds to own address)

Our architecture:
  Enclave code (attested, open-source):
    - Withdrawal only after margin check
    - Signing only for a specific user + amount
    - Rate limit on withdrawals
    - Spending guardrails (signature count limit)

  The operator CANNOT force the enclave to sign
  an arbitrary transaction — the enclave code forbids it.
```

### 4. DCAP Attestation — Code Is Verified

```
Drift: users trust that the smart contract does
       what is written (but admin key bypasses everything)

Our architecture:
  1. Enclave publishes MRENCLAVE (code hash)
  2. Intel signs SGX Quote (DCAP)
  3. Anyone can verify:
     - Enclave code = published open-source code
     - Running on genuine Intel SGX
     - Operator has not modified the code

  If the operator tries to run a modified enclave
  — MRENCLAVE changes → attestation fails
  → users see the substitution
```

### 5. XRPL Settlement — Funds on L1, Not in a Contract

```
Drift: all funds inside a smart contract on Solana
       admin key = full access to contract = full access to funds

Our architecture:
  Funds: RLUSD on XRPL escrow account
  Control: SignerListSet 2-of-3 (not a smart contract)

  XRPL — fixed protocol, no upgradeable contracts.
  SignerListSet — native XRPL feature, not our code.
  No admin key, no upgrade function, no proxy pattern.
```

---

## Attack Comparison Table

| Attack Vector | Drift (Smart Contract) | Our Architecture (TEE + Multisig) |
|---|---|---|
| **Admin key theft** | ✅ Full access ($200M) | ❌ No admin key. Keys in SGX, multisig 2-of-3 |
| **Insider threat** | ✅ One person with the key | ❌ Requires collusion of 2 of 3 operators + SGX compromise |
| **Social engineering** | ✅ Convince the key holder | ❌ The key cannot be "shown" — it is in hardware |
| **Phishing** | ✅ Sign a fake tx | ❌ Enclave verifies that tx is valid (margin check) |
| **Supply chain attack** | ✅ Swap out contract upgrade | ❌ MRENCLAVE changes → attestation fail |
| **Rehearsal attack** | ✅ Test tx → wait → drain | ❌ Every tx goes through margin check in enclave |
| **Rug pull** | ✅ Admin withdraws everything | ❌ Master key disabled, SignerListSet immutable without multisig |

---

## What If SGX Is Compromised?

Theoretical side-channel attacks on SGX exist (Spectre, Foreshadow). However:

1. **One compromised SGX = one key** out of three. Withdrawal requires 2.
2. **Key rotation:** upon discovering a vulnerability — new keys, new SignerListSet, transfer funds.
3. **Intel microcode updates:** fix known side-channels.
4. **Time window:** the attacker needs to compromise 2 SGX instances simultaneously, before key rotation.

Compare: in Drift, once a key is stolen — it's stolen **forever**. In our architecture — even if one SGX is compromised, we have time for key rotation.

---

## What If an Operator Is Malicious?

| Operator Action | Drift | Our Architecture |
|---|---|---|
| Withdraw all funds | ✅ One tx (admin key) | ❌ Requires 2-of-3 + enclave only signs valid tx |
| Swap out code | ✅ Upgrade contract | ❌ MRENCLAVE changes → DCAP attestation fail |
| Delay withdrawals | ✅ Pause contract | ⚠️ Can delay if they are the sequencer, but 2 other operators continue |
| Front-run users | ✅ MEV (sees all tx) | ❌ Orders encrypted for enclave |
| Forge prices | ✅ Modify oracle | ⚠️ Median from 3 operators, one cannot influence |

---

## Practical Recommendations

### For users of our DEX:

1. **Verify attestation** before depositing: `POST /v1/attestation/quote` → verify MRENCLAVE
2. **Check SignerListSet** on XRPL: ensure escrow has quorum=2, master disabled
3. **Make sure operators are on different providers** (Azure, OVH, Hetzner)
4. **Monitor key rotation** — if MRENCLAVE changed, check why

### For operators:

1. **Never store keys outside SGX** — all keys are generated inside the enclave
2. **Disable master key** on escrow account — always
3. **Monitoring:** alerting on unusual withdrawals, spending limit guardrails
4. **Regular key rotation** — don't wait for an incident
5. **DCAP attestation** — publish MRENCLAVE, let users verify

---

## Summary

| | Drift (before hack) | Our Architecture |
|---|---|---|
| Security model | Single admin key | TEE + Multisig 2-of-3 |
| Minimum for theft | 1 key | 2 SGX compromise + 2 operator collusion |
| Time to react | 0 (one tx) | Available (key rotation, 2-of-3 continues operating) |
| Code verification | Audit report (static) | DCAP attestation (runtime, Intel-signed) |
| Funds | In smart contract (admin control) | On XRPL L1 (SignerListSet, no admin) |
| Recovery | Impossible (funds are gone) | Key rotation + new escrow + fund transfer |

**The $200M Drift hack is impossible in a TEE + Multisig architecture.**
Not because we are smarter — but because **the key is physically inaccessible** to the operator.

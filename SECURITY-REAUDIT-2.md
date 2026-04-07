# Security Re-Audit #2: XRPL Perpetual DEX

**Date**: 2026-04-07
**Scope**: Verification of NEW-01 and NEW-02 fixes from re-audit #1

---

## Findings Verified

### NEW-01: Cancel Order TOCTOU — **FIXED** ✅

**File:** `orchestrator/src/api.rs:497-516`

**Fix:** Ownership check now happens BEFORE `cancel_order()`:
```rust
// Check ownership BEFORE removing from orderbook (fixes TOCTOU from audit)
if let Some(user) = request.extensions().get::<auth::AuthenticatedUser>() {
    if let Some(owner) = state.engine.order_owner(order_id).await {
        if owner != user.xrpl_address {
            return err(StatusCode::FORBIDDEN, "cannot cancel another user's order");
        }
    }
}
// Only THEN remove from book
match state.engine.cancel_order(order_id).await { ... }
```

New `order_owner()` method (`trading.rs:254-270`) performs read-only search through bids/asks without modifying the book. `PriceLevel` and `bids/asks` visibility changed to `pub(crate)` for access.

### NEW-02: Mandatory Timestamp — **FIXED** ✅

**File:** `orchestrator/src/auth.rs:54-56,111-122`

**Fix:** Timestamp header is now **required** (not optional):
```rust
let timestamp_str = headers
    .get("x-xrpl-timestamp")
    .and_then(|v| v.to_str().ok())
    .ok_or("missing X-XRPL-Timestamp header (required for replay protection)")?;
```

- Legacy mode (no timestamp) completely removed
- Timestamp always included in signed hash
- New test `missing_timestamp_rejected()` verifies rejection
- All existing tests updated to include timestamp

---

## Remaining Open Items (from previous audits)

| # | Severity | Status | Notes |
|---|----------|--------|-------|
| C-02 | Critical | **Acceptable MVP** | Price/funding auth = localhost + nginx. Needs admin session key for production. |
| C-04 | Critical | **By design MVP** | Deposit trust model. Needs SPV proof for production. |
| NEW-03 | Medium | **Open** | Session key fallback to zeros on file-not-found. Should fail instead. |
| NEW-04 | Medium | **Open** | Enclave receives same mark/index price. Should pass separate values. |
| NEW-05 | Low | **Open** | Account sequence fallback to 1 on error. |
| NEW-06 | Low | **Open** | ocall_rename return values unchecked in enclave. |
| NEW-07 | Info | **Open** | PerpEngine.cpp dead code should be deleted. |

---

## Conclusion

**Both High-severity findings from re-audit #1 are now fully fixed.** The cancel order TOCTOU is resolved with a read-only ownership check before the destructive operation. Replay protection is now mandatory with no legacy bypass.

**Assessment: Ready for testnet deployment.** The remaining open items (NEW-03 through NEW-07) are medium/low severity and acceptable for a PoC/testnet environment. They should be addressed before mainnet.

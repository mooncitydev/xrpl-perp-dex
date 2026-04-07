//! XRPL withdrawal flow: margin check in enclave + submit Payment to XRPL.
//!
//! Uses xrpl-mithril-codec for proper XRPL binary serialization.
//!
//! MVP: single operator, single enclave signature.
//! Production: 2-of-3 multisig via SignerListSet (see doc 04).
//!
//! Flow:
//!   1. User calls POST /v1/withdraw { user_id, amount, destination }
//!   2. Orchestrator autofills tx (Sequence, Fee) from XRPL
//!   3. Orchestrator computes signing_hash via xrpl-mithril-codec
//!   4. Enclave checks margin + ECDSA signs the hash
//!   5. Orchestrator injects signature, serializes blob, submits to XRPL

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tracing::{error, info};
use xrpl_mithril_codec::signing;

/// Withdrawal request from user.
#[derive(Debug, Deserialize)]
pub struct WithdrawRequest {
    pub user_id: String,
    pub amount: String,
    pub destination: String,
}

/// Withdrawal result.
#[derive(Debug, Serialize)]
pub struct WithdrawResult {
    pub status: String,
    pub amount: String,
    pub destination: String,
    pub xrpl_tx_hash: Option<String>,
    pub message: String,
}

/// Submit a withdrawal: enclave signs, orchestrator submits to XRPL.
pub async fn process_withdrawal(
    perp: &crate::perp_client::PerpClient,
    xrpl_url: &str,
    escrow_address: &str,
    escrow_account_id: &str,
    session_key: &str,
    req: &WithdrawRequest,
) -> Result<WithdrawResult> {
    info!(
        user = %req.user_id,
        amount = %req.amount,
        destination = %req.destination,
        "processing withdrawal"
    );

    // Step 1: Autofill — get account sequence from XRPL
    let sequence = fetch_account_sequence(xrpl_url, escrow_address)
        .await
        .unwrap_or(1); // fallback for testnet

    // Step 2: Build Payment tx JSON
    let tx_json = serde_json::json!({
        "TransactionType": "Payment",
        "Account": escrow_address,
        "Destination": req.destination,
        "Amount": {
            "currency": "USD",
            "issuer": escrow_address,
            "value": req.amount
        },
        "Fee": "12",
        "Sequence": sequence,
        "SigningPubKey": "" // Will be filled by enclave or from config
    });

    // Step 3: Compute signing hash via xrpl-mithril-codec
    let tx_map = tx_json.as_object().context("tx_json is not an object")?;
    let sign_hash = signing::signing_hash(tx_map)
        .map_err(|e| anyhow::anyhow!("codec signing_hash failed: {:?}", e))?;
    let sign_hash_hex = hex::encode(sign_hash);

    info!(
        sign_hash = %sign_hash_hex,
        sequence = sequence,
        "computed XRPL signing hash via binary codec"
    );

    // Step 4: Call enclave — margin check + ECDSA sign
    let result = perp
        .withdraw(
            &req.user_id,
            &req.amount,
            escrow_account_id,
            session_key,
            &sign_hash_hex,
        )
        .await;

    match result {
        Ok(resp) => {
            let status = resp["status"].as_str().unwrap_or("unknown");
            if status != "success" {
                let msg = resp["message"]
                    .as_str()
                    .unwrap_or("enclave rejected withdrawal")
                    .to_string();
                return Ok(WithdrawResult {
                    status: "error".into(),
                    amount: req.amount.clone(),
                    destination: req.destination.clone(),
                    xrpl_tx_hash: None,
                    message: msg,
                });
            }

            let signature_hex = resp["signature"].as_str().unwrap_or("").to_string();

            info!(
                user = %req.user_id,
                sig_len = signature_hex.len(),
                "enclave signed withdrawal"
            );

            // Step 5: Inject signature into tx, serialize blob, submit
            let mut signed_tx = tx_json.clone();
            signed_tx["TxnSignature"] = serde_json::Value::String(signature_hex.to_uppercase());

            // Serialize to binary blob
            let signed_map = signed_tx
                .as_object()
                .context("signed tx is not an object")?;
            let mut blob = Vec::new();
            xrpl_mithril_codec::serializer::serialize_json_object(signed_map, &mut blob, false)
                .map_err(|e| anyhow::anyhow!("codec serialize failed: {:?}", e))?;
            let blob_hex = hex::encode_upper(&blob);

            // Submit blob to XRPL
            match submit_blob(xrpl_url, &blob_hex).await {
                Ok(xrpl_hash) => {
                    info!(
                        user = %req.user_id,
                        xrpl_hash = %xrpl_hash,
                        "withdrawal submitted to XRPL"
                    );
                    Ok(WithdrawResult {
                        status: "success".into(),
                        amount: req.amount.clone(),
                        destination: req.destination.clone(),
                        xrpl_tx_hash: Some(xrpl_hash),
                        message: "withdrawal submitted to XRPL".into(),
                    })
                }
                Err(e) => {
                    error!(user = %req.user_id, "XRPL submission failed: {}", e);
                    Ok(WithdrawResult {
                        status: "signed_but_not_submitted".into(),
                        amount: req.amount.clone(),
                        destination: req.destination.clone(),
                        xrpl_tx_hash: None,
                        message: format!(
                            "Enclave signed but XRPL submission failed: {}. Balance already deducted.",
                            e
                        ),
                    })
                }
            }
        }
        Err(e) => Ok(WithdrawResult {
            status: "error".into(),
            amount: req.amount.clone(),
            destination: req.destination.clone(),
            xrpl_tx_hash: None,
            message: format!("Enclave error: {}", e),
        }),
    }
}

/// Fetch account Sequence number from XRPL.
async fn fetch_account_sequence(xrpl_url: &str, account: &str) -> Result<u32> {
    let client = reqwest::Client::new();
    let resp: serde_json::Value = client
        .post(xrpl_url)
        .json(&serde_json::json!({
            "method": "account_info",
            "params": [{"account": account}]
        }))
        .send()
        .await?
        .json()
        .await?;

    let seq = resp["result"]["account_data"]["Sequence"]
        .as_u64()
        .context("missing Sequence in account_info")?;
    Ok(seq as u32)
}

/// Submit a pre-signed tx blob to XRPL via JSON-RPC.
async fn submit_blob(xrpl_url: &str, blob_hex: &str) -> Result<String> {
    let client = reqwest::Client::new();
    let resp: serde_json::Value = client
        .post(xrpl_url)
        .json(&serde_json::json!({
            "method": "submit",
            "params": [{"tx_blob": blob_hex}]
        }))
        .send()
        .await
        .context("XRPL submit request failed")?
        .json()
        .await
        .context("XRPL submit response parse failed")?;

    let engine_result = resp["result"]["engine_result"]
        .as_str()
        .unwrap_or("unknown");

    if engine_result == "tesSUCCESS" || engine_result.starts_with("tes") {
        let hash = resp["result"]["tx_json"]["hash"]
            .as_str()
            .unwrap_or("unknown")
            .to_string();
        Ok(hash)
    } else {
        anyhow::bail!(
            "XRPL: {} — {}",
            engine_result,
            resp["result"]["engine_result_message"]
                .as_str()
                .unwrap_or("")
        )
    }
}

//! XRPL signature authentication middleware.
//!
//! Users sign request body with their XRPL secp256k1 private key.
//! Server verifies signature and derives XRPL address from public key.
//!
//! Headers:
//!   X-XRPL-Address:   r-address of the signer
//!   X-XRPL-PublicKey:  compressed secp256k1 public key (hex, 66 chars)
//!   X-XRPL-Signature:  DER-encoded ECDSA signature of SHA-256(body) (hex)
//!
//! For GET requests (no body): signs the full URI path + query string.

use axum::{
    body::Body,
    extract::Request,
    http::{HeaderMap, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use k256::ecdsa::{signature::Verifier, Signature, VerifyingKey};
use sha2::{Digest, Sha256};
use tracing::warn;

use crate::xrpl_signer::pubkey_to_xrpl_address;

/// Authentication result: verified XRPL address.
#[derive(Clone, Debug)]
pub struct AuthenticatedUser {
    pub xrpl_address: String,
}

/// Extract and verify XRPL signature from request headers.
pub fn verify_request(
    headers: &HeaderMap,
    body_bytes: &[u8],
    uri_path: &str,
) -> Result<AuthenticatedUser, String> {
    // Extract headers
    let address = headers
        .get("x-xrpl-address")
        .and_then(|v| v.to_str().ok())
        .ok_or("missing X-XRPL-Address header")?;

    let pubkey_hex = headers
        .get("x-xrpl-publickey")
        .and_then(|v| v.to_str().ok())
        .ok_or("missing X-XRPL-PublicKey header")?;

    let sig_hex = headers
        .get("x-xrpl-signature")
        .and_then(|v| v.to_str().ok())
        .ok_or("missing X-XRPL-Signature header")?;

    // Validate address format
    if !address.starts_with('r') || address.len() < 25 || address.len() > 35 {
        return Err("invalid XRPL address format".into());
    }

    // Validate pubkey format (33 bytes compressed = 66 hex chars)
    if pubkey_hex.len() != 66 {
        return Err("invalid public key length (expected 66 hex chars)".into());
    }

    // Decode public key
    let pubkey_bytes = hex::decode(pubkey_hex)
        .map_err(|_| "invalid public key hex")?;
    let verifying_key = VerifyingKey::from_sec1_bytes(&pubkey_bytes)
        .map_err(|_| "invalid secp256k1 public key")?;

    // Verify pubkey → address derivation
    let uncompressed_point = verifying_key.to_encoded_point(false);
    let uncompressed_bytes = uncompressed_point.as_bytes();
    let uncompressed_hex = hex::encode(uncompressed_bytes);
    let derived_address = pubkey_to_xrpl_address(&uncompressed_hex)
        .map_err(|e| format!("address derivation failed: {}", e))?;
    if derived_address != address {
        return Err(format!(
            "address mismatch: header={}, derived from pubkey={}",
            address, derived_address
        ));
    }

    // Compute hash of body (or URI for GET)
    let hash = if body_bytes.is_empty() {
        Sha256::digest(uri_path.as_bytes())
    } else {
        Sha256::digest(body_bytes)
    };

    // Decode and verify signature
    let sig_bytes = hex::decode(sig_hex)
        .map_err(|_| "invalid signature hex")?;
    let signature = Signature::from_der(&sig_bytes)
        .map_err(|_| "invalid DER signature")?;

    verifying_key
        .verify(&hash, &signature)
        .map_err(|_| "signature verification failed")?;

    Ok(AuthenticatedUser {
        xrpl_address: address.to_string(),
    })
}

/// Axum middleware: verify auth headers on mutating endpoints.
/// GET requests to public market data are exempt.
pub async fn auth_middleware(request: Request, next: Next) -> Response {
    let method = request.method().clone();
    let uri = request.uri().path().to_string();

    // Public endpoints — no auth required
    if method == "GET" {
        let is_public = uri == "/v1/openapi.json"
            || uri.starts_with("/v1/markets/");
        if is_public {
            return next.run(request).await;
        }
    }

    let headers = request.headers().clone();
    let uri_string = request.uri().to_string();

    // For requests with body, we need to read it for signature verification
    let (parts, body) = request.into_parts();
    let body_bytes = match axum::body::to_bytes(body, 1024 * 1024).await {
        Ok(bytes) => bytes,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(serde_json::json!({"status": "error", "message": "failed to read body"})),
            )
                .into_response();
        }
    };

    match verify_request(&headers, &body_bytes, &uri_string) {
        Ok(user) => {
            // For POST with body: verify user_id in body matches authenticated address
            if !body_bytes.is_empty() {
                if let Ok(body_json) = serde_json::from_slice::<serde_json::Value>(&body_bytes) {
                    if let Some(body_user_id) = body_json.get("user_id").and_then(|v| v.as_str()) {
                        if body_user_id != user.xrpl_address {
                            return (
                                StatusCode::FORBIDDEN,
                                Json(serde_json::json!({
                                    "status": "error",
                                    "message": format!(
                                        "user_id '{}' does not match authenticated address '{}'",
                                        body_user_id, user.xrpl_address
                                    )
                                })),
                            )
                                .into_response();
                        }
                    }
                }
            }

            // For GET with user_id query param: verify matches
            if method == "GET" {
                if let Some(query) = parts.uri.query() {
                    for pair in query.split('&') {
                        if let Some(val) = pair.strip_prefix("user_id=") {
                            if val != user.xrpl_address {
                                return (
                                    StatusCode::FORBIDDEN,
                                    Json(serde_json::json!({
                                        "status": "error",
                                        "message": "user_id does not match authenticated address"
                                    })),
                                )
                                    .into_response();
                            }
                        }
                    }
                }
            }

            // Reconstruct request with body
            let request = Request::from_parts(parts, Body::from(body_bytes));
            next.run(request).await
        }
        Err(msg) => {
            warn!(uri = %uri_string, "auth failed: {}", msg);
            (
                StatusCode::UNAUTHORIZED,
                Json(serde_json::json!({"status": "error", "message": msg})),
            )
                .into_response()
        }
    }
}

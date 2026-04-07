//! WebSocket gateway — real-time event push to connected clients.
//!
//! All events broadcast via `tokio::sync::broadcast`. Each connected
//! client gets its own receiver. Slow clients skip (lag) rather than
//! block producers.

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    response::IntoResponse,
};
use std::sync::Arc;
use tokio::sync::broadcast;
use tracing::{info, warn};

use crate::api::AppState;

/// Events pushed over WebSocket. JSON with `"type"` discriminator.
#[derive(Clone, Debug, serde::Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum WsEvent {
    Trade {
        trade_id: u64,
        price: String,
        size: String,
        taker_side: String,
        maker_user_id: String,
        taker_user_id: String,
        timestamp_ms: u64,
    },
    Orderbook {
        bids: Vec<[String; 2]>,
        asks: Vec<[String; 2]>,
    },
    Ticker {
        mark_price: String,
        index_price: String,
        timestamp: u64,
    },
    Liquidation {
        position_id: u64,
        user_id: String,
        price: String,
    },
}

/// Axum handler: upgrade to WebSocket, then forward broadcast events.
pub async fn ws_handler(
    ws: WebSocketUpgrade,
    State(state): State<Arc<AppState>>,
) -> impl IntoResponse {
    let rx = state.ws_tx.subscribe();
    ws.on_upgrade(move |socket| client_loop(socket, rx))
}

/// Per-client loop: read from broadcast, write JSON to socket.
async fn client_loop(mut socket: WebSocket, mut rx: broadcast::Receiver<WsEvent>) {
    info!("WebSocket client connected");
    loop {
        tokio::select! {
            result = rx.recv() => {
                match result {
                    Ok(event) => {
                        let json = match serde_json::to_string(&event) {
                            Ok(j) => j,
                            Err(_) => continue,
                        };
                        if socket.send(Message::Text(json.into())).await.is_err() {
                            break;
                        }
                    }
                    Err(broadcast::error::RecvError::Lagged(n)) => {
                        warn!("WebSocket client lagged, skipped {} events", n);
                    }
                    Err(broadcast::error::RecvError::Closed) => break,
                }
            }
            msg = socket.recv() => {
                match msg {
                    Some(Ok(Message::Close(_))) | None => break,
                    _ => {}
                }
            }
        }
    }
    info!("WebSocket client disconnected");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn trade_event_serialization() {
        let event = WsEvent::Trade {
            trade_id: 1,
            price: "0.55000000".into(),
            size: "100.00000000".into(),
            taker_side: "long".into(),
            maker_user_id: "rAlice".into(),
            taker_user_id: "rBob".into(),
            timestamp_ms: 1743500000000,
        };
        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("\"type\":\"trade\""));
        assert!(json.contains("\"trade_id\":1"));
        assert!(json.contains("\"price\":\"0.55000000\""));
    }

    #[test]
    fn orderbook_event_serialization() {
        let event = WsEvent::Orderbook {
            bids: vec![["0.55".into(), "100.0".into()]],
            asks: vec![["0.56".into(), "50.0".into()]],
        };
        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("\"type\":\"orderbook\""));
        assert!(json.contains("\"bids\""));
        assert!(json.contains("\"asks\""));
    }

    #[test]
    fn ticker_event_serialization() {
        let event = WsEvent::Ticker {
            mark_price: "0.55120000".into(),
            index_price: "0.55120000".into(),
            timestamp: 1743500000,
        };
        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("\"type\":\"ticker\""));
        assert!(json.contains("\"mark_price\""));
    }

    #[test]
    fn liquidation_event_serialization() {
        let event = WsEvent::Liquidation {
            position_id: 7,
            user_id: "rCharlie".into(),
            price: "0.48000000".into(),
        };
        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("\"type\":\"liquidation\""));
        assert!(json.contains("\"position_id\":7"));
    }

    #[test]
    fn all_events_have_type_field() {
        let events: Vec<WsEvent> = vec![
            WsEvent::Trade {
                trade_id: 0,
                price: "0".into(),
                size: "0".into(),
                taker_side: "long".into(),
                maker_user_id: "a".into(),
                taker_user_id: "b".into(),
                timestamp_ms: 0,
            },
            WsEvent::Orderbook {
                bids: vec![],
                asks: vec![],
            },
            WsEvent::Ticker {
                mark_price: "0".into(),
                index_price: "0".into(),
                timestamp: 0,
            },
            WsEvent::Liquidation {
                position_id: 0,
                user_id: "a".into(),
                price: "0".into(),
            },
        ];
        for event in events {
            let json = serde_json::to_string(&event).unwrap();
            assert!(
                json.contains("\"type\":"),
                "missing type field in: {}",
                json
            );
        }
    }
}

#!/usr/bin/env python3
"""Mock enclave server for Docker testing (replaces real SGX enclave)."""

from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory state
users = {}
positions = []
mark_price = 100000000  # 1.0 FP8
next_pos_id = 0


@app.route("/v1/pool/status", methods=["GET"])
def pool_status():
    return jsonify({"status": "success", "accounts": [], "mode": "mock"})


@app.route("/v1/perp/deposit", methods=["POST"])
def deposit():
    data = request.json
    uid = data["user_id"]
    if uid not in users:
        users[uid] = {"margin_balance": 0, "xrp_balance": 0}
    # Parse FP8 string
    amount = int(round(float(data["amount"]) * 100000000))
    users[uid]["margin_balance"] += amount
    return jsonify({"status": "success"})


@app.route("/v1/perp/balance", methods=["GET"])
def balance():
    uid = request.args.get("user_id", "")
    if uid not in users:
        return jsonify({"status": "error", "message": "user not found"}), 500
    u = users[uid]
    mb = u["margin_balance"]
    return jsonify({
        "status": "success",
        "data": {
            "margin_balance": f"{mb // 100000000}.{mb % 100000000:08d}",
            "xrp_balance": "0.00000000",
            "xrp_collateral_value": "0.00000000",
            "staked_xrp": "0.00000000",
            "staked_collateral_value": "0.00000000",
            "stake_tier": 0,
            "fee_multiplier": "1.00000000",
            "points": "0.00000000",
            "unrealized_pnl": "0.00000000",
            "used_margin": "0.00000000",
            "available_margin": f"{mb // 100000000}.{mb % 100000000:08d}",
            "positions": []
        }
    })


@app.route("/v1/perp/position/open", methods=["POST"])
def open_position():
    global next_pos_id
    data = request.json
    next_pos_id += 1
    return jsonify({"status": "success", "position_id": next_pos_id})


@app.route("/v1/perp/position/close", methods=["POST"])
def close_position():
    return jsonify({"status": "success"})


@app.route("/v1/perp/price", methods=["POST"])
def update_price():
    global mark_price
    mark_price = int(round(float(request.json["mark_price"]) * 100000000))
    return jsonify({"status": "success"})


@app.route("/v1/perp/liquidations/check", methods=["GET"])
def check_liquidations():
    return jsonify({"status": "success", "count": 0, "liquidatable": []})


@app.route("/v1/perp/liquidate", methods=["POST"])
def liquidate():
    return jsonify({"status": "success"})


@app.route("/v1/perp/funding/apply", methods=["POST"])
def apply_funding():
    return jsonify({"status": "success"})


@app.route("/v1/perp/state/save", methods=["POST"])
def save_state():
    return jsonify({"status": "success"})


@app.route("/v1/perp/state/load", methods=["POST"])
def load_state():
    return jsonify({"status": "success"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9088)

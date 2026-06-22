import time
import httpx
import json
import hmac
import hashlib
import base64
import math
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
from cachetools import TTLCache

app = Flask(__name__)
CORS(app)
cache = TTLCache(maxsize=100, ttl=300)
uid_region_cache = {}

SUPPORTED_REGIONS = ["vn", "th", "tw", "sg", "id", "ind", "bd", "pk", "me", "br", "us", "na", "sac", "ru", "cis", "europe"]
SECRET = "GAMESKINBOFFIDCHECKERSECURITYPROTOCOL"

def generate_token(uid: str) -> str:
    timestamp_ms = int(time.time() * 1000)
    time_block = math.floor(timestamp_ms / 30000)
    nonce = hmac.new(
        SECRET.encode(),
        str(time_block).encode(),
        hashlib.sha256
    ).hexdigest()[:32]
    signature = hmac.new(
        nonce.encode(),
        f"{uid}|{timestamp_ms}".encode(),
        hashlib.sha256
    ).hexdigest()
    raw = f"{uid}|{timestamp_ms}|{signature}"
    return base64.b64encode(raw.encode()).decode()

def GetAccountInformation(uid: str, region: str):
    """Synchronous version using httpx.Client"""
    token = generate_token(uid)
    url = f"https://gameskinbo.com/api/ff_id_checker?uid={uid}&token={token}&region={region}"
    headers = {
        'authority': 'gameskinbo.com',
        'accept': '*/*',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
        'x-api-client': 'gameskinbo-web',
        'referer': 'https://gameskinbo.com/free_fire_id_checker',
    }
    with httpx.Client(verify=False, timeout=10.0) as client:
        resp = client.get(url, headers=headers)
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}")
        data = resp.json()
        if "name" not in data:
            raise Exception(f"UID not found in {region}")
        
        return {
            "uid": int(uid),
            "nickname": data.get("name", ""),
            "likes": int(data.get("likes", 0)) if data.get("likes") else 0,
            "level": data.get("level", 0),
            "region": data.get("region", region).upper(),
            "badges": data.get("equipped_bp_badges", 0),
            "booyah_pass": False,
            "full_data": data
        }

def cached_endpoint(ttl=300):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            key = (request.path, tuple(request.args.items()))
            if key in cache:
                return cache[key]
            res = fn(*a, **k)
            cache[key] = res
            return res
        return wrapper
    return decorator

@app.route('/player-info')
@cached_endpoint()
def get_account_info():
    uid = request.args.get('uid')
    if not uid:
        return jsonify({"error": "Please provide UID."}), 400

    print(f"DEBUG: Processing request for UID: {uid}")
    if uid in uid_region_cache:
        try:
            return_data = GetAccountInformation(uid, uid_region_cache[uid])
            formatted_json = json.dumps(return_data, indent=2, ensure_ascii=False)
            return formatted_json, 200, {'Content-Type': 'application/json; charset=utf-8'}
        except Exception as ex:
            print(f"DEBUG: Cache hit failed with {ex}")
            # fall through to try all regions again

    print(f"DEBUG: Starting loop over regions: {SUPPORTED_REGIONS}")
    for region in SUPPORTED_REGIONS:
        try:
            return_data = GetAccountInformation(uid, region)
            uid_region_cache[uid] = region
            formatted_json = json.dumps(return_data, indent=2, ensure_ascii=False)
            return formatted_json, 200, {'Content-Type': 'application/json; charset=utf-8'}
        except Exception as e:
            print(f"DEBUG: [{region}] GetAccountInformation error: {type(e).__name__} - {e}", flush=True)
            continue

    print("DEBUG: All regions failed. Returning 404.", flush=True)
    return jsonify({"error": "UID not found in any region."}), 404

@app.route("/")
def home():
    return jsonify({
        "message": "API is running. Use : https://nullinfoapi.vercel.app/player-info?uid={uid}"
    })

@app.route('/refresh', methods=['GET', 'POST'])
def refresh_tokens_endpoint():
    cache.clear()
    uid_region_cache.clear()
    return jsonify({
        'message': 'Cache refreshed successfully.'
    }), 200

# For local development
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

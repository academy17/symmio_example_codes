"""Vibecaps Demo (Base): Instant Open + Stop Loss

Run
- python trading_bot_example/vibecaps_open_set_sl_demo.py

Required .env
- PRIVATE_KEY
- VIBE_SUBACCOUNT (or SUB_ACCOUNT_ADDRESS)
- CONDITIONAL_ORDERS_BASE_URL
- VIBE_MULTIACCOUNT_ADDRESS (or MULTIACCOUNT_ADDRESS)
- VIBE_HEDGER_WHITELIST (or HEDGER_WHITELIST)  # JSON list or comma-separated addresses

Optional .env
- VIBE_SOLVER_URL
- VIBE_CHAIN_ID
- VIBE_DIAMOND_ADDRESS
- MUON_BASE_URL
- CONDITIONAL_ORDERS_APP_NAME
"""

import os
import time
import json
import traceback
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN

import asyncio
import requests
import websockets
from eth_account import Account
from eth_account.messages import encode_defunct
from dotenv import load_dotenv
from web3 import Web3


# --------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------
CONFIG = {
    "SYMBOL_ID": 1,            # Symbol ID for SYMM
    "QUANTITY": "2500",          # Trade quantity
    "POSITION_TYPE": 1,         # 0 = Long, 1 = Short
    "ORDER_TYPE": 1,            # 1 = Market
    "LEVERAGE": "3",
    "MAX_FUNDING_RATE": "200",
    "DEADLINE_OFFSET": 3600,    # 1 hour
    "STATUS_POLL_INTERVAL": 2,  # seconds
    "SLIPPAGE": Decimal("0.95"),  # -5% for shorts
}

load_dotenv()

# --------------------------------------------------------------------
# Environment / Wallet Setup
# --------------------------------------------------------------------
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

# Vibe-specific: active account (subaccount address)
ACTIVE_ACCOUNT = os.getenv("VIBE_SUBACCOUNT") or os.getenv("ACTIVE_ACCOUNT") or os.getenv("SUB_ACCOUNT_ADDRESS")
if ACTIVE_ACCOUNT:
    ACTIVE_ACCOUNT = Web3.to_checksum_address(ACTIVE_ACCOUNT)

wallet = Account.from_key(PRIVATE_KEY)

# --------------------------------------------------------------------
# Vibe-Specific URLs and Addresses
# --------------------------------------------------------------------
SOLVER_BASE_URL = os.getenv("VIBE_SOLVER_URL")
CHAIN_ID = int(os.getenv("VIBE_CHAIN_ID", "8453"))  # Base chain
SYMMIO_DIAMOND_ADDRESS = os.getenv("VIBE_DIAMOND_ADDRESS", "0xC6a7cc26fd84aE573b705423b7d1831139793025")
SYMMIO_DIAMOND_ADDRESS = Web3.to_checksum_address(SYMMIO_DIAMOND_ADDRESS)

CONDITIONAL_ORDERS_BASE_URL = os.getenv("CONDITIONAL_ORDERS_BASE_URL")
VIBE_MULTI_ACCOUNT_ADDRESS = (
    os.getenv("VIBE_MULTIACCOUNT_ADDRESS")
    or os.getenv("MULTIACCOUNT_ADDRESS")
    or os.getenv("MULTI_ACCOUNT_ADDRESS")
)
if VIBE_MULTI_ACCOUNT_ADDRESS:
    VIBE_MULTI_ACCOUNT_ADDRESS = Web3.to_checksum_address(VIBE_MULTI_ACCOUNT_ADDRESS)

_ENV_HEDGER_WHITELIST = os.getenv("VIBE_HEDGER_WHITELIST") or os.getenv("HEDGER_WHITELIST")

MUON_BASE_URL = os.getenv("MUON_BASE_URL", "https://muon-oracle1.rasa.capital/v1/")

DOMAIN = "localhost"
ORIGIN = "http://localhost:3000"
LOGIN_URI = f"{SOLVER_BASE_URL}/login"

# WebSocket notifications service
NOTIFICATION_WS_URL = "wss://notification.rasa.capital/ws/v1/subscribe"
NOTIFICATION_APP_NAME = "Base_Superflow_Production"

CONDITIONAL_ORDERS_APP_NAME = os.getenv("CONDITIONAL_ORDERS_APP_NAME", "VIBE")

# --------------------------------------------------------------------
# Dynamic URLs (built at runtime)
# --------------------------------------------------------------------
def get_locked_params_url(symbol_id: int, leverage: str) -> str:
    return f"{SOLVER_BASE_URL}/get_locked_params/{symbol_id}?leverage={leverage}"


def get_muon_url(party_a: str, chain_id: int, symmio: str, symbol_id: int) -> str:
    return (
        f"{MUON_BASE_URL}?app=symmio&method=uPnl_A_withSymbolPrice"
        f"&params[partyA]={party_a}"
        f"&params[chainId]={chain_id}"
        f"&params[symmio]={symmio}"
        f"&params[symbolId]={symbol_id}"
    )


# --------------------------------------------------------------------
# Timestamps for SIWE
# --------------------------------------------------------------------
ISSUED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
EXPIRATION_DATE = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# --------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------
def build_siwe_message(
    domain: str,
    address: str,
    statement: str,
    uri: str,
    version: str,
    chain_id: int,
    nonce: str,
    issued_at: str,
    expiration_time: str,
) -> str:
    return f"""{domain} wants you to sign in with your Ethereum account:
{address}

{statement}

URI: {uri}
Version: {version}
Chain ID: {chain_id}
Nonce: {nonce}
Issued At: {issued_at}
Expiration Time: {expiration_time}"""


def get_nonce(address: str) -> str:
    url = f"{SOLVER_BASE_URL}/nonce/{address}"
    print(f"[NONCE] Fetching nonce from: {url}")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()["nonce"]


def login() -> str:
    """Perform SIWE login and return the access token."""
    print(f"[LOGIN] Wallet: {wallet.address}")
    print(f"[LOGIN] Active Account: {ACTIVE_ACCOUNT}")

    nonce = get_nonce(ACTIVE_ACCOUNT)
    print(f"[LOGIN] Got nonce: {nonce}")

    message_string = build_siwe_message(
        domain=DOMAIN,
        address=wallet.address,
        statement=f"msg: {ACTIVE_ACCOUNT}",
        uri=LOGIN_URI,
        version="1",
        chain_id=CHAIN_ID,
        nonce=nonce,
        issued_at=ISSUED_AT,
        expiration_time=EXPIRATION_DATE,
    )
    print(f"[LOGIN] SIWE Message:\n{message_string}\n")

    message = encode_defunct(text=message_string)
    signed_message = wallet.sign_message(message)
    signature = "0x" + signed_message.signature.hex()
    print(f"[LOGIN] Signature: {signature[:20]}...")

    body = {
        "account_address": ACTIVE_ACCOUNT,
        "expiration_time": EXPIRATION_DATE,
        "issued_at": ISSUED_AT,
        "signature": signature,
        "nonce": nonce,
    }
    headers = {
        "Content-Type": "application/json",
        "Origin": ORIGIN,
        "Referer": ORIGIN,
    }

    print("[LOGIN] Sending login request...")
    response = requests.post(LOGIN_URI, json=body, headers=headers, timeout=30)
    print(f"[LOGIN] Response: {response.text}")
    response.raise_for_status()

    token = response.json().get("access_token")
    if not token:
        raise ValueError("No access_token in login response")
    return token


def fetch_muon_price() -> Decimal:
    """Fetch current price from Muon oracle (returns price as Decimal, converted from wei)."""
    url = get_muon_url(ACTIVE_ACCOUNT, CHAIN_ID, SYMMIO_DIAMOND_ADDRESS, CONFIG["SYMBOL_ID"])
    print(f"[MUON] Fetching price from: {url}")

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()

    price_wei = data["result"]["data"]["result"]["price"]
    if not price_wei:
        raise ValueError("Muon price not found in response")

    # Convert from wei (18 decimals) to normal units
    price = Decimal(price_wei) / Decimal("1e18")
    print(f"[MUON] Price (wei): {price_wei}")
    print(f"[MUON] Price (units): {price}")
    return price


def fetch_locked_params() -> dict:
    """Fetch locked parameters (CVA, LF, MM values) from the solver."""
    url = get_locked_params_url(CONFIG["SYMBOL_ID"], CONFIG["LEVERAGE"])
    print(f"[PARAMS] Fetching locked params from: {url}")

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()

    if data.get("message") == "Success" or "cva" in data:
        print(f"[PARAMS] Locked params: {json.dumps(data, indent=2)}")
        return data
    else:
        raise ValueError(f"Failed to fetch locked params: {data}")


def fetch_symbol_info(symbol_id: int) -> dict:
    """Fetch symbol info including price_precision and quantity_precision."""
    url = f"{SOLVER_BASE_URL}/contract-symbols"
    print(f"[SYMBOLS] Fetching symbol info from: {url}")

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()

    symbols: list[dict] = []
    if isinstance(payload, list):
        symbols = [s for s in payload if isinstance(s, dict)]
    elif isinstance(payload, dict):
        candidate = None
        for key in ("symbols", "data", "result", "items", "contract_symbols"):
            val = payload.get(key)
            if isinstance(val, list):
                candidate = val
                break
            if isinstance(val, dict):
                nested = val.get("symbols") or val.get("data") or val.get("result")
                if isinstance(nested, list):
                    candidate = nested
                    break

        if isinstance(candidate, list):
            symbols = [s for s in candidate if isinstance(s, dict)]
        else:
            # Sometimes it's a mapping like {"1": {...}, "2": {...}}
            values = list(payload.values())
            if values and all(isinstance(v, dict) for v in values):
                symbols = values
    else:
        raise ValueError(f"Unexpected /contract-symbols payload type: {type(payload)}")

    def _coerce_int(val) -> int | None:
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    for sym in symbols:
        sym_id = (
            _coerce_int(sym.get("symbol_id"))
            or _coerce_int(sym.get("symbolId"))
            or _coerce_int(sym.get("id"))
        )
        if sym_id == symbol_id:
            print(
                f"[SYMBOLS] Found symbol {symbol_id}: "
                f"price_precision={sym.get('price_precision')}, "
                f"quantity_precision={sym.get('quantity_precision')}"
            )
            return sym

    payload_hint = f"type={type(payload).__name__}"
    if isinstance(payload, dict):
        payload_hint += f", keys={list(payload.keys())[:10]}"
    raise ValueError(f"Symbol ID {symbol_id} not found in contract-symbols ({payload_hint})")


def format_decimal(value: Decimal, precision: int) -> str:
    """Format a Decimal to a string with the specified number of decimal places."""
    quantizer = Decimal(10) ** -precision
    formatted = value.quantize(quantizer, rounding=ROUND_DOWN)
    return str(formatted)


def calculate_normalized_locked_value(
    notional: Decimal,
    locked_param: str,
    leverage: Decimal,
    apply_leverage: bool = True,
) -> str:
    """Calculate normalized locked value (CVA, LF, MM)."""
    locked = Decimal(str(locked_param))
    if apply_leverage:
        val = notional * locked / (Decimal("100") * leverage)
    else:
        val = notional * locked / Decimal("100")

    # Strip trailing zeros
    s = "{:f}".format(val)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def open_instant_trade(token: str) -> tuple[str, Decimal, str, str]:
    """
    Open an instant trade.
    Returns (temp_quote_id, open_price, requested_open_price_str, quantity_str).
    """
    print("[TRADE] Starting instant open...")

    # 1. Fetch symbol info for precision
    symbol_info = fetch_symbol_info(CONFIG["SYMBOL_ID"])
    price_precision = symbol_info.get("price_precision", 6)
    quantity_precision = symbol_info.get("quantity_precision", 6)

    # 2. Fetch price
    fetched_price = fetch_muon_price()

    # 3. Apply slippage (+5% for long, -5% for short)
    adjusted_price = fetched_price * CONFIG["SLIPPAGE"]
    formatted_price = format_decimal(adjusted_price, price_precision)
    slippage_label = "+5%" if CONFIG["SLIPPAGE"] >= Decimal("1") else "-5%"
    print(f"[TRADE] Adjusted price ({slippage_label}): {adjusted_price} -> formatted: {formatted_price}")

    # 4. Fetch locked params
    locked_params = fetch_locked_params()
    leverage = Decimal(locked_params.get("leverage", CONFIG["LEVERAGE"]))

    # 5. Format quantity with correct precision
    quantity = Decimal(CONFIG["QUANTITY"])
    formatted_quantity = format_decimal(quantity, quantity_precision)
    print(f"[TRADE] Quantity: {quantity} -> formatted: {formatted_quantity}")

    # 6. Calculate notional (use formatted price for consistency)
    notional = Decimal(formatted_price) * Decimal(formatted_quantity)
    print(f"[TRADE] Notional: {notional}")

    # 7. Calculate normalized values
    normalized_cva = calculate_normalized_locked_value(notional, locked_params["cva"], leverage, True)
    normalized_lf = calculate_normalized_locked_value(notional, locked_params["lf"], leverage, True)
    normalized_party_amm = calculate_normalized_locked_value(notional, locked_params["partyAmm"], leverage, True)
    normalized_party_bmm = calculate_normalized_locked_value(notional, locked_params["partyBmm"], leverage, False)

    print(f"[TRADE] CVA: {normalized_cva}, LF: {normalized_lf}")
    print(f"[TRADE] PartyAmm: {normalized_party_amm}, PartyBmm: {normalized_party_bmm}")

    # 8. Build payload
    deadline = int(time.time()) + CONFIG["DEADLINE_OFFSET"]
    trade_params = {
        "symbolId": CONFIG["SYMBOL_ID"],
        "positionType": CONFIG["POSITION_TYPE"],
        "orderType": CONFIG["ORDER_TYPE"],
        "price": formatted_price,
        "quantity": formatted_quantity,
        "cva": normalized_cva,
        "lf": normalized_lf,
        "partyAmm": normalized_party_amm,
        "partyBmm": normalized_party_bmm,
        "maxFundingRate": CONFIG["MAX_FUNDING_RATE"],
        "deadline": deadline,
    }
    print(f"[TRADE] Payload: {json.dumps(trade_params, indent=2)}")

    # 7. Send request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    response = requests.post(f"{SOLVER_BASE_URL}/instant_open", json=trade_params, headers=headers, timeout=30)
    print(f"[TRADE] Response: {response.text}")
    response.raise_for_status()

    result = response.json()
    temp_quote_id = result.get("temp_quote_id") or result.get("quote_id")
    if not temp_quote_id:
        raise ValueError("No temp_quote_id in response")

    return temp_quote_id, fetched_price, formatted_price, formatted_quantity


async def wait_for_quote_confirmation(temp_quote_id: int, timeout: int = 120) -> int:
    """Subscribe to WebSocket notifications and wait for quote confirmation.
    
    Returns the permanent quote_id when the quote is confirmed on-chain.
    """
    print(f"[WS] Connecting to notifications service...")
    print(f"[WS] URL: {NOTIFICATION_WS_URL}")
    print(f"[WS] Waiting for temp_quote_id: {temp_quote_id}")
    
    # Build subscription message
    subscribe_msg = {
        "channel_patterns": [
            {
                "app_name": NOTIFICATION_APP_NAME,
                "address": ACTIVE_ACCOUNT,
                "primary_identifier": "*",
                "secondary_identifier": "*"
            }
        ]
    }
    
    target_temp_id = int(temp_quote_id)
    
    try:
        async with websockets.connect(NOTIFICATION_WS_URL) as ws:
            # Send subscription
            print(f"[WS] Subscribing to channel: {NOTIFICATION_APP_NAME} / {ACTIVE_ACCOUNT}")
            await ws.send(json.dumps(subscribe_msg))
            print("[WS] Subscription sent, waiting for confirmation...")
            
            start_time = time.time()
            
            while True:
                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    raise TimeoutError(f"Timed out after {timeout}s waiting for quote confirmation")
                
                try:
                    # Wait for message with timeout
                    remaining = timeout - elapsed
                    raw_msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 30))
                    
                    try:
                        msg = json.loads(raw_msg)
                    except json.JSONDecodeError:
                        print(f"[WS] Received non-JSON message: {raw_msg[:100]}...")
                        continue
                    
                    # Check if this is our quote confirmation
                    data = msg.get("data", {})
                    msg_temp_id = data.get("temp_quote_id")
                    msg_quote_id = data.get("quote_id")
                    action_status = data.get("action_status")
                    last_action = data.get("last_seen_action", "")
                    
                    print(f"[WS] Received: temp_id={msg_temp_id}, quote_id={msg_quote_id}, "
                          f"status={action_status}, action={last_action}")
                    
                    # Match by temp_quote_id
                    if msg_temp_id is not None:
                        try:
                            if int(msg_temp_id) == target_temp_id:
                                if action_status == "success" and msg_quote_id is not None:
                                    quote_id = int(msg_quote_id)
                                    print(f"[WS] ✓ CONFIRMED: Quote ID {quote_id}")
                                    return quote_id
                                elif action_status == "failed":
                                    raise ValueError(f"Quote failed: {data}")
                        except (TypeError, ValueError) as e:
                            if "Quote failed" in str(e):
                                raise
                            pass
                    
                except asyncio.TimeoutError:
                    print(f"[WS] Still waiting... ({int(elapsed)}s elapsed)")
                    continue
                    
    except Exception as e:
        print(f"[WS] Error: {e}")
        raise


def poll_quote_status_sync(temp_quote_id: int, timeout: int = 120) -> int:
    """Synchronous wrapper for the async WebSocket confirmation."""
    return asyncio.run(wait_for_quote_confirmation(temp_quote_id, timeout))


def set_stop_loss(token: str, quote_id: int, open_price: Decimal) -> None:
    """Set a stop loss via CONDITIONAL_ORDERS_BASE_URL.

    Payload shape matches the conditional orders service:
    {
      "account_address": "0x...",
      "quote_id": 123,
      "conditional_orders": [...],
      "symbol_id": 1,
      "multi_account_address": "0x...",
      "hedger_whitelist": ["0x..."]
    }

    For a -20% stop loss: trigger at 0.8x current price.
    """

    if not CONDITIONAL_ORDERS_BASE_URL:
        raise ValueError("CONDITIONAL_ORDERS_BASE_URL is not set in the environment")
    if not VIBE_MULTI_ACCOUNT_ADDRESS:
        raise ValueError(
            "Multi-account address is not set. Provide VIBE_MULTIACCOUNT_ADDRESS (or MULTIACCOUNT_ADDRESS)."
        )
    if not _ENV_HEDGER_WHITELIST:
        raise ValueError(
            "Hedger whitelist is not set. Provide VIBE_HEDGER_WHITELIST (or HEDGER_WHITELIST) as JSON or comma-separated."
        )

    # Parse whitelist as JSON array or comma-separated string
    hedger_whitelist: list[str]
    wl_raw = _ENV_HEDGER_WHITELIST.strip()
    if wl_raw.startswith("["):
        hedger_whitelist = json.loads(wl_raw)
    else:
        hedger_whitelist = [w.strip() for w in wl_raw.split(",") if w.strip()]
    hedger_whitelist = [Web3.to_checksum_address(w) for w in hedger_whitelist]

    # Fetch symbol precision so we format the prices correctly
    symbol_info = fetch_symbol_info(CONFIG["SYMBOL_ID"])
    price_precision = symbol_info.get("price_precision", 6)
    quantity_precision = symbol_info.get("quantity_precision", 6)

    # Use a fresh price as "current price" for the conditional order
    current_price = fetch_muon_price()
    current_price_str = format_decimal(current_price, price_precision)
    quantity_str = format_decimal(Decimal(CONFIG["QUANTITY"]), quantity_precision)

    # Calculate stop-loss trigger price for -20% move against position
    # - Long loses when price drops -> trigger below current
    # - Short loses when price rises -> trigger above current
    if int(CONFIG["POSITION_TYPE"]) == 0:
        conditional_price = current_price * Decimal("0.8")
        label = "LONG (-20% price)"
    else:
        conditional_price = current_price * Decimal("1.2")
        label = "SHORT (+20% price)"
    print(f"[STOP LOSS] {label} - Current: {current_price} -> Conditional: {conditional_price}")
    conditional_price_str = format_decimal(conditional_price, price_precision)

    # Frontend uses a trailing slash; some backends treat /api/v4 and /api/v4/ differently.
    endpoint = CONDITIONAL_ORDERS_BASE_URL.rstrip("/") + "/"
    payload = {
        "account_address": ACTIVE_ACCOUNT,
        "quote_id": int(quote_id),
        "conditional_orders": [
            {
                "quantity": quantity_str,
                "price": current_price_str,
                "conditional_price": conditional_price_str,
                "conditional_price_type": "last_close",
                "order_type": int(CONFIG["ORDER_TYPE"]),
                "position_type": int(CONFIG["POSITION_TYPE"]),
                "conditional_order_type": "stop_loss",
                "leverage": int(Decimal(CONFIG["LEVERAGE"])),
            }
        ],
        "symbol_id": int(CONFIG["SYMBOL_ID"]),
        "multi_account_address": VIBE_MULTI_ACCOUNT_ADDRESS,
        "hedger_whitelist": hedger_whitelist,
    }

    print(f"[STOP LOSS] Endpoint: {endpoint}")
    print(f"[STOP LOSS] Payload: {json.dumps(payload, indent=2)}")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "App-Name": CONDITIONAL_ORDERS_APP_NAME,
    }

    response = requests.post(endpoint, json=payload, headers=headers, timeout=30, allow_redirects=True)
    print(f"[STOP LOSS] Response Status: {response.status_code}")
    print(f"[STOP LOSS] Response: {response.text}")
    response.raise_for_status()
    print("✅ Stop Loss Set Successfully")


# --------------------------------------------------------------------
# Main
# --------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Vibe Trading Bot: Login -> Instant Open -> Stop Loss")
    print("=" * 60)
    print(f"Chain ID: {CHAIN_ID}")
    print(f"Diamond: {SYMMIO_DIAMOND_ADDRESS}")
    print(f"Solver: {SOLVER_BASE_URL}")
    print(f"Active Account: {ACTIVE_ACCOUNT}")
    print("=" * 60)

    try:
        # 1. Login
        token = login()
        print("✅ Logged in.\n")

        # 2. Open trade
        temp_quote_id, open_price, requested_open_price, requested_quantity = open_instant_trade(token)
        print(f"✅ Trade opened. Temp Quote ID: {temp_quote_id}\n")

        # 3. Wait for confirmation via WebSocket notifications
        quote_id = poll_quote_status_sync(int(temp_quote_id), timeout=120)
        print(f"✅ Quote confirmed. Quote ID: {quote_id}\n")

        # 4. Set stop loss
        set_stop_loss(token, quote_id, open_price)
        print("\n✅ All done!")

    except Exception as e:
        print(f"❌ Fatal Error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()

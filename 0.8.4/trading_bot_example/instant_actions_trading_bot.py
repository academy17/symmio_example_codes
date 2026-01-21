"""Instant Actions Demo (legacy): Login + Instant Open/Close loop

What this script does
- Logs in to a hedger/solver (SIWE) and then performs instant actions based on price checks.

Run
- python trading_bot_example/instant_actions_trading_bot.py

Required .env
- PRIVATE_KEY
- SUB_ACCOUNT_ADDRESS
- HEDGER_URL
- MUON_BASE_URL
- DIAMOND_ADDRESS

Optional .env
- CHAIN_ID (default: 42161)
"""

import os
import time
import requests
import json
from eth_account import Account
from eth_account.messages import encode_defunct
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import traceback

# Configuration
CONFIG = {
    "SYMBOL": "XRPUSDT",   # Trading pair on Binance
    "ENTRY_PRICE": "3.05",  # Price to enter the position (adjust as needed)
    "EXIT_PRICE": "3.1",   # Price to exit the position (adjust as needed)
    "QUANTITY": "6",      # Amount of XRP to trade
    "POSITION_TYPE": 0,     # 0 for long, 1 for short
    "SYMBOL_ID": 340,       # XRP symbol ID in Symmio
    "LEVERAGE": "1",        # Leverage value
    "MAX_FUNDING_RATE": "200",
    "DEADLINE_OFFSET": 3600,  # 1 hour
    "POLL_INTERVAL": 5,       # Seconds between price checks
    "STATUS_POLL_INTERVAL": 0.5  # Seconds between status checks
}

# Load environment variables
load_dotenv()

# Environment variables
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
ACTIVE_ACCOUNT = os.getenv("SUB_ACCOUNT_ADDRESS")
HEDGER_URL = os.getenv("HEDGER_URL")
CHAIN_ID = int(os.getenv("CHAIN_ID", 42161))
MUON_BASE_URL = os.getenv("MUON_BASE_URL")
DOMAIN = "localhost"
ORIGIN = "http://localhost:3000"
LOGIN_URI = f"{HEDGER_URL}/login"
DIAMOND_ADDRESS = os.getenv("DIAMOND_ADDRESS")

# URLs
BINANCE_API_URL = "https://api.binance.com/api/v3/ticker/price"
LOCKED_PARAMS_URL = f"{HEDGER_URL}/get_locked_params/XRPUSDT?leverage={CONFIG['LEVERAGE']}"
MUON_URL = f"{MUON_BASE_URL}?app=symmio&method=uPnl_A_withSymbolPrice&params[partyA]={ACTIVE_ACCOUNT}&params[chainId]={CHAIN_ID}&params[symmio]={DIAMOND_ADDRESS}&params[symbolId]={CONFIG['SYMBOL_ID']}"
STATUS_URL = f"{HEDGER_URL}/instant_open/{ACTIVE_ACCOUNT}"

# Initialize wallet
wallet = Account.from_key(PRIVATE_KEY)

# Timestamp formats
ISSUED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
EXPIRATION_DATE = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=30)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def get_nonce(address: str) -> str:
    """Fetch the nonce for the active account from the server."""
    url = f"{HEDGER_URL}/nonce/{address}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()["nonce"]

def build_siwe_message(domain, address, statement, uri, version, chain_id, nonce, issued_at, expiration_time):
    """Build a SIWE message string following the EIP-4361 format."""
    return f"""{domain} wants you to sign in with your Ethereum account:
{address}

{statement}

URI: {uri}
Version: {version}
Chain ID: {chain_id}
Nonce: {nonce}
Issued At: {issued_at}
Expiration Time: {expiration_time}"""

def login():
    """Perform SIWE login and return the access token."""
    try:
        print(f"[LOGIN] Wallet Address: {wallet.address}")
        print(f"[LOGIN] Active Account: {ACTIVE_ACCOUNT}")

        # Fetch the nonce for the active account from the server
        nonce = get_nonce(ACTIVE_ACCOUNT)
        print(f"[LOGIN] Got nonce: {nonce}")

        # Create the SIWE message manually
        message_string = build_siwe_message(
            domain=DOMAIN,
            address=wallet.address,
            statement=f"msg: {ACTIVE_ACCOUNT}",
            uri=LOGIN_URI,
            version="1",
            chain_id=CHAIN_ID,
            nonce=nonce,
            issued_at=ISSUED_AT,
            expiration_time=EXPIRATION_DATE
        )

        message = encode_defunct(text=message_string)
        
        signed_message = wallet.sign_message(message)
        signature = "0x" + signed_message.signature.hex()

        body = {
            "account_address": ACTIVE_ACCOUNT,
            "expiration_time": EXPIRATION_DATE,
            "issued_at": ISSUED_AT,
            "signature": signature,
            "nonce": nonce
        }

        headers = {
            "Content-Type": "application/json",
            "Origin": ORIGIN,
            "Referer": ORIGIN,
        }

        print("[LOGIN] Sending login request...")

        response = requests.post(
            LOGIN_URI,
            json=body,
            headers=headers
        )
        
        response.raise_for_status()
        token = response.json().get("access_token")
        print(f"[LOGIN] Successfully obtained access token")
        return token
    except Exception as e:
        print(f"[ERROR] Login failed: {e}")
        traceback.print_exc()
        return None

def get_binance_price(symbol):
    """Get the current price of a symbol from Binance."""
    try:
        params = {"symbol": symbol}
        response = requests.get(BINANCE_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        price = Decimal(data["price"])
        print(f"[PRICE] Current {symbol} price: {price}")
        return price
    except Exception as e:
        print(f"[ERROR] Failed to get Binance price: {e}")
        return None

def fetch_muon_price():
    """Fetch the current price from Muon oracle."""
    try:
        response = requests.get(MUON_URL)
        response.raise_for_status()
        data = response.json()
        fetched_price_wei = data["result"]["data"]["result"]["price"]
        if not fetched_price_wei:
            raise ValueError("Muon price not found in response.")
        return Decimal(fetched_price_wei) / Decimal('1e18')
    except Exception as e:
        print(f"[ERROR] Failed to fetch Muon price: {e}")
        return None

def fetch_locked_params():
    """Fetch locked parameters for the trade."""
    try:
        response = requests.get(LOCKED_PARAMS_URL)
        response.raise_for_status()
        data = response.json()
        if data.get("message") == "Success":
            return data
        else:
            raise ValueError("Failed to fetch locked parameters")
    except Exception as e:
        print(f"[ERROR] Failed to fetch locked parameters: {e}")
        return None

def calculate_normalized_locked_value(notional, locked_param, leverage, apply_leverage=True):
    """Compute normalized locked value for a given parameter."""
    notional = Decimal(str(notional))
    locked_param = Decimal(str(locked_param))
    leverage = Decimal(str(leverage))
    
    if apply_leverage:
        return str(notional * locked_param / (Decimal('100') * leverage))
    else:
        return str(notional * locked_param / Decimal('100'))

def open_instant_trade(token):
    """Execute an instant open trade using the access token. Returns temp_quote_id."""
    try:
        print("[TRADE] Starting instant open process...")
        
        fetched_price = fetch_muon_price()
        if not fetched_price:
            return None
        print(f"[TRADE] Fetched price: {fetched_price}")
        
        # Because in this example we are going LONG, we are increasing the price by 1% before we send the order
        adjusted_price = fetched_price * Decimal('1.01')
        print(f"[TRADE] Adjusted price (+1%): {adjusted_price}")
        
        locked_params = fetch_locked_params()
        if not locked_params:
            return None
        
        notional = adjusted_price * Decimal(CONFIG["QUANTITY"])
        print(f"[TRADE] Notional: {notional}")
        
        leverage = Decimal(locked_params["leverage"])
        normalized_cva = calculate_normalized_locked_value(notional, locked_params["cva"], leverage, True)
        normalized_lf = calculate_normalized_locked_value(notional, locked_params["lf"], leverage, True)
        normalized_party_amm = calculate_normalized_locked_value(notional, locked_params["partyAmm"], leverage, True)
        
        deadline = int(time.time()) + CONFIG["DEADLINE_OFFSET"]
        trade_params = {
            "symbolId": CONFIG["SYMBOL_ID"],
            "positionType": CONFIG["POSITION_TYPE"],
            "orderType": 1,  # 1 for market order
            "price": str(adjusted_price),
            "quantity": CONFIG["QUANTITY"],
            "cva": normalized_cva,
            "lf": normalized_lf,
            "partyAmm": normalized_party_amm,
            "partyBmm": '0',
            "maxFundingRate": CONFIG["MAX_FUNDING_RATE"],
            "deadline": deadline
        }
        
        print(f"[TRADE] Trade Payload: {trade_params}")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.post(f"{HEDGER_URL}/instant_open", json=trade_params, headers=headers)
        
        print(f"[TRADE] Response status: {response.status_code}")
        print(f"[TRADE] Response: {response.text}")
        
        response.raise_for_status()
        result = response.json()
        
        temp_quote_id = result.get("quote_id")
        if temp_quote_id:
            print(f"[TRADE] Received temporary quote ID: {temp_quote_id}")
            return temp_quote_id
        else:
            print("[ERROR] No temporary quote ID in response")
            return None
            
    except Exception as e:
        print(f"[ERROR] Failed to open instant trade: {e}")
        traceback.print_exc()
        return None

def poll_quote_status(token, temp_quote_id):
    """Poll for the status of a quote until it gets a permanent ID.""" #In order to track the status of the quote, we will poll the /instant_open/{address} endpoint
    print(f"[STATUS] Starting to poll for quote status of temp ID: {temp_quote_id}")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    max_attempts = 120  # 60 seconds (120 * 0.5s)
    attempts = 0
    
    if isinstance(temp_quote_id, str) and temp_quote_id.startswith('-'):
        try:
            temp_quote_id = int(temp_quote_id)
        except ValueError:
            print(f"[STATUS] Warning: Could not convert temp_quote_id {temp_quote_id} to int")
    
    print(f"[STATUS] Looking for temp_quote_id: {temp_quote_id} (type: {type(temp_quote_id)})")
    
    while attempts < max_attempts:
        try:
            response = requests.get(STATUS_URL, headers=headers)
            if response.status_code != 200:
                print(f"[STATUS] Error: Response status {response.status_code}")
                print(f"[STATUS] Response text: {response.text}")
                attempts += 1
                time.sleep(CONFIG["STATUS_POLL_INTERVAL"])
                continue
                
            data = response.json()
            print(f"[STATUS] Poll attempt {attempts+1}/{max_attempts}")
            
            if not data:
                print("[STATUS] Empty response, waiting for next update...")
                attempts += 1
                time.sleep(CONFIG["STATUS_POLL_INTERVAL"])
                continue
                            
            quotes = []
            if isinstance(data, list):
                quotes = data
            elif isinstance(data, dict) and "quotes" in data:
                quotes = data["quotes"]
            
            if not quotes:
                print("[STATUS] No quotes found in response")
                attempts += 1
                time.sleep(CONFIG["STATUS_POLL_INTERVAL"])
                continue
                
            print(f"[STATUS] Found {len(quotes)} quotes to check")
            
            # Look for any quote with a positive quote_id (confirmed)
            for quote in quotes:
                quote_id = quote.get("quote_id")
            
                if isinstance(quote_id, str) and quote_id.isdigit():
                    quote_id = int(quote_id)
                
                if isinstance(quote_id, int) and quote_id > 0:
                    print(f"[STATUS] ✓ CONFIRMED: Quote has permanent ID: {quote_id}")
                    return quote_id
            
            attempts += 1
            time.sleep(CONFIG["STATUS_POLL_INTERVAL"])
            
        except Exception as e:
            print(f"[ERROR] Error polling quote status: {e}")
            traceback.print_exc()
            attempts += 1
            time.sleep(CONFIG["STATUS_POLL_INTERVAL"])
    
    print("[STATUS] ⚠ Timed out waiting for permanent quote ID")
    return None

def close_instant_position(token, quote_id, current_price):
    """Close an open position."""
    try:
        print(f"[CLOSE] Preparing to close position with quote ID: {quote_id}")
        
        # Fetch Muon price and apply -1% slippage (for long positions)
        muon_price = fetch_muon_price()
        if not muon_price:
            return False
            
        close_price = str(muon_price * Decimal("0.99"))  # 1% slippage for selling
        print(f"[CLOSE] Close Price: {close_price}")
        
        payload = {
            "quote_id": quote_id,
            "quantity_to_close": CONFIG["QUANTITY"],
            "close_price": close_price
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        print("[CLOSE] Sending instant close request...")
        response = requests.post(f"{HEDGER_URL}/instant_close", json=payload, headers=headers)
        
        print(f"[CLOSE] Response status: {response.status_code}")
        print(f"[CLOSE] Response: {response.text}")
        
        response.raise_for_status()
        print("[CLOSE] Position closed successfully")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to close position: {e}")
        traceback.print_exc()
        return False

def main():
    """Main trading bot logic."""
    try:
        print("=============================================")
        print("XRP Trading Bot Starting")
        print("=============================================")
        print(f"Entry Price: {CONFIG['ENTRY_PRICE']}")
        print(f"Exit Price: {CONFIG['EXIT_PRICE']}")
        print(f"Quantity: {CONFIG['QUANTITY']}")
        print("=============================================")
        
        # Login and get access token
        access_token = login()
        if not access_token:
            print("[ERROR] Failed to login. Exiting.")
            return
        
        # Entry price as Decimal for comparison
        entry_price = Decimal(CONFIG["ENTRY_PRICE"])
        exit_price = Decimal(CONFIG["EXIT_PRICE"])
        
        # Trading state
        in_position = False
        confirmed_quote_id = None
        temp_quote_id = None
        
        print("[BOT] Starting price monitoring loop...")
        
        # Main trading loop
        while True:
            try:
                # Get current price from Binance
                current_price = get_binance_price(CONFIG["SYMBOL"])
                
                if not current_price:
                    print("[WARNING] Failed to get price, retrying...")
                    time.sleep(CONFIG["POLL_INTERVAL"])
                    continue
                
                # If not in a position and price is below entry price, enter position
                if not in_position and current_price <= entry_price:
                    print(f"[SIGNAL] Entry signal triggered at price {current_price}")
                    
                    # Execute the trade
                    temp_quote_id = open_instant_trade(access_token)
                    
                    if temp_quote_id:
                        print(f"[BOT] Trade executed with temporary quote ID: {temp_quote_id}")
                        
                        # Poll for the permanent quote ID
                        confirmed_quote_id = poll_quote_status(access_token, temp_quote_id)
                        
                        if confirmed_quote_id:
                            print(f"[BOT] Quote confirmed with ID: {confirmed_quote_id}")
                            in_position = True
                        else:
                            print("[WARNING] Failed to get confirmed quote ID. Will retry on next cycle.")
                    else:
                        print("[ERROR] Failed to execute trade")
                
                elif in_position and current_price >= exit_price:
                    print(f"[SIGNAL] Exit signal triggered at price {current_price}")
                    
                    success = close_instant_position(access_token, confirmed_quote_id, current_price)
                    
                    if success:
                        print("[BOT] Position closed successfully")
                        in_position = False
                        confirmed_quote_id = None
                        temp_quote_id = None
                        print("[BOT] Waiting for next entry opportunity...")
                    else:
                        print("[ERROR] Failed to close position. Will retry.")
                
                time.sleep(CONFIG["POLL_INTERVAL"])
                
            except Exception as e:
                print(f"[ERROR] Error in main trading loop: {e}")
                traceback.print_exc()
                time.sleep(CONFIG["POLL_INTERVAL"])
        
    except KeyboardInterrupt:
        print("\n[BOT] Trading bot stopped by user")
    except Exception as e:
        print(f"[ERROR] Unhandled exception: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
import os
import time
import requests
import json
from eth_account import Account
from eth_account.messages import encode_defunct
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
import traceback
from web3 import Web3




CONFIG = {
    "SYMBOL": "XRPUSDT",
    "QUANTITY": "7.2",      
    "POSITION_TYPE": 0,     
    "SYMBOL_ID": 4,       
    "LEVERAGE": "1",
    "MAX_FUNDING_RATE": "200",
    "DEADLINE_OFFSET": 3600,
    "STATUS_POLL_INTERVAL": 2
}


load_dotenv()


PRIVATE_KEY = os.getenv("PRIVATE_KEY")
ACTIVE_ACCOUNT = os.getenv("ACTIVE_ACCOUNT") or os.getenv("SUB_ACCOUNT_ADDRESS")
if ACTIVE_ACCOUNT:
    ACTIVE_ACCOUNT = Web3.to_checksum_address(ACTIVE_ACCOUNT)

MULTI_ACCOUNT_ADDRESS = os.getenv("MULTIACCOUNT_ADDRESS")
if MULTI_ACCOUNT_ADDRESS:
    MULTI_ACCOUNT_ADDRESS = Web3.to_checksum_address(MULTI_ACCOUNT_ADDRESS)

CHAIN_ID = int(os.getenv("CHAIN_ID", 8453)) 



ENV_HEDGER_URL = os.getenv("HEDGER_URL", "https://www.perps-streaming.com/v1/")
if ENV_HEDGER_URL.endswith("/"):
    ENV_HEDGER_URL = ENV_HEDGER_URL[:-1]

SYMM_ID = f"{CHAIN_ID}a"

HEDGER_URL = f"{ENV_HEDGER_URL}/{SYMM_ID}/{MULTI_ACCOUNT_ADDRESS}"

MUON_BASE_URL = os.getenv("MUON_BASE_URL", "https://muon-oracle1.rasa.capital/v1/")
DOMAIN = "localhost"
ORIGIN = "http://localhost:3000"
LOGIN_URI = f"{HEDGER_URL}/login"
DIAMOND_ADDRESS = os.getenv("SYMMIO_DIAMOND_ADDRESS") or os.getenv("DIAMOND_ADDRESS")
if DIAMOND_ADDRESS:
    DIAMOND_ADDRESS = Web3.to_checksum_address(DIAMOND_ADDRESS)


LOCKED_PARAMS_URL = f"{HEDGER_URL}/get_locked_params/XRPUSDT?leverage={CONFIG['LEVERAGE']}"
MUON_URL = f"{MUON_BASE_URL}?app=symmio&method=uPnl_A_withSymbolPrice&params[partyA]={ACTIVE_ACCOUNT}&params[chainId]={CHAIN_ID}&params[symmio]={DIAMOND_ADDRESS}&params[symbolId]={CONFIG['SYMBOL_ID']}"
STATUS_URL = f"{HEDGER_URL}/instant_open/{ACTIVE_ACCOUNT}"


wallet = Account.from_key(PRIVATE_KEY)


ISSUED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
EXPIRATION_DATE = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"





def get_nonce(address: str) -> str:
    url = f"{HEDGER_URL}/nonce/{address}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()["nonce"]

def build_siwe_message(domain, address, statement, uri, version, chain_id, nonce, issued_at, expiration_time):
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
    try:
        print(f"[LOGIN] Logging in as {wallet.address} for account {ACTIVE_ACCOUNT}...")
        nonce = get_nonce(ACTIVE_ACCOUNT)
        
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

        headers = {"Content-Type": "application/json", "Origin": ORIGIN, "Referer": ORIGIN}
        response = requests.post(LOGIN_URI, json=body, headers=headers)
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        print(f"[ERROR] Login failed: {e}")
        raise

def fetch_muon_price():
    try:
        response = requests.get(MUON_URL)
        response.raise_for_status()
        data = response.json()
        fetched_price_wei = data["result"]["data"]["result"]["price"]
        if not fetched_price_wei:
            raise ValueError("Muon price not found")
        
        return Decimal(fetched_price_wei) / Decimal('1e18')
    except Exception as e:
        print(f"[ERROR] Failed to fetch Muon price: {e}")
        raise

def fetch_locked_params():
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
        raise

def calculate_normalized_locked_value(notional, locked_param, leverage, apply_leverage=True):
    notional = Decimal(str(notional))
    locked_param = Decimal(str(locked_param))
    leverage = Decimal(str(leverage))
    
    if apply_leverage:
        val = notional * locked_param / (Decimal('100') * leverage)
    else:
        val = notional * locked_param / Decimal('100')
    
    
    
    s = "{:f}".format(val)
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s





def open_instant_trade(token):
    """Opens a trade and returns (temp_quote_id, open_price)."""
    print("[TRADE] Starting instant open process...")
    
    
    fetched_price = fetch_muon_price()
    print(f"[TRADE] Fetched Raw Price: {fetched_price}")
    
    
    adjusted_price = fetched_price * Decimal('1.05')
    print(f"[TRADE] Adjusted Price (+5%): {adjusted_price}")
    
    
    locked_params = fetch_locked_params()
    
    
    notional = adjusted_price * Decimal(CONFIG["QUANTITY"])
    leverage = Decimal(locked_params["leverage"])
    
    normalized_cva = calculate_normalized_locked_value(notional, locked_params["cva"], leverage, True)
    normalized_lf = calculate_normalized_locked_value(notional, locked_params["lf"], leverage, True)
    normalized_party_amm = calculate_normalized_locked_value(notional, locked_params["partyAmm"], leverage, True)
    normalized_party_bmm = calculate_normalized_locked_value(notional, locked_params["partyBmm"], leverage, False)
    
    deadline = int(time.time()) + CONFIG["DEADLINE_OFFSET"]
    
    trade_params = {
        "symbolId": CONFIG["SYMBOL_ID"],
        "positionType": CONFIG["POSITION_TYPE"],
        "orderType": 1,
        "price": str(adjusted_price),
        "quantity": CONFIG["QUANTITY"],
        "cva": normalized_cva,
        "lf": normalized_lf,
        "partyAmm": normalized_party_amm,
        "partyBmm": normalized_party_bmm,
        "maxFundingRate": CONFIG["MAX_FUNDING_RATE"],
        "deadline": deadline
    }
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    response = requests.post(f"{HEDGER_URL}/instant_open", json=trade_params, headers=headers)
    
    print(f"[TRADE] Response: {response.text}")
    response.raise_for_status()
    result = response.json()
    
    temp_quote_id = result.get("temp_quote_id") or result.get("quote_id")
    if not temp_quote_id:
        raise ValueError("No temporary quote ID in response")
        
    return temp_quote_id, fetched_price

def poll_quote_status(token, temp_quote_id):
    """Polls until a permanent quote ID is found."""
    print(f"[STATUS] Polling for confirmation of temp ID: {temp_quote_id}")
    headers = {"Authorization": f"Bearer {token}"}
    
    
    target_temp_id = str(temp_quote_id)
    
    for i in range(30): 
        try:
            response = requests.get(STATUS_URL, headers=headers)
            if response.status_code == 200:
                data = response.json()
                quotes = data if isinstance(data, list) else data.get("quotes", [])
                
                
                for quote in quotes:
                    
                    if str(quote.get("temp_quote_id")) == target_temp_id:
                        quote_id = quote.get("quote_id")
                        
                        if quote_id and int(quote_id) != -1:
                            print(f"[STATUS] ✓ CONFIRMED: Quote ID {quote_id}")
                            return int(quote_id)
            
            time.sleep(CONFIG["STATUS_POLL_INTERVAL"])
        except Exception as e:
            print(f"[STATUS] Error polling: {e}")
            time.sleep(CONFIG["STATUS_POLL_INTERVAL"])
            
    raise TimeoutError("Timed out waiting for permanent quote ID")

def set_stop_loss(token, quote_id, open_price):
    """Sets a stop loss for the given quote ID."""
    print(f"[STOP LOSS] Setting Stop Loss for Quote ID: {quote_id}...")
    
    
    
    sl_price = (open_price * Decimal('0.8')).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
    
    print(f"[STOP LOSS] Open Price: {open_price}, SL Price (0.8x): {sl_price}")
    
    payload = {
        "userAddress": wallet.address,
        "accountAddress": ACTIVE_ACCOUNT,
        "positionSide": CONFIG["POSITION_TYPE"],
        "symbolId": CONFIG["SYMBOL_ID"],
        "requestedPrice": str(open_price), 
        "quoteId": quote_id,
        "tpPrice": "", 
        "slPrice": str(sl_price),
        "timestamp": int(time.time() * 1000) 
    }
    
    print(f"[STOP LOSS] Payload: {json.dumps(payload, indent=2)}")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.post(f"{HEDGER_URL}/stop_loss", json=payload, headers=headers)
        print(f"[STOP LOSS] Response Status: {response.status_code}")
        print(f"[STOP LOSS] Response: {response.text}")
        response.raise_for_status()
        print("✅ Stop Loss Set Successfully")
    except Exception as e:
        print(f"❌ Error setting Stop Loss: {e}")





def main():
    try:
        print("=============================================")
        print("XRP Trading Bot + Stop Loss")
        print("=============================================")
        
        
        token = login()
        print("✅ Logged in.")
        
        
        temp_quote_id, open_price = open_instant_trade(token)
        print(f"✅ Trade Opened. Temp Quote ID: {temp_quote_id}")
        
        
        quote_id = poll_quote_status(token, temp_quote_id)
        
        
        set_stop_loss(token, quote_id, open_price)
        
    except Exception as e:
        print(f"❌ Fatal Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()

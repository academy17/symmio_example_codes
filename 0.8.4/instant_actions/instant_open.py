"""Instant Trading (Solver) - instant open example.

Instant trading allows the solver to open a position on behalf of the user. This is done by:


High-level flow :
- Delegation happens on-chain : the trader (partyA) authorizes a
    solver to execute specific protocol functions on their behalf.
- The trader authenticates to the solver (SIWE message + nonce) and
    receives an access token.
- The bot/frontend calls solver APIs (e.g., `instant_open`) using that token.
    The solver can then price-lock quickly and submit the on-chain transaction
    using its delegated permissions.

This script is a practical example of an instant open:
- logs in to the solver, fetches oracle price (Muon) and solver "locked params",
    computes the normalized lock values, then calls the solver's `/instant_open`
    endpoint.
"""

import os
import requests
import json
from eth_account import Account
from eth_account.messages import encode_defunct
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import time
from decimal import Decimal
import math

# Load environment variables
load_dotenv()

# Environment variables
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
ACTIVE_ACCOUNT = os.getenv("SUB_ACCOUNT_ADDRESS")
HEDGER_URL = os.getenv("HEDGER_URL")
CHAIN_ID = int(os.getenv("CHAIN_ID", 42161))  
MUON_BASE_URL = os.getenv("MUON_BASE_URL")  # Load MUON_BASE_URL from .env
DOMAIN = "localhost"
ORIGIN = "http://localhost:3000"
LOGIN_URI = f"{HEDGER_URL}/login"
DIAMOND_ADDRESS = os.getenv("DIAMOND_ADDRESS")


ISSUED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
EXPIRATION_DATE = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=30)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

# Initialize wallet
wallet = Account.from_key(PRIVATE_KEY)

# Trade Configuration - XRP
SYMBOL_ID = 340
POSITION_TYPE = 0  # 0 for long, 1 for short
ORDER_TYPE = 1  # 1 for market order
QUANTITY = "6.1"  # Amount of XRP to trade
MAX_FUNDING_RATE = "200"
DEADLINE = int(time.time()) + 3600  # Current time + 1 hour
LEVERAGE = "1"  # Leverage value

# URLs
LOCKED_PARAMS_URL = f"{HEDGER_URL}/get_locked_params/XRPUSDT?leverage={LEVERAGE}"
MUON_URL = f"{MUON_BASE_URL}?app=symmio&method=uPnl_A_withSymbolPrice&params[partyA]={ACTIVE_ACCOUNT}&params[chainId]={CHAIN_ID}&params[symmio]={DIAMOND_ADDRESS}&params[symbolId]={SYMBOL_ID}"

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
        print(f"\n[1/4] Wallet Address: {wallet.address}")
        print(f"[1.5/4] Active Account (Checksum): {ACTIVE_ACCOUNT}")

        nonce = get_nonce(ACTIVE_ACCOUNT)
        print(f"[2/4] Got nonce: {nonce}")

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
        
        print("\n[3/4] SIWE message to sign:\n", message_string)

        message = encode_defunct(text=message_string)
        
        signed_message = wallet.sign_message(message)
        signature = "0x" + signed_message.signature.hex()
        print("\nSignature:", signature)

        body = {
            "account_address": ACTIVE_ACCOUNT,
            "expiration_time": EXPIRATION_DATE,
            "issued_at": ISSUED_AT,
            "signature": signature,
            "nonce": nonce
        }

        print("body: ", body)

        headers = {
            "Content-Type": "application/json",
            "Origin": ORIGIN,
            "Referer": ORIGIN,
        }

        print("\n[4/4] Sending login request...")

        response = requests.post(
            LOGIN_URI,
            json=body,
            headers=headers
        )
        
        if response.status_code != 200:
            print(f"Server response: {response.status_code}")
            print(f"Response text: {response.text}")
            
        response.raise_for_status()
        print("Login response:", response.json())
        
        return response.json().get("access_token")
    except Exception as e:
        print(f"Error in SIWE login flow: {e}")
        import traceback
        traceback.print_exc()
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
        return fetched_price_wei
    except Exception as e:
        print(f"Error fetching Muon price: {e}")
        raise

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
        print(f"Error fetching locked parameters: {e}")
        raise

def calculate_normalized_locked_value(notional, locked_param, leverage, apply_leverage=True):
    """
    Compute normalized locked value for a given parameter.
    
    For CVA, LF, and PartyAmm: (notionalValue * lockedParam) / (100 * leverage)
    For PartyBmm: (notionalValue * partyBmm) / 100
    """
    notional = Decimal(str(notional))
    locked_param = Decimal(str(locked_param))
    leverage = Decimal(str(leverage))
    
    if apply_leverage:
        return str(notional * locked_param / (Decimal('100') * leverage))
    else:
        return str(notional * locked_param / Decimal('100'))

def open_instant_trade(token):
    """Execute an instant open trade using the access token."""
    try:
        fetched_price_wei = fetch_muon_price()
        print(f"Fetched price (wei): {fetched_price_wei}")
        
        # Because in this example we are going LONG, we are increasing the price by 1% before we send the order
        fetched_price = Decimal(fetched_price_wei) / Decimal('1e18')  # Convert from wei to human-readable
        adjusted_price = fetched_price * Decimal('1.01')  # Add 1% slippage
        print(f"Adjusted price (+1%): {adjusted_price}")
        
        locked_params = fetch_locked_params()
        print(f"Locked parameters: {locked_params}")
        
        notional = adjusted_price * Decimal(QUANTITY)
        print(f"Notional: {notional}")
        
        # Compute normalized locked values
        leverage = Decimal(locked_params["leverage"])
        normalized_cva = calculate_normalized_locked_value(notional, locked_params["cva"], leverage, True)
        normalized_lf = calculate_normalized_locked_value(notional, locked_params["lf"], leverage, True)
        normalized_party_amm = calculate_normalized_locked_value(notional, locked_params["partyAmm"], leverage, True)
        normalized_party_bmm = calculate_normalized_locked_value(notional, locked_params["partyBmm"], leverage, False)
        
        print(f"Normalized CVA: {normalized_cva}")
        print(f"Normalized LF: {normalized_lf}")
        print(f"Normalized PartyAmm: {normalized_party_amm}")
        print(f"Normalized PartyBmm: {normalized_party_bmm}")
        
        trade_params = {
            "symbolId": SYMBOL_ID,
            "positionType": POSITION_TYPE,
            "orderType": ORDER_TYPE,
            "price": str(adjusted_price),
            "quantity": QUANTITY,
            "cva": normalized_cva,
            "lf": normalized_lf,
            "partyAmm": normalized_party_amm,
            "partyBmm": '0',
            "maxFundingRate": MAX_FUNDING_RATE,
            "deadline": DEADLINE
        }
        
        print(f"Trade Payload: {trade_params}")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.post(f"{HEDGER_URL}/instant_open", json=trade_params, headers=headers)
        
        print(f"Response status: {response.status_code}")
        print(f"Instant open response: {response.text}")
        
        response.raise_for_status()
        print(f"Instant open successful: {response.json()}")
        return response.json()
        
    except Exception as e:
        print(f"Error in openInstantTrade: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Main execution flow."""
    access_token = login()
    if not access_token:
        print("Login failed. Cannot proceed with trade.")
        return
    
    print(f"\nAccess token obtained: {access_token}")
    
    print("\n----- Starting Instant Open Trade Process -----")
    result = open_instant_trade(access_token)
    
    if result:
        print("\n----- Instant Open Trade Completed Successfully -----")
    else:
        print("\n----- Instant Open Trade Failed -----")

if __name__ == "__main__":
    main()
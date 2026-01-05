"""Instant Trading (Solver) - instant close example.

Instant trading allows the solver to open a position on behalf of the user. This is done by:


- On-chain delegation (commonly via MultiAccount): the user grants the solver
    permission to call certain protocol functions on their behalf.
- Off-chain session/authentication: the user signs a SIWE login
    message (with a server-provided nonce + expiration) and receives an access
    token.

With an access token, the bot/frontend calls the solver's HTTP endpoints (e.g.
`/instant_close`). The solver uses delegated permissions to perform the fast
price-lock and submit the closing transaction on-chain.

"""

import os
import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from decimal import Decimal

load_dotenv()

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
ACTIVE_ACCOUNT = os.getenv("SUB_ACCOUNT_ADDRESS")
HEDGER_URL = os.getenv("HEDGER_URL")
MUON_BASE_URL = os.getenv("MUON_BASE_URL")
CHAIN_ID = int(os.getenv("CHAIN_ID", 42161))  
DOMAIN = "localhost"
ORIGIN = "http://localhost:3000"
LOGIN_URI = f"{HEDGER_URL}/login"
DIAMOND_ADDRESS = os.getenv("DIAMOND_ADDRESS")

ISSUED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
EXPIRATION_DATE = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

wallet = Account.from_key(PRIVATE_KEY)

SYMBOL_ID = 340  # XRP symbol ID
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
        raise

def fetch_muon_price():
    """Fetch the current price from Muon oracle and convert to decimal."""
    try:
        response = requests.get(MUON_URL)
        response.raise_for_status()
        data = response.json()
        fetched_price_wei = data["result"]["data"]["result"]["price"]
        if not fetched_price_wei:
            raise ValueError("Muon price not found in response.")
        return Decimal(fetched_price_wei) / Decimal("1e18")
    except Exception as e:
        print(f"Error fetching Muon price: {e}")
        raise

def close_instant_position(token, quote_id, quantity_to_close, close_price):
    """Call the /instant_close endpoint to close a position."""
    try:
        payload = {
            "quote_id": quote_id,
            "quantity_to_close": quantity_to_close,
            "close_price": close_price
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        response = requests.post(f"{HEDGER_URL}/instant_close", json=payload, headers=headers)
        response.raise_for_status()
        print("Instant close response:", response.json())
        return response.json()
    except Exception as e:
        print(f"Error in closeInstantPosition: {e}")
        raise

def main():
    """Main execution flow."""
    try:
        access_token = login()
        if not access_token:
            print("Login failed. Cannot proceed with trade.")
            return
        
        print(f"\nAccess token obtained: {access_token}")
        
        muon_price = fetch_muon_price()
        print(f"Fetched Muon Price (converted): {muon_price}")
        
        quote_id = 43685  # Replace with correct quote ID
        quantity_to_close = "6.1"  # Replace with the quantity to close
        close_price = str(muon_price * Decimal("0.99"))  # Apply 1% slippage for LONGS
        
        print(f"Close Price: {close_price}")
        
        print("\nSending instant close request...")
        close_response = close_instant_position(access_token, quote_id, quantity_to_close, close_price)
        print("Instant close response:", close_response)
    except Exception as e:
        print(f"Error in SIWE login flow or closing position: {e}")

if __name__ == "__main__":
    main()
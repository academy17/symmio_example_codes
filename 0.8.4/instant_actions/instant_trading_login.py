"""Instant Trading (Solver) login helper.

Instant trading allows the solver to open a position on behalf of the user. This is done by:

- Delegation: the user delegates specific functions to a solver (typically via the
    MultiAccount contract), so the solver can submit the on-chain transactions
    without the user signing every trade.
- Authentication/session: the user signs a short login message (SIWE-style,
    EIP-4361 format) and the solver issues an access token. The frontend/bot then
    uses that token when calling the solver's instant-action HTTP APIs.

"""

import os
import requests
import json
from eth_account import Account
from eth_account.messages import encode_defunct
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone


load_dotenv()


PRIVATE_KEY = os.getenv("PRIVATE_KEY")
ACTIVE_ACCOUNT = os.getenv("SUB_ACCOUNT_ADDRESS")
HEDGER_URL = os.getenv("HEDGER_URL")
CHAIN_ID = int(os.getenv("CHAIN_ID", 42161))  
DOMAIN = "localhost"
ORIGIN = "http://localhost:3000"
LOGIN_URI = f"{HEDGER_URL}/login"


ISSUED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

EXPIRATION_DATE = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=30)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


wallet = Account.from_key(PRIVATE_KEY)

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

def main():
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
    except Exception as e:
        print(f"Error in SIWE login flow: {e}")
        
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
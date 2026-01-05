from dotenv import load_dotenv
import os
import json
import requests
import time
from web3 import Web3

# Load environment variables
load_dotenv()
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
DIAMOND_ADDRESS = os.getenv("DIAMOND_ADDRESS")
CHAIN_ID = os.getenv("CHAIN_ID", "137")
MUON_BASE_URL = os.getenv("MUON_BASE_URL", "https://polygon-testnet-oracle.rasa.capital/v1/")

# Load the full Diamond ABI
abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
with open(abi_path, "r") as abi_file:
    DIAMOND_ABI = json.load(abi_file)

# Initialize Web3 and contract instance
w3 = Web3(Web3.HTTPProvider(RPC_URL))
account = w3.eth.account.from_key(PRIVATE_KEY)
diamond = w3.eth.contract(address=Web3.to_checksum_address(DIAMOND_ADDRESS), abi=DIAMOND_ABI)

# Settings for force close
QUOTE_ID = 123  # Replace with your actual quote ID
PARTY_B = "0x9206D9d8F7F1B212A4183827D20De32AF3A23c59"  # Replace with the actual party B address
SYMBOL_ID = 1  # Replace with the actual symbol ID

# Time range for price data (in seconds, Unix timestamp)
# Default to current time and 3 hours ago
current_time = int(time.time())
T0 = 1722499980  # Example: first cooldown + close request time, rounded to nearest 60
T1 = 1722510960  # Example: second cooldown before now, rounded to nearest 60


def pretty_print_price_sig(price_sig):
    req_id, timestamp, symbol_id, highest, lowest, avg_price, start_time, end_time, upnl_party_b, upnl_party_a, current_price, gateway_signature, schnorr_sign = price_sig
    signature, owner, nonce = schnorr_sign
    pretty = {
        "reqId": req_id.hex(),
        "timestamp": timestamp,
        "symbolId": symbol_id,
        "highest": highest,
        "lowest": lowest,
        "averagePrice": avg_price,
        "startTime": start_time,
        "endTime": end_time,
        "upnlPartyB": upnl_party_b,
        "upnlPartyA": upnl_party_a,
        "currentPrice": current_price,
        "gatewaySignature": gateway_signature.hex(),
        "sigs": {
            "signature": str(signature),
            "owner": owner,
            "nonce": nonce
        }
    }
    print(json.dumps(pretty, indent=2))

def fetch_price_range_signature(party_a, party_b, t0, t1, symbol_id, chain_id, symmio_address):
    """Fetch price range signature from Muon API"""
    url = (
        f"{MUON_BASE_URL}?app=symmio&method=priceRange"
        f"&params[t0]={t0}"
        f"&params[t1]={t1}"
        f"&params[partyA]={party_a}"
        f"&params[partyB]={party_b}"
        f"&params[chainId]={chain_id}"
        f"&params[symmio]={symmio_address}"
        f"&params[symbolId]={symbol_id}"
    )
    
    print(f"Fetching signature from: {url}")
    response = requests.get(url)
    
    if response.status_code != 200:
        raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
    
    result = response.json()
    
    if not result.get("success", False):
        raise Exception(f"API returned error: {result}")
    
    return result

def format_price_range_signature(result):
    """Format the API response into HighLowPriceSig structure as a tuple for web3.py"""
    req_id = result["result"]["reqId"]
    timestamp = int(result["result"]["data"]["timestamp"])
    symbol_id = int(result["result"]["data"]["result"]["symbolId"])
    highest = int(result["result"]["data"]["result"]["highest"])
    lowest = int(result["result"]["data"]["result"]["lowest"])
    avg_price = int(result["result"]["data"]["result"]["mean"])
    start_time = int(result["result"]["data"]["result"]["startTime"])
    end_time = int(result["result"]["data"]["result"]["endTime"])
    upnl_party_b = int(result["result"]["data"]["result"].get("uPnlB", "0"))
    upnl_party_a = int(result["result"]["data"]["result"].get("uPnlA", "0"))
    current_price = int(result["result"]["data"]["result"]["price"])
    gateway_signature = result["result"]["nodeSignature"]

    # SchnorrSign structure
    signature = int(result["result"]["signatures"][0]["signature"], 16)
    owner = Web3.to_checksum_address(result["result"]["signatures"][0]["owner"])
    nonce = Web3.to_checksum_address(result["result"]["data"]["init"]["nonceAddress"])

    # Convert hex strings to bytes for web3.py
    req_id_bytes = Web3.to_bytes(hexstr=req_id)
    gateway_signature_bytes = Web3.to_bytes(hexstr=gateway_signature)

    # Return as tuple for HighLowPriceSig
    schnorr_sign = (signature, owner, nonce)
    price_sig = (
        req_id_bytes, timestamp, symbol_id, highest, lowest, avg_price,
        start_time, end_time, upnl_party_b, upnl_party_a, current_price,
        gateway_signature_bytes, schnorr_sign
    )
    return price_sig

def main():
    try:
        # Use the account address as partyA
        party_a_address = account.address
        party_b_address = Web3.to_checksum_address(PARTY_B)
        symmio_address = DIAMOND_ADDRESS
        
        print(f"Fetching price range signature for:")
        print(f"- Party A: {party_a_address}")
        print(f"- Party B: {party_b_address}")
        print(f"- Time range: {T0} to {T1}")
        print(f"- Symbol ID: {SYMBOL_ID}")
        
        result = fetch_price_range_signature(
            party_a_address, party_b_address, T0, T1, 
            SYMBOL_ID, CHAIN_ID, symmio_address
        )
        
        price_sig = format_price_range_signature(result)
        print("\nFormatted price range signature:")
        pretty_print_price_sig(price_sig)
        
        # Build and send forceClosePosition transaction
        force_close_txn = diamond.functions.forceClosePosition(
            QUOTE_ID, price_sig
        ).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 500000,  # Adjust gas as needed
            "gasPrice": w3.eth.gas_price,
        })
        
        signed_txn = w3.eth.account.sign_transaction(force_close_txn, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        print(f"\nForceClosePosition transaction sent! Tx hash: {tx_hash.hex()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
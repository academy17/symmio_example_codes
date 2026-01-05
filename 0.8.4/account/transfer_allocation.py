from dotenv import load_dotenv
import os
import json
import requests
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

AMOUNT = w3.to_wei(1, "ether")  # Adjust amount as needed

# Set these as needed
ORIGIN = "0xEb42F3b1aC3b1552138C7D30E9f4e0eF43229542"  # This is partyA and the origin of the allocation
RECIPIENT = "0x66ddbC60868cdC3dFb66398d7F452B18F3695b9a"            # Replace with actual recipient address
PARTY_A = ORIGIN  # For the Muon API, partyA is the origin
RECIPIENT = Web3.to_checksum_address(RECIPIENT)
PARTY_A = Web3.to_checksum_address(PARTY_A)

def pretty_print_upnl_sig(upnl_sig):
    req_id, timestamp, upnl, gateway_signature, schnorr_sign = upnl_sig
    signature, owner, nonce = schnorr_sign
    pretty = {
        "reqId": req_id.hex(),
        "timestamp": timestamp,
        "upnl": upnl,
        "gatewaySignature": gateway_signature.hex(),
        "sigs": {
            "signature": str(signature),
            "owner": owner,
            "nonce": nonce
        }
    }
    print(json.dumps(pretty, indent=2))

def fetch_upnl_signature(party_b_address, party_a_address, chain_id, symmio_address):
    """Fetch uPnl signature for Party B from Muon API"""
    url = (
        f"{MUON_BASE_URL}?app=symmio&method=uPnl_B"
        f"&params[partyB]={party_b_address}"
        f"&params[partyA]={party_a_address}"
        f"&params[chainId]={chain_id}"
        f"&params[symmio]={symmio_address}"
    )
    print(f"Fetching signature from: {url}")
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
    result = response.json()
    if not result.get("success", False):
        raise Exception(f"API returned error: {result}")
    return result

def format_upnl_signature(result):
    """Format the API response into SingleUpnlSig structure as a tuple for web3.py"""
    req_id = result["result"]["reqId"]
    timestamp = int(result["result"]["data"]["timestamp"]) if result["result"]["data"].get("timestamp") else 0
    upnl = int(result["result"]["data"]["result"].get("uPnl", "0"))
    gateway_signature = result["result"]["nodeSignature"]

    # SchnorrSign structure
    signature = int(result["result"]["signatures"][0]["signature"], 16)
    owner = Web3.to_checksum_address(result["result"]["signatures"][0]["owner"])
    nonce = Web3.to_checksum_address(result["result"]["data"]["init"]["nonceAddress"])

    # Convert hex strings to bytes for web3.py
    req_id_bytes = Web3.to_bytes(hexstr=req_id)
    gateway_signature_bytes = Web3.to_bytes(hexstr=gateway_signature)

    # Return as tuple, not dict!
    schnorr_sign = (signature, owner, nonce)
    upnl_sig = (req_id_bytes, timestamp, upnl, gateway_signature_bytes, schnorr_sign)
    return upnl_sig

def main():
    try:
        print(f"Fetching uPnl signature for Party B: {account.address} and Party A (origin): {ORIGIN}")
        result = fetch_upnl_signature(account.address, ORIGIN, CHAIN_ID, DIAMOND_ADDRESS)
        upnl_sig = format_upnl_signature(result)
        print("Formatted uPnl signature:")
        pretty_print_upnl_sig(upnl_sig)

        # Build and send transferAllocation transaction
        txn = diamond.functions.transferAllocation(AMOUNT, ORIGIN, RECIPIENT, upnl_sig).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 300000,
            "gasPrice": w3.eth.gas_price,
        })
        signed_txn = w3.eth.account.sign_transaction(txn, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        print(f"transferAllocation transaction sent! Tx hash: {tx_hash.hex()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
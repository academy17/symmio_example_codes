from dotenv import load_dotenv
import os
import json
import requests
from web3 import Web3

# Load environment variables
load_dotenv()

# Configuration
CONFIG = {
    "rpc_url": os.getenv("RPC_URL"),
    "private_key": os.getenv("PRIVATE_KEY"),
    "diamond_address": os.getenv("DIAMOND_ADDRESS"),
    "chain_id": os.getenv("CHAIN_ID", "137"),
    "muon_base_url": os.getenv("MUON_BASE_URL", "https://polygon-testnet-oracle.rasa.capital/v1/"),
}

class LockQuoteClient:
    def __init__(self, config):
        self.config = config
        
        # Load ABI
        abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
        with open(abi_path, "r") as abi_file:
            self.abi = json.load(abi_file)
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))
        self.account = self.w3.eth.account.from_key(config["private_key"])
        self.diamond = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["diamond_address"]),
            abi=self.abi
        )
    
    def fetch_upnl_signature(self, party_b_address, party_a_address, chain_id, symmio_address):
        """Fetch uPnl signature for Party B from Muon API"""
        url = (
            f"{self.config['muon_base_url']}?app=symmio&method=uPnl_B"
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

    def format_upnl_signature(self, result):
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

        # Return as tuple
        schnorr_sign = (signature, owner, nonce)
        upnl_sig = (req_id_bytes, timestamp, upnl, gateway_signature_bytes, schnorr_sign)
        return upnl_sig

    def lock_quote(self, quote_id: int, upnl_sig):
        """Lock a quote by providing a valid Muon signature"""
        # Calculate gas price with a 1.5x buffer
        current_gas_price = self.w3.eth.gas_price
        buffered_gas_price = int(current_gas_price * 1.5)  # Increase gas price by 50%
        try:
            # Build transaction
            txn = self.diamond.functions.lockQuote(quote_id, upnl_sig).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 2000000,
                "gasPrice": buffered_gas_price,
            })
            
            # Sign and send transaction
            signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.config["private_key"])
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"Transaction sent: {tx_hash.hex()}")
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Transaction confirmed.")
            return receipt
        except Exception as e:
            print(f"Error locking quote: {e}")
            raise

def main():
    """Main function to demonstrate locking a quote"""
    client = LockQuoteClient(CONFIG)
    
    # Example: Parameters for locking a quote
    quote_id = 2217  # Replace with the actual quote ID
    party_a_address = "0x4921a5fC974d5132b4eba7F8697236fc5851a3fA"  # Replace with Party A's address
    party_b_address = client.account.address  # Party B is the sender
    chain_id = CONFIG["chain_id"]
    symmio_address = CONFIG["diamond_address"]
    
    # Fetch and format the uPnl signature
    result = client.fetch_upnl_signature(party_b_address, party_a_address, chain_id, symmio_address)
    upnl_sig = client.format_upnl_signature(result)
    
    # Lock the quote
    receipt = client.lock_quote(quote_id, upnl_sig)

if __name__ == "__main__":
    main()
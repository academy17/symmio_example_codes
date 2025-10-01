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

class ChargeFundingRateClient:
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
    
    def fetch_pair_upnl_sig(self, party_a_address, chain_id, symmio_address):
        """Fetch PairUpnlSig from Muon API"""
        url = (
            f"{self.config['muon_base_url']}?app=symmio&method=uPnl_A"
            f"&params[partyA]={party_a_address}"
            f"&params[chainId]={chain_id}"
            f"&params[symmio]={symmio_address}"
        )
        print(f"Fetching PairUpnlSig from: {url}")
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
        result = response.json()
        if not result.get("success", False):
            raise Exception(f"API returned error: {result}")
        return result

    def format_pair_upnl_sig(self, result):
        """Format the API response into PairUpnlSig structure as a tuple for web3.py"""
        req_id = result["result"]["reqId"]
        timestamp = int(result["result"]["data"]["timestamp"]) if result["result"]["data"].get("timestamp") else 0
        upnl_party_a = int(result["result"]["data"]["result"].get("uPnlA", "0"))
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
        pair_upnl_sig = (req_id_bytes, timestamp, upnl_party_a, gateway_signature_bytes, schnorr_sign)
        return pair_upnl_sig

    def charge_funding_rate(self, party_a_address: str, quote_ids: list, rates: list, pair_upnl_sig):
        """Charge funding rate for Party A"""
        try:
            # Build transaction
            txn = self.diamond.functions.chargeFundingRate(
                party_a_address,
                quote_ids,
                rates,
                pair_upnl_sig
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 300000,
                "gasPrice": self.w3.eth.gas_price,
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
            print(f"Error charging funding rate: {e}")
            raise

def main():
    """Main function to demonstrate charging funding rate"""
    client = ChargeFundingRateClient(CONFIG)
    
    # Example: Parameters for charging funding rate
    party_a_address = "0xEb42F3b1aC3b1552138C7D30E9f4e0eF43229542"  # Replace with Party A's address
    quote_ids = [1, 2, 3]  # Replace with the actual quote IDs
    rates = [100, -50, 200]  # Replace with the funding rates (in int256 format)
    chain_id = CONFIG["chain_id"]
    symmio_address = CONFIG["diamond_address"]
    
    # Fetch and format the PairUpnlSig
    result = client.fetch_pair_upnl_sig(party_a_address, chain_id, symmio_address)
    pair_upnl_sig = client.format_pair_upnl_sig(result)
    
    # Charge funding rate
    receipt = client.charge_funding_rate(party_a_address, quote_ids, rates, pair_upnl_sig)
    print(f"Charge funding rate transaction receipt: {receipt}")

if __name__ == "__main__":
    main()
from dotenv import load_dotenv
import os
import json
from web3 import Web3

# Load environment variables
load_dotenv()

# Configuration
CONFIG = {
    "rpc_url": os.getenv("RPC_URL"),
    "private_key": os.getenv("PRIVATE_KEY"),
    "diamond_address": os.getenv("DIAMOND_ADDRESS"),
}

class RequestToCancelCloseRequestClient:
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
    
    def request_to_cancel_close_request(self, quote_id: int):
        """Request to cancel a close request by its ID"""
        try:
            # Build transaction
            txn = self.diamond.functions.requestToCancelCloseRequest(quote_id).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 200000,
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
            print(f"Error requesting to cancel close request: {e}")
            raise

def main():
    """Main function to demonstrate requesting to cancel a close request"""
    client = RequestToCancelCloseRequestClient(CONFIG)
    
    # Example: Quote ID to cancel close request
    quote_id = 1  # Replace with the actual quote ID
    
    receipt = client.request_to_cancel_close_request(quote_id)
    print(f"Request to cancel close request transaction receipt: {receipt}")

if __name__ == "__main__":
    main()
from dotenv import load_dotenv
import os
import json
import time
from web3 import Web3

# Load environment variables
load_dotenv()

# Configuration
CONFIG = {
    "rpc_url": os.getenv("RPC_URL"),
    "private_key": os.getenv("PRIVATE_KEY"),
    "diamond_address": os.getenv("DIAMOND_ADDRESS"),
}

class RequestToClosePositionClient:
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
    
    def request_to_close_position(self, quote_id: int, close_price: int, quantity_to_close: int, order_type: int, deadline: int):
        """Request to close a position"""
        try:
            # Build transaction
            txn = self.diamond.functions.requestToClosePosition(
                quote_id,
                close_price,
                quantity_to_close,
                order_type,
                deadline
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
            print(f"Error requesting to close position: {e}")
            raise

def main():
    """Main function to demonstrate requesting to close a position"""
    client = RequestToClosePositionClient(CONFIG)
    
    # Example: Parameters for closing a position
    quote_id = 1  # Replace with the actual quote ID
    close_price = Web3.to_wei(2000, "ether")  # Replace with the desired close price
    quantity_to_close = Web3.to_wei(1, "ether")  # Replace with the quantity to close
    order_type = 1  # 0 for LIMIT, 1 for MARKET
    deadline = int(time.time()) + 3600  # 1 hour from now
    
    receipt = client.request_to_close_position(quote_id, close_price, quantity_to_close, order_type, deadline)
    print(f"Request to close position transaction receipt: {receipt}")

if __name__ == "__main__":
    main()
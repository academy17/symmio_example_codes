from dotenv import load_dotenv
import os
import json
from web3 import Web3

# Load environment variables
load_dotenv()

CONFIG = {
    "rpc_url": os.getenv("RPC_URL"),
    "private_key": os.getenv("PRIVATE_KEY"),
    "diamond_address": os.getenv("DIAMOND_ADDRESS"),
    "multiaccount_address": os.getenv("MULTIACCOUNT_ADDRESS"),
    "sub_account_address": os.getenv("SUB_ACCOUNT_ADDRESS"),
}

class MultiAccountRequestToCancelCloseRequestClient:
    def __init__(self, config):
        self.config = config
        
        # Load ABIs
        symmio_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "abi", "symmio.json"))
        multiaccount_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "abi", "MultiAccount.json"))
        
        with open(symmio_abi_path, "r") as abi_file:
            self.symmio_abi = json.load(abi_file)
        
        with open(multiaccount_abi_path, "r") as abi_file:
            self.multiaccount_abi = json.load(abi_file)
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))
        self.account = self.w3.eth.account.from_key(config["private_key"])
        self.diamond = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["diamond_address"]),
            abi=self.symmio_abi
        )
        self.multiaccount = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["multiaccount_address"]),
            abi=self.multiaccount_abi
        )
    
    def request_to_cancel_close_request_via_multiaccount(self, quote_id: int):
        """Request to cancel a close request via MultiAccount"""
        try:
            # Build the requestToCancelCloseRequest transaction
            request_cancel_close_txn = self.diamond.functions.requestToCancelCloseRequest(
                quote_id
            ).build_transaction({
                "from": self.account.address,
                "gas": 200000,
                "gasPrice": self.w3.eth.gas_price,
                "nonce": 0,  # This will be ignored when sending via MultiAccount
            })

            # Get the encoded function call
            encoded_request_cancel_close = request_cancel_close_txn["data"]

            # Build the MultiAccount _call transaction
            txn = self.multiaccount.functions._call(
                Web3.to_checksum_address(self.config["sub_account_address"]),
                [encoded_request_cancel_close]
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 300000,
                "gasPrice": self.w3.eth.gas_price,
            })

            # Sign and send the transaction
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
    """Main function to demonstrate requesting to cancel a close request via MultiAccount"""
    client = MultiAccountRequestToCancelCloseRequestClient(CONFIG)
    
    # Replace with the actual quote ID
    quote_id = 2221
    
    print(f"Requesting to cancel close request for quote ID: {quote_id}")
    receipt = client.request_to_cancel_close_request_via_multiaccount(quote_id)
    print(f"Request to cancel close request transaction receipt: {receipt}")

if __name__ == "__main__":
    main()
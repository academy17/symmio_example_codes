from dotenv import load_dotenv
import os
import json
import time
from web3 import Web3


load_dotenv()


CONFIG = {
    "rpc_url": os.getenv("RPC_URL"),
    "private_key": os.getenv("PRIVATE_KEY"),
    "diamond_address": os.getenv("DIAMOND_ADDRESS"),
    "multiaccount_address": os.getenv("MULTIACCOUNT_ADDRESS"),
    "sub_account_address": os.getenv("SUB_ACCOUNT_ADDRESS"),
}

class MultiAccountRequestToClosePositionClient:
    def __init__(self, config):
        self.config = config
        
        
        symmio_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "abi", "symmio.json"))
        multiaccount_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "abi", "MultiAccount.json"))
        
        with open(symmio_abi_path, "r") as abi_file:
            self.symmio_abi = json.load(abi_file)
        
        with open(multiaccount_abi_path, "r") as abi_file:
            self.multiaccount_abi = json.load(abi_file)
        
        
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
    
    def request_to_close_position_via_multiaccount(self, quote_id: int, close_price: int, quantity_to_close: int, order_type: int, deadline: int):
        """Request to close a position via MultiAccount"""
        try:
            
            close_position_txn = self.diamond.functions.requestToClosePosition(
                quote_id,
                close_price,
                quantity_to_close,
                order_type,
                deadline
            ).build_transaction({
                "from": self.account.address,
                "gas": 300000,
                "gasPrice": self.w3.eth.gas_price,
                "nonce": 0,  
            })

            
            encoded_close_position = close_position_txn["data"]

            
            txn = self.multiaccount.functions._call(
                Web3.to_checksum_address(self.config["sub_account_address"]),
                [encoded_close_position]
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 400000,
                "gasPrice": self.w3.eth.gas_price,
            })

            
            signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.config["private_key"])
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"Transaction sent: {tx_hash.hex()}")

            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Transaction confirmed.")
            return receipt
        except Exception as e:
            print(f"Error requesting to close position: {e}")
            raise

def main():
    """Main function to demonstrate requesting to close a position via MultiAccount"""
    client = MultiAccountRequestToClosePositionClient(CONFIG)
    
    
    quote_id = 2222
    close_price = Web3.to_wei(3.1, "ether")  
    quantity_to_close = Web3.to_wei(6, "ether")  
    order_type = 0 
    deadline = int(time.time()) + 3600  
    
    receipt = client.request_to_close_position_via_multiaccount(quote_id, close_price, quantity_to_close, order_type, deadline)
    print(f"Request to close position transaction receipt: {receipt}")

if __name__ == "__main__":
    main()
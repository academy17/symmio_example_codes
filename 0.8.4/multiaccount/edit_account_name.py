from dotenv import load_dotenv
import os
import json
from web3 import Web3


load_dotenv()


CONFIG = {
    "rpc_url": os.getenv("RPC_URL"),
    "private_key": os.getenv("PRIVATE_KEY"),
    "multiaccount_address": os.getenv("MULTIACCOUNT_ADDRESS"),
}

class MultiAccountClient:
    def __init__(self, config):
        self.config = config
        
        
        abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "MultiAccount.json"))
        with open(abi_path, "r") as abi_file:
            self.abi = json.load(abi_file)
        
        
        self.w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))
        self.account = self.w3.eth.account.from_key(config["private_key"])
        self.multiaccount = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["multiaccount_address"]),
            abi=self.abi
        )
    
    def edit_account_name(self, account_address: str, name: str):
        """Edit the name of an account"""
        try:
            
            txn = self.multiaccount.functions.editAccountName(
                Web3.to_checksum_address(account_address),
                name
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 300000,
                "gasPrice": self.w3.eth.gas_price,
            })
            
            
            signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.config["private_key"])
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"Transaction sent: {tx_hash.hex()}")
            
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Transaction confirmed.")
            return receipt
        except Exception as e:
            print(f"Error editing account name: {e}")
            raise

def main():
    """Main function to demonstrate editing an account name"""
    client = MultiAccountClient(CONFIG)
    
    
    sub_account_address = "0x980b2CaEF214358cF9e7566372c7c2b9D7c2Da83"  
    new_name = "updated_account_name"  
    
    receipt = client.edit_account_name(sub_account_address, new_name)

if __name__ == "__main__":
    main()
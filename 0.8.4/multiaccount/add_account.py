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
    
    def add_account(self, name: str):
        """Add a new account and retrieve its address from the emitted event"""
        try:
            txn = self.multiaccount.functions.addAccount(name).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 8000000,
                "gasPrice": self.w3.eth.gas_price,
            })
            
            signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.config["private_key"])
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"Transaction sent: {tx_hash.hex()}")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Transaction confirmed.")
            
            event_signature_hash = self.w3.keccak(text="AddAccount(address,address,string)").hex()
            for log in receipt.logs:
                if log.topics[0].hex() == event_signature_hash:
                    decoded_event = self.multiaccount.events.AddAccount().process_log(log)  
                    account_address = decoded_event["args"]["account"]
                    print(f"New account created: {account_address}")
                    return account_address
            
            print("AddAccount event not found in transaction logs.")
            return None
        except Exception as e:
            print(f"Error adding account: {e}")
            raise

def main():
    """Main function to demonstrate adding an account"""
    client = MultiAccountClient(CONFIG)
    
    # Example: Name for the new account
    account_name = "sdk_client"  # Replace with the desired account name
    
    new_account_address = client.add_account(account_name)
    if new_account_address:
        print(f"Successfully created account with address: {new_account_address}")
    else:
        print("Failed to retrieve the new account address.")

if __name__ == "__main__":
    main()
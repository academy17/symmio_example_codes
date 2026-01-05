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
        
        
        multiaccount_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "MultiAccount.json"))
        with open(multiaccount_abi_path, "r") as abi_file:
            self.multiaccount_abi = json.load(abi_file)
        
        
        self.w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))
        self.account = self.w3.eth.account.from_key(config["private_key"])
        self.multiaccount = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["multiaccount_address"]),
            abi=self.multiaccount_abi
        )
    
    def withdraw_from_account(self, account_address: str, amount: int):
        """Withdraw funds from a specific account"""
        try:
            
            txn = self.multiaccount.functions.withdrawFromAccount(
                Web3.to_checksum_address(account_address),
                amount
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 300000,
                "gasPrice": self.w3.eth.gas_price,
            })
            
            
            signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.config["private_key"])
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"Withdraw transaction sent: {tx_hash.hex()}")
            
            
            self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Withdraw transaction confirmed.")
        except Exception as e:
            print(f"Error withdrawing from account: {e}")
            raise

def main():
    """Main function to demonstrate withdrawing from an account"""
    client = MultiAccountClient(CONFIG)
    
    
    sub_account_address = "0x980b2CaEF214358cF9e7566372c7c2b9D7c2Da83"  
    withdraw_amount = Web3.to_wei(0.5, "ether")  
    
    
    print("Withdrawing from account...")
    client.withdraw_from_account(sub_account_address, withdraw_amount)

if __name__ == "__main__":
    main()
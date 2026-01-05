from dotenv import load_dotenv
import os
import json
from web3 import Web3


load_dotenv()


CONFIG = {
    "rpc_url": os.getenv("RPC_URL"),
    "private_key": os.getenv("PRIVATE_KEY"),
    "multiaccount_address": os.getenv("MULTIACCOUNT_ADDRESS"),
    "sub_account_address": os.getenv("SUB_ACCOUNT_ADDRESS"),  
}

class MultiAccountClient:
    def __init__(self, config):
        self.config = config
        
        
        abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "abi", "MultiAccount.json"))
        with open(abi_path, "r") as abi_file:
            self.abi = json.load(abi_file)
        
        
        self.w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))
        self.account = self.w3.eth.account.from_key(config["private_key"])
        self.multiaccount = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["multiaccount_address"]),
            abi=self.abi
        )
    
    def get_accounts(self, user_address: str, start: int, size: int):
        """Retrieve accounts belonging to the specified user"""
        try:
            
            accounts = self.multiaccount.functions.getAccounts(
                Web3.to_checksum_address(user_address),
                start,
                size
            ).call()
            
            
            return accounts
        except Exception as e:
            print(f"Error retrieving accounts: {e}")
            raise

def main():
    """Main function to demonstrate retrieving accounts"""
    client = MultiAccountClient(CONFIG)
    
    
    user_address = client.account.address  
    start = 0  
    size = 10  
    
    accounts = client.get_accounts(user_address, start, size)
    print(f"Retrieved accounts: {accounts}")

if __name__ == "__main__":
    main()
from dotenv import load_dotenv
import os
import json
from web3 import Web3


load_dotenv()


CONFIG = {
    "rpc_url": os.getenv("RPC_URL"),
    "private_key": os.getenv("PRIVATE_KEY"),
    "multiaccount_address": os.getenv("MULTIACCOUNT_ADDRESS"),
    "erc20_address": os.getenv("COLLATERAL_ADDRESS"),  
}

class MultiAccountClient:
    def __init__(self, config):
        self.config = config
        
        
        multiaccount_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "MultiAccount.json"))
        erc20_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "ERC20.json"))
        
        with open(multiaccount_abi_path, "r") as abi_file:
            self.multiaccount_abi = json.load(abi_file)
        
        with open(erc20_abi_path, "r") as abi_file:
            self.erc20_abi = json.load(abi_file)
        
        
        self.w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))
        self.account = self.w3.eth.account.from_key(config["private_key"])
        self.multiaccount = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["multiaccount_address"]),
            abi=self.multiaccount_abi
        )
        self.erc20 = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["erc20_address"]),
            abi=self.erc20_abi
        )
    
    def approve_erc20(self, spender_address: str, amount: int):
        """Approve the MultiAccount contract to spend ERC20 tokens"""
        try:
            
            txn = self.erc20.functions.approve(
                Web3.to_checksum_address(spender_address),
                amount
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 100000,
                "gasPrice": self.w3.eth.gas_price,
            })
            
            
            signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.config["private_key"])
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"Approval transaction sent: {tx_hash.hex()}")
            
            
            self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Approval transaction confirmed.")
        except Exception as e:
            print(f"Error approving ERC20 tokens: {e}")
            raise

    def deposit_and_allocate_for_account(self, account_address: str, amount: int):
        """Deposit and allocate funds for a specific account"""
        try:
            
            txn = self.multiaccount.functions.depositAndAllocateForAccount(
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
            print(f"Deposit and allocate transaction sent: {tx_hash.hex()}")
            
            
            self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Deposit and allocate transaction confirmed.")
        except Exception as e:
            print(f"Error depositing and allocating for account: {e}")
            raise

def main():
    """Main function to demonstrate depositing and allocating for an account"""
    client = MultiAccountClient(CONFIG)
    
    
    sub_account_address = "0x4921a5fC974d5132b4eba7F8697236fc5851a3fA"  
    deposit_amount = Web3.to_wei(100, "ether")  
    
    
    print("Approving ERC20 tokens...")
    client.approve_erc20(CONFIG["multiaccount_address"], deposit_amount)
    
    
    print("Depositing and allocating for account...")
    client.deposit_and_allocate_for_account(sub_account_address, deposit_amount)

if __name__ == "__main__":
    main()
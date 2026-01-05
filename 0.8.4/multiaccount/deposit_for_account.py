# filepath: [deposit_for_account.py](http://_vscodecontentref_/1)
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
    "multiaccount_address": os.getenv("MULTIACCOUNT_ADDRESS"),
    "erc20_address": os.getenv("COLLATERAL_ADDRESS"),  # Address of the collateral token
}

class MultiAccountClient:
    def __init__(self, config):
        self.config = config
        
        # Load ABI
        multiaccount_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "MultiAccount.json"))
        erc20_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "ERC20.json"))
        
        with open(multiaccount_abi_path, "r") as abi_file:
            self.multiaccount_abi = json.load(abi_file)
        
        with open(erc20_abi_path, "r") as abi_file:
            self.erc20_abi = json.load(abi_file)
        
        # Initialize Web3
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
            # Build transaction
            txn = self.erc20.functions.approve(
                Web3.to_checksum_address(spender_address),
                amount
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 100000,
                "gasPrice": self.w3.eth.gas_price,
            })
            
            # Sign and send transaction
            signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.config["private_key"])
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"Approval transaction sent: {tx_hash.hex()}")
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Approval transaction confirmed.")
            return receipt
        except Exception as e:
            print(f"Error approving ERC20 tokens: {e}")
            raise

    def deposit_for_account(self, account_address: str, amount: int):
        """Deposit funds for a specific account"""
        try:
            # Build transaction
            txn = self.multiaccount.functions.depositForAccount(
                Web3.to_checksum_address(account_address),
                amount
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 300000,
                "gasPrice": self.w3.eth.gas_price,
            })
            
            # Sign and send transaction
            signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.config["private_key"])
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"Deposit transaction sent: {tx_hash.hex()}")
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Deposit transaction confirmed.")
            return receipt
        except Exception as e:
            print(f"Error depositing for account: {e}")
            raise

def main():
    """Main function to demonstrate depositing for an account"""
    client = MultiAccountClient(CONFIG)
    
    # Example: Parameters for depositing funds
    sub_account_address = "0x980b2CaEF214358cF9e7566372c7c2b9D7c2Da83"  # Replace with the actual account address
    deposit_amount = Web3.to_wei(1, "ether")  # Replace with the desired deposit amount in wei
    
    # Step 1: Approve the MultiAccount contract to spend the ERC20 tokens
    print("Approving ERC20 tokens...")
    client.approve_erc20(CONFIG["multiaccount_address"], deposit_amount)
    
    # Step 2: Deposit the approved amount for the account
    print("Depositing for account...")
    receipt = client.deposit_for_account(sub_account_address, deposit_amount)

if __name__ == "__main__":
    main()
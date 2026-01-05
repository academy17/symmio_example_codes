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
        self.multiaccount = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["multiaccount_address"]),
            abi=self.abi
        )

    def get_owner(self, sub_account_address: str):
        """Read the owner of a sub-account"""
        try:
            owner = self.multiaccount.functions.owners(
                Web3.to_checksum_address(sub_account_address)
            ).call()
            return owner
        except Exception as e:
            print(f"Error reading owner: {e}")
            raise

def main():
    client = MultiAccountClient(CONFIG)
    sub_account_address = CONFIG["sub_account_address"]
    owner = client.get_owner(sub_account_address)
    print(f"Owner of sub-account {sub_account_address}: {owner}")

if __name__ == "__main__":
    main()
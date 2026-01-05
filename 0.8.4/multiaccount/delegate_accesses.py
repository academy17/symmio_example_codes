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
    "party_b_address": os.getenv("PARTY_B_ADDRESS"),
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
    
    def delegate_accesses(self, account_address: str, target_address: str, selectors: list, state: bool):
        """Batch delegate access for multiple function selectors"""
        try:
            selectors_bytes = [Web3.to_bytes(hexstr=s) for s in selectors]
            txn = self.multiaccount.functions.delegateAccesses(
                Web3.to_checksum_address(account_address),
                Web3.to_checksum_address(target_address),
                selectors_bytes,
                state
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 400000,
                "gasPrice": self.w3.eth.gas_price,
            })
            signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.config["private_key"])
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"Delegate accesses transaction sent: {tx_hash.hex()}")
            self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Delegate accesses transaction confirmed.")
        except Exception as e:
            print(f"Error delegating accesses: {e}")
            raise

def main():
    client = MultiAccountClient(CONFIG)
    sub_account_address = CONFIG["sub_account_address"]
    party_b_address = CONFIG["party_b_address"]
    selectors = [
        "0x7f2755b2",  # sendQuote
        "0x40f1310c",  # sendQuoteWithAffiliate
        "0x501e891f",  # requestToClosePosition
        "0xa63b9363", # requestToCancelCloseRequest
    ]
    state = True

    print("Batch delegating access for Instant Open and Instant Close...")
    client.delegate_accesses(sub_account_address, party_b_address, selectors, state)

if __name__ == "__main__":
    main()
from dotenv import load_dotenv
import os
import json
from web3 import Web3

load_dotenv()
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")  # Private Key must be the bridge's private key
DIAMOND_ADDRESS = os.getenv("DIAMOND_ADDRESS")

abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
with open(abi_path, "r") as abi_file:
    DIAMOND_ABI = json.load(abi_file)

w3 = Web3(Web3.HTTPProvider(RPC_URL))
account = w3.eth.account.from_key(PRIVATE_KEY)
diamond = w3.eth.contract(address=Web3.to_checksum_address(DIAMOND_ADDRESS), abi=DIAMOND_ABI)

TRANSACTION_IDS = [62, 63, 64]  # Replace with your actual transaction IDs

def main():
    try:
        txn = diamond.functions.withdrawReceivedBridgeValues(TRANSACTION_IDS).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 400000,  # Increase if needed for multiple withdrawals
            "gasPrice": w3.eth.gas_price,
        })
        signed_txn = w3.eth.account.sign_transaction(txn, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        print(f"withdrawReceivedBridgeValues transaction sent! Tx hash: {tx_hash.hex()}")
    except Exception as e:
        print(f"Error sending withdrawReceivedBridgeValues transaction: {e}")

if __name__ == "__main__":
    main()
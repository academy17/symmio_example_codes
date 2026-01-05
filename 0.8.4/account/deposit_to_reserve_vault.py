from dotenv import load_dotenv
import os
import json
from web3 import Web3

# Load environment variables
load_dotenv()
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
DIAMOND_ADDRESS = os.getenv("DIAMOND_ADDRESS")

# Load the full Diamond ABI
abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
with open(abi_path, "r") as abi_file:
    DIAMOND_ABI = json.load(abi_file)

# Initialize Web3 and contract instance
w3 = Web3(Web3.HTTPProvider(RPC_URL))
account = w3.eth.account.from_key(PRIVATE_KEY)
diamond = w3.eth.contract(address=Web3.to_checksum_address(DIAMOND_ADDRESS), abi=DIAMOND_ABI)

AMOUNT = w3.to_wei(1, "ether")  # Adjust decimals as needed
PARTY_B = "0x3B5aC601c7bB74999AB3135fa43cbDBc6aB74570"  # Replace with the target Party B address
PARTY_B = Web3.to_checksum_address(PARTY_B)

def main():
    try:
        txn = diamond.functions.depositToReserveVault(AMOUNT, PARTY_B).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 200000,
            "gasPrice": w3.eth.gas_price,
        })
        signed_txn = w3.eth.account.sign_transaction(txn, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        print(f"depositToReserveVault transaction sent! Tx hash: {tx_hash.hex()}")
    except Exception as e:
        print(f"Error sending depositToReserveVault transaction: {e}")

if __name__ == "__main__":
    main()
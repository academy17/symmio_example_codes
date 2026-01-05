from dotenv import load_dotenv
import os
import json
from web3 import Web3

# Load environment variables
load_dotenv()
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
DIAMOND_ADDRESS = os.getenv("DIAMOND_ADDRESS")
COLLATERAL_ADDRESS = "0x50E88C692B137B8a51b6017026Ef414651e0d5ba"

# Load ABIs
abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
with open(abi_path, "r") as abi_file:
    DIAMOND_ABI = json.load(abi_file)

erc20_abi = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

# Initialize Web3 and contract instances
w3 = Web3(Web3.HTTPProvider(RPC_URL))
account = w3.eth.account.from_key(PRIVATE_KEY)
diamond = w3.eth.contract(address=Web3.to_checksum_address(DIAMOND_ADDRESS), abi=DIAMOND_ABI)
erc20 = w3.eth.contract(address=Web3.to_checksum_address(COLLATERAL_ADDRESS), abi=erc20_abi)

AMOUNT = w3.to_wei(1, "ether")  # Adjust decimals as needed

def main():
    try:
        # 1. Approve
        approve_txn = erc20.functions.approve(DIAMOND_ADDRESS, AMOUNT).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 60000,
            "gasPrice": w3.eth.gas_price,
        })
        signed_approve = w3.eth.account.sign_transaction(approve_txn, private_key=PRIVATE_KEY)
        approve_tx_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
        print(f"Approve transaction sent! Tx hash: {approve_tx_hash.hex()}")
        w3.eth.wait_for_transaction_receipt(approve_tx_hash)
        print("Approve confirmed.")

        # 2. Deposit and allocate
        deposit_allocate_txn = diamond.functions.depositAndAllocate(AMOUNT).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 200000,
            "gasPrice": w3.eth.gas_price,
        })
        signed_deposit_allocate = w3.eth.account.sign_transaction(deposit_allocate_txn, private_key=PRIVATE_KEY)
        deposit_allocate_tx_hash = w3.eth.send_raw_transaction(signed_deposit_allocate.raw_transaction)
        print(f"DepositAndAllocate transaction sent! Tx hash: {deposit_allocate_tx_hash.hex()}")
    except Exception as e:
        print("Error sending transaction:", e)

if __name__ == "__main__":
    main()
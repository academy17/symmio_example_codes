from dotenv import load_dotenv
import os
import json
from web3 import Web3

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
RPC_URL = os.getenv("RPC_URL")
DIAMOND_ADDRESS = os.getenv("DIAMOND_ADDRESS")

abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "abi", "symmio.json"))
with open(abi_path, "r") as abi_file:
    ABI = json.load(abi_file)

w3 = Web3(Web3.HTTPProvider(RPC_URL))
contract = w3.eth.contract(
    address=Web3.to_checksum_address(DIAMOND_ADDRESS),
    abi=ABI
)

COLLATERAL_ADDRESS = os.getenv("COLLATERAL_ADDRESS")
COLLATERAL_ADDRESS = Web3.to_checksum_address(COLLATERAL_ADDRESS)

def main():
    try:
        balance_limit_per_user = contract.functions.getBalanceLimitPerUser(COLLATERAL_ADDRESS).call()
        print(f"Balance limit per user for collateral {COLLATERAL_ADDRESS}: {balance_limit_per_user}")
    except Exception as e:
        print("Error calling getBalanceLimitPerUser:", e)

if __name__ == "__main__":
    main()
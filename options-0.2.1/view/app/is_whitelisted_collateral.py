from dotenv import load_dotenv
import os
import json
from web3 import Web3


load_dotenv()
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


COLLATERAL_ADDRESS = "0x0000000000000000000000000000000000000000"  # Replace with actual collateral address
COLLATERAL_ADDRESS = Web3.to_checksum_address(COLLATERAL_ADDRESS)

def main():
    try:
        whitelisted_collateral = contract.functions.isWhitelistedCollateral(COLLATERAL_ADDRESS).call()
        print(f"Is whitelisted collateral {COLLATERAL_ADDRESS}: {whitelisted_collateral}")
    except Exception as e:
        print("Error calling isWhitelistedCollateral:", e)

if __name__ == "__main__":
    main()
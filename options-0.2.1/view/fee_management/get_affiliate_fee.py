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


AFFILIATE_ADDRESS = "0x0000000000000000000000000000000000000000"  # Replace with actual affiliate address
AFFILIATE_ADDRESS = Web3.to_checksum_address(AFFILIATE_ADDRESS)
SYMBOL_ID = 1  # Replace with actual symbol ID

def main():
    try:
        affiliate_fee = contract.functions.getAffiliateFee(AFFILIATE_ADDRESS, SYMBOL_ID).call()
        print(f"Affiliate fee for {AFFILIATE_ADDRESS} and symbol {SYMBOL_ID}: {affiliate_fee}")
    except Exception as e:
        print("Error calling getAffiliateFee:", e)

if __name__ == "__main__":
    main()
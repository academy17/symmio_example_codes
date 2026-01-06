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


START = 0  # Replace with actual start index
SIZE = 10  # Replace with actual size

def main():
    try:
        symbols = contract.functions.getSymbols(START, SIZE).call()
        print(f"Symbols from {START} to {START + SIZE}: {symbols}")
    except Exception as e:
        print("Error calling getSymbols:", e)

if __name__ == "__main__":
    main()
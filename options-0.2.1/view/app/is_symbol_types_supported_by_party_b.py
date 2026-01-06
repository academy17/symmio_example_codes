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


PARTY_B_ADDRESS = "0x0000000000000000000000000000000000000000"  # Replace with actual Party B address
PARTY_B_ADDRESS = Web3.to_checksum_address(PARTY_B_ADDRESS)
SYMBOL_TYPE = 1  # Replace with actual symbol type

def main():
    try:
        symbol_types_supported = contract.functions.isSymbolTypesSupportedByPartyB(PARTY_B_ADDRESS, SYMBOL_TYPE).call()
        print(f"Is symbol type {SYMBOL_TYPE} supported by Party B {PARTY_B_ADDRESS}: {symbol_types_supported}")
    except Exception as e:
        print("Error calling isSymbolTypesSupportedByPartyB:", e)

if __name__ == "__main__":
    main()
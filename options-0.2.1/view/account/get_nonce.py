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


PARTY_ADDRESS = "0xEb42F3b1aC3b1552138C7D30E9f4e0eF43229542"
PARTY_ADDRESS = Web3.to_checksum_address(PARTY_ADDRESS)
COUNTER_PARTY_ADDRESS = "0x0000000000000000000000000000000000000000"  # Replace with actual counter party address
COUNTER_PARTY_ADDRESS = Web3.to_checksum_address(COUNTER_PARTY_ADDRESS)

def main():
    try:
        nonce = contract.functions.getNonce(PARTY_ADDRESS, COUNTER_PARTY_ADDRESS).call()
        print(f"Nonce for party {PARTY_ADDRESS} and counter party {COUNTER_PARTY_ADDRESS}: {nonce}")
    except Exception as e:
        print("Error calling getNonce:", e)

if __name__ == "__main__":
    main()
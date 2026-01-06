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


INTENT_ID = 1  # Replace with actual intent ID

def main():
    try:
        party_b_open_intent_index = contract.functions.getPartyBOpenIntentIndex(INTENT_ID).call()
        print(f"Party B open intent index for intent {INTENT_ID}: {party_b_open_intent_index}")
    except Exception as e:
        print("Error calling getPartyBOpenIntentIndex:", e)

if __name__ == "__main__":
    main()
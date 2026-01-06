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


USER_ADDRESS = "0xEb42F3b1aC3b1552138C7D30E9f4e0eF43229542"
USER_ADDRESS = Web3.to_checksum_address(USER_ADDRESS)

def main():
    try:
        active_open_intents_count = contract.functions.getActiveOpenIntentsCount(USER_ADDRESS).call()
        print(f"Active open intents count for {USER_ADDRESS}: {active_open_intents_count}")
    except Exception as e:
        print("Error calling getActiveOpenIntentsCount:", e)

if __name__ == "__main__":
    main()
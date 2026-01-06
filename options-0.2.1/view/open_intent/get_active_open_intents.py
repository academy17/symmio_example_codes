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
START = 0  # Replace with actual start index
SIZE = 10  # Replace with actual size

def main():
    try:
        active_open_intents = contract.functions.getActiveOpenIntents(USER_ADDRESS, START, SIZE).call()
        print(f"Active open intents for {USER_ADDRESS} from {START} to {START + SIZE}: {active_open_intents}")
    except Exception as e:
        print("Error calling getActiveOpenIntents:", e)

if __name__ == "__main__":
    main()
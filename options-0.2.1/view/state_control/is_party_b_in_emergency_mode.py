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

def main():
    try:
        party_b_in_emergency_mode = contract.functions.isPartyBInEmergencyMode(PARTY_B_ADDRESS).call()
        print(f"Is Party B {PARTY_B_ADDRESS} in emergency mode: {party_b_in_emergency_mode}")
    except Exception as e:
        print("Error calling isPartyBInEmergencyMode:", e)

if __name__ == "__main__":
    main()
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


PARTY_B = "0x1EcAbF0Eba136920677C9575FAccee36f30592cf"  
PARTY_B = Web3.to_checksum_address(PARTY_B)

def main():
    try:
        balance = contract.functions.balanceOfReserveVault(PARTY_B).call()
        print(f"Reserve vault balance for Party B {PARTY_B}: {balance}")
    except Exception as e:
        print("Error calling balanceOfReserveVault:", e)

if __name__ == "__main__":
    main()
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


PARTY_A = "0xEb42F3b1aC3b1552138C7D30E9f4e0eF43229542"
PARTY_A = Web3.to_checksum_address(PARTY_A)


LIQUIDATION_DETAIL_FIELDS = [
    "liquidationId",
    "liquidationType",
    "upnl",
    "totalUnrealizedLoss",
    "deficit",
    "liquidationFee",
    "timestamp",
    "involvedPartyBCounts",
    "partyAAccumulatedUpnl",
    "disputed",
    "liquidationTimestamp"
]

def main():
    try:
        detail = contract.functions.getLiquidatedStateOfPartyA(PARTY_A).call()
        if isinstance(detail, (list, tuple)):
            detail_dict = dict(zip(LIQUIDATION_DETAIL_FIELDS, detail))
            print(json.dumps(detail_dict, indent=2, default=str))
        else:
            print(detail)
    except Exception as e:
        print("Error calling getLiquidatedStateOfPartyA:", e)

if __name__ == "__main__":
    main()
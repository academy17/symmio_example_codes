from dotenv import load_dotenv
import os
import json
from web3 import Web3

# Load environment variables
load_dotenv()
RPC_URL = os.getenv("RPC_URL")
DIAMOND_ADDRESS = os.getenv("DIAMOND_ADDRESS")

# Load the full Diamond ABI
abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "abi", "symmio.json"))
with open(abi_path, "r") as abi_file:
    ABI = json.load(abi_file)

# Initialize Web3 and contract instance
w3 = Web3(Web3.HTTPProvider(RPC_URL))
contract = w3.eth.contract(
    address=Web3.to_checksum_address(DIAMOND_ADDRESS),
    abi=ABI
)

MUON_IDS_FIELDS = [
    "muonAppId",
    "muonPublicKey",
    "validGateway"
]

PUBLIC_KEY_FIELDS = [
    "x",
    "parity"
]

def main():
    try:
        muon_ids = contract.functions.getMuonIds().call()
        muon_ids_dict = dict(zip(MUON_IDS_FIELDS, muon_ids))
        # Pretty print muonPublicKey as a dict with field names
        if isinstance(muon_ids_dict["muonPublicKey"], (list, tuple)):
            muon_ids_dict["muonPublicKey"] = dict(zip(PUBLIC_KEY_FIELDS, muon_ids_dict["muonPublicKey"]))
        print(json.dumps(muon_ids_dict, indent=2, default=str))
    except Exception as e:
        print("Error calling getMuonIds:", e)

if __name__ == "__main__":
    main()
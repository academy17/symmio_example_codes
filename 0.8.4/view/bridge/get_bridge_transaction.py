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


TRANSACTION_ID = 137


BRIDGE_TX_FIELDS = [
    "transactionId",
    "from",
    "to",
    "amount",
    "timestamp",
    "status"
    
]

def main():
    try:
        bridge_tx = contract.functions.getBridgeTransaction(TRANSACTION_ID).call()
        if isinstance(bridge_tx, (list, tuple)):
            bridge_tx_dict = dict(zip(BRIDGE_TX_FIELDS, bridge_tx))
            print(json.dumps(bridge_tx_dict, indent=2, default=str))
        else:
            print(bridge_tx)
    except Exception as e:
        print("Error calling getBridgeTransaction:", e)

if __name__ == "__main__":
    main()
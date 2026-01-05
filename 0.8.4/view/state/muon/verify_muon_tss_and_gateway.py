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

# Example data (replace with actual values)
HASH = "0x..."  # bytes32 hash
SCHNORR_SIGN = (
    123456789,  # uint256 signature
    987654321,  # uint256 pubKeyX
    1           # uint8 pubKeyParity
)
GATEWAY_SIGNATURE = b"\x00\x01..."  # bytes

def main():
    try:
        # This function is view and does not return anything, so just call it
        contract.functions.verifyMuonTSSAndGateway(HASH, SCHNORR_SIGN, GATEWAY_SIGNATURE).call()
        print("verifyMuonTSSAndGateway call succeeded (no return value)")
    except Exception as e:
        print("Error calling verifyMuonTSSAndGateway:", e)

if __name__ == "__main__":
    main()
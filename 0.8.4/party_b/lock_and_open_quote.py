from dotenv import load_dotenv
import os
import json
import requests
from web3 import Web3

# Load environment variables
load_dotenv()

# Configuration
CONFIG = {
    "rpc_url": os.getenv("RPC_URL"),
    "private_key": os.getenv("PRIVATE_KEY"),
    "diamond_address": os.getenv("DIAMOND_ADDRESS"),
    "sub_account_address": os.getenv("SUB_ACCOUNT_ADDRESS"),  # This is Party A (the counterparty)
    "chain_id": os.getenv("CHAIN_ID", "137"),
    "muon_base_url": os.getenv("MUON_BASE_URL", "https://polygon-testnet-oracle.rasa.capital/v1/"),
    "symbol_id": 4,  # Replace with the actual symbol ID
}

class LockAndOpenQuoteClient:
    def __init__(self, config):
        self.config = config
        
        # Load ABI
        symmio_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
        
        with open(symmio_abi_path, "r") as abi_file:
            self.symmio_abi = json.load(abi_file)
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))
        self.account = self.w3.eth.account.from_key(config["private_key"])
        self.diamond = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["diamond_address"]),
            abi=self.symmio_abi
        )
    
    def fetch_upnl_signature(self, party_b_address, party_a_address, chain_id, symmio_address):
        """Fetch SingleUpnlSig from Muon API"""
        url = (
            f"{self.config['muon_base_url']}?app=symmio&method=uPnl_B"
            f"&params[partyB]={party_b_address}"
            f"&params[partyA]={party_a_address}"
            f"&params[chainId]={chain_id}"
            f"&params[symmio]={symmio_address}"
        )
        print(f"Fetching SingleUpnlSig from: {url}")
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
        result = response.json()
        if not result.get("success", False):
            raise Exception(f"API returned error: {result}")
        return result

    def format_upnl_signature(self, result):
        """Format the API response into SingleUpnlSig structure as a tuple for web3.py"""
        req_id = result["result"]["reqId"]
        timestamp = int(result["result"]["data"]["timestamp"]) if result["result"]["data"].get("timestamp") else 0
        upnl = int(result["result"]["data"]["result"].get("uPnl", "0"))
        gateway_signature = result["result"]["nodeSignature"]

        # SchnorrSign structure
        signature = int(result["result"]["signatures"][0]["signature"], 16)
        owner = Web3.to_checksum_address(result["result"]["signatures"][0]["owner"])
        nonce = Web3.to_checksum_address(result["result"]["data"]["init"]["nonceAddress"])

        # Convert hex strings to bytes for web3.py
        req_id_bytes = Web3.to_bytes(hexstr=req_id)
        gateway_signature_bytes = Web3.to_bytes(hexstr=gateway_signature)

        # CRITICAL: Format exactly like JS implementation
        upnl_sig = {
            "reqId": req_id_bytes,
            "timestamp": timestamp,
            "upnl": upnl,
            "gatewaySignature": gateway_signature_bytes,
            "sigs": {
                "signature": signature,
                "owner": owner,
                "nonce": nonce
            }
        }
        
        return upnl_sig

    def fetch_pair_upnl_and_price_sig(self, party_b_address, party_a_address, chain_id, symbol_id, symmio_address):
        """Fetch PairUpnlAndPriceSig from Muon API"""
        url = (
            f"{self.config['muon_base_url']}?app=symmio&method=uPnlWithSymbolPrice"
            f"&params[partyB]={party_b_address}"
            f"&params[partyA]={party_a_address}"
            f"&params[chainId]={chain_id}"
            f"&params[symbolId]={symbol_id}"
            f"&params[symmio]={symmio_address}"
        )
        print(f"Fetching PairUpnlAndPriceSig from: {url}")
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
        result = response.json()
        if not result.get("success", False):
            raise Exception(f"API returned error: {result}")
        return result

    def format_pair_upnl_and_price_sig(self, result):
        """Format the API response into PairUpnlAndPriceSig structure as a tuple for web3.py"""
        req_id = result["result"]["reqId"]
        timestamp = int(result["result"]["data"]["timestamp"]) if result["result"]["data"].get("timestamp") else 0
        upnl_party_a = int(result["result"]["data"]["result"].get("uPnlA", "0"))
        upnl_party_b = int(result["result"]["data"]["result"].get("uPnlB", "0"))
        price = int(result["result"]["data"]["result"].get("price", "0"))
        gateway_signature = result["result"]["nodeSignature"]

        # SchnorrSign structure
        signature = int(result["result"]["signatures"][0]["signature"], 16)
        owner = Web3.to_checksum_address(result["result"]["signatures"][0]["owner"])
        nonce = Web3.to_checksum_address(result["result"]["data"]["init"]["nonceAddress"])

        # Convert hex strings to bytes for web3.py
        req_id_bytes = Web3.to_bytes(hexstr=req_id)
        gateway_signature_bytes = Web3.to_bytes(hexstr=gateway_signature)

        # CRITICAL: Format exactly like JS implementation
        pair_upnl_sig = {
            "reqId": req_id_bytes,
            "timestamp": timestamp,
            "upnlPartyA": upnl_party_a,
            "upnlPartyB": upnl_party_b,
            "price": price,
            "gatewaySignature": gateway_signature_bytes,
            "sigs": {
                "signature": signature,
                "owner": owner,
                "nonce": nonce
            }
        }
        
        return pair_upnl_sig

    def lock_and_open_quote(self, quote_id: int, filled_amount: int, opened_price: int, upnl_sig, pair_upnl_sig):
        """Lock and open a quote directly (Party B operation)"""
        try:
            # Build transaction to call lockAndOpenQuote directly on the diamond contract
            txn = self.diamond.functions.lockAndOpenQuote(
                quote_id,
                filled_amount,
                opened_price,
                upnl_sig,
                pair_upnl_sig
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 800000,  # Increased gas limit for this complex transaction
                "gasPrice": self.w3.eth.gas_price,
            })

            # Sign and send the transaction
            signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.config["private_key"])
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"Transaction sent: {tx_hash.hex()}")

            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Transaction confirmed.")
            return receipt
        except Exception as e:
            print(f"Error locking and opening quote: {e}")
            raise

def main():
    """Main function to demonstrate locking and opening a quote"""
    client = LockAndOpenQuoteClient(CONFIG)
    
    # Example: Parameters for locking and opening a quote
    quote_id = 2223  # Replace with the actual quote ID
    filled_amount = Web3.to_wei(6, "ether")  # Replace with the filled amount
    opened_price = Web3.to_wei(3.1, "ether")  # Replace with the opened price
    
    # Party A is the sub-account (counterparty)
    party_a_address = client.config["sub_account_address"]
    # Party B is the sender (us)
    party_b_address = client.account.address
    chain_id = CONFIG["chain_id"]
    symmio_address = CONFIG["diamond_address"]
    symbol_id = CONFIG["symbol_id"]
    
    # Fetch and format the SingleUpnlSig
    print(f"Fetching SingleUpnlSig for PartyB: {party_b_address}, PartyA: {party_a_address}")
    single_upnl_result = client.fetch_upnl_signature(party_b_address, party_a_address, chain_id, symmio_address)
    upnl_sig = client.format_upnl_signature(single_upnl_result)
    print(f"SingleUpnlSig formatted successfully")
    
    # Fetch and format the PairUpnlAndPriceSig
    print(f"Fetching PairUpnlAndPriceSig with SymbolID: {symbol_id}")
    pair_upnl_result = client.fetch_pair_upnl_and_price_sig(party_b_address, party_a_address, chain_id, symbol_id, symmio_address)
    pair_upnl_sig = client.format_pair_upnl_and_price_sig(pair_upnl_result)
    print(f"PairUpnlAndPriceSig formatted successfully")
    
    # Lock and open the quote
    print(f"Locking and opening quote ID: {quote_id}")
    receipt = client.lock_and_open_quote(quote_id, filled_amount, opened_price, upnl_sig, pair_upnl_sig)
    print(f"Lock and open quote transaction receipt: {receipt}")

if __name__ == "__main__":
    main()
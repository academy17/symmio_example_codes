from dotenv import load_dotenv
import os
import json
import requests
import time
from web3 import Web3
from typing import Dict, Any, List, Tuple

# Load environment variables
load_dotenv()

CONFIG = {
    "rpc_url": os.getenv("RPC_URL"),
    "private_key": os.getenv("PRIVATE_KEY"),
    "diamond_address": os.getenv("DIAMOND_ADDRESS"),
    "multiaccount_address": os.getenv("MULTIACCOUNT_ADDRESS"),
    "sub_account_address": os.getenv("SUB_ACCOUNT_ADDRESS"),
    "chain_id": os.getenv("CHAIN_ID", "137"),
    "muon_base_url": os.getenv("MUON_BASE_URL", "https://polygon-testnet-oracle.rasa.capital/v1/"),
}

class MultiAccountForceClosePositionClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Load ABIs
        symmio_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "abi", "symmio.json"))
        multiaccount_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "abi", "MultiAccount.json"))
        
        with open(symmio_abi_path, "r") as abi_file:
            self.symmio_abi = json.load(abi_file)
        
        with open(multiaccount_abi_path, "r") as abi_file:
            self.multiaccount_abi = json.load(abi_file)
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))
        self.account = self.w3.eth.account.from_key(config["private_key"])
        self.diamond = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["diamond_address"]),
            abi=self.symmio_abi
        )
        self.multiaccount = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["multiaccount_address"]),
            abi=self.multiaccount_abi
        )
    
    def get_force_close_cooldowns(self) -> Tuple[int, int]:
        """Get force close cooldown periods from the contract"""
        return self.diamond.functions.forceCloseCooldowns().call()
    
    def get_quote_details(self, quote_id: int) -> Dict[str, Any]:
        """Get quote details from the contract"""
        quote = self.diamond.functions.getQuote(quote_id).call()
        print(f"Fetched quote details: {quote}")  # Debug log
        
        # Access fields using tuple indices
        return {
            "symbolId": int(quote[2]),  # symbolId is at index 2
            "positionType": int(quote[3]),  # positionType is at index 3
            "orderType": int(quote[4]),  # orderType is at index 4
            "quoteStatus": int(quote[16]),  # quoteStatus is at index 16
            "statusModifyTimestamp": int(quote[22]),  # statusModifyTimestamp is at index 22
            "requestedClosePrice": int(quote[18]),  # requestedClosePrice is at index 18 (was 17)
            "partyB": Web3.to_checksum_address(quote[15]),  # partyB is at index 15
            "deadline": int(quote[24]),  # deadline is at index 24 (was 23)
        }
    
    def calculate_time_range(self, quote_id: int) -> Tuple[int, int]:
        """Calculate appropriate startTime and endTime for the price range signature"""
        quote = self.get_quote_details(quote_id)
        
        # Get force close cooldown periods
        force_close_first_cooldown, force_close_second_cooldown = self.get_force_close_cooldowns()
        
        # Calculate startTime: must be >= statusModifyTimestamp + forceCloseFirstCooldown
        start_time = quote["statusModifyTimestamp"] + force_close_first_cooldown
        
        # Calculate endTime: must be <= min(quote.deadline, block.timestamp - forceCloseSecondCooldown)
        current_time = int(time.time())
        end_time = min(
            quote["deadline"],
            current_time - force_close_second_cooldown
        )
        
        # Debugging: Print values
        print(f"statusModifyTimestamp: {quote['statusModifyTimestamp']}")
        print(f"forceCloseFirstCooldown: {force_close_first_cooldown}")
        print(f"forceCloseSecondCooldown: {force_close_second_cooldown}")
        print(f"current_time: {current_time}")
        print(f"deadline: {quote['deadline']}")
        print(f"Calculated start_time: {start_time}")
        print(f"Calculated end_time: {end_time}")
        
        # Ensure startTime and endTime are valid
        if end_time <= start_time:
            raise ValueError("Invalid time range: endTime must be greater than startTime")
        
        # Round startTime up to the nearest minute
        start_time = ((start_time + 59) // 60) * 60
        # Round endTime down to the nearest minute
        end_time = (end_time // 60) * 60
        
        print(f"Rounded start_time: {start_time}")
        print(f"Rounded end_time: {end_time}")
        return start_time, end_time
    
    def fetch_price_range_signature(self, quote_id: int) -> Dict[str, Any]:
        """Fetch price range signature from Muon API"""
        quote = self.get_quote_details(quote_id)
        start_time, end_time = self.calculate_time_range(quote_id)
        
        party_a = self.config["sub_account_address"]
        party_b = quote["partyB"]
        symbol_id = quote["symbolId"]
        
        url = (
            f"{self.config['muon_base_url']}?app=symmio&method=priceRange"
            f"&params[t0]={start_time}"
            f"&params[t1]={end_time}"
            f"&params[partyA]={party_a}"
            f"&params[partyB]={party_b}"
            f"&params[chainId]={self.config['chain_id']}"
            f"&params[symmio]={self.config['diamond_address']}"
            f"&params[symbolId]={symbol_id}"
        )
        
        print(f"Fetching price range signature from: {url}")
        response = requests.get(url)
        
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
        
        result = response.json()
        
        if not result.get("success", False):
            raise Exception(f"API returned error: {result}")
        
        return result
    
    def format_price_range_signature(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Format the API response into HighLowPriceSig structure as a dictionary for web3.py"""
        req_id = result["result"]["reqId"]
        timestamp = int(result["result"]["data"]["timestamp"])
        symbol_id = int(result["result"]["data"]["result"]["symbolId"])
        highest = int(result["result"]["data"]["result"]["highest"])
        lowest = int(result["result"]["data"]["result"]["lowest"])
        avg_price = int(result["result"]["data"]["result"]["mean"])
        start_time = int(result["result"]["data"]["result"]["startTime"])
        end_time = int(result["result"]["data"]["result"]["endTime"])
        upnl_party_b = int(result["result"]["data"]["result"].get("uPnlB", "0"))
        upnl_party_a = int(result["result"]["data"]["result"].get("uPnlA", "0"))
        current_price = int(result["result"]["data"]["result"]["price"])
        gateway_signature = result["result"]["nodeSignature"]

        # SchnorrSign structure
        signature = int(result["result"]["signatures"][0]["signature"], 16)
        owner = Web3.to_checksum_address(result["result"]["signatures"][0]["owner"])
        nonce = Web3.to_checksum_address(result["result"]["data"]["init"]["nonceAddress"])

        # Convert hex strings to bytes for web3.py
        req_id_bytes = Web3.to_bytes(hexstr=req_id)
        gateway_signature_bytes = Web3.to_bytes(hexstr=gateway_signature)

        # Format as dictionary matching the HighLowPriceSig structure
        price_sig = {
            "reqId": req_id_bytes,
            "timestamp": timestamp,
            "symbolId": symbol_id,
            "highest": highest,
            "lowest": lowest,
            "averagePrice": avg_price,
            "startTime": start_time,
            "endTime": end_time,
            "upnlPartyB": upnl_party_b,
            "upnlPartyA": upnl_party_a,
            "currentPrice": current_price,
            "gatewaySignature": gateway_signature_bytes,
            "sigs": {
                "signature": signature,
                "owner": owner,
                "nonce": nonce
            }
        }
        
        return price_sig
    
    def force_close_position_via_multiaccount(self, quote_id: int) -> Dict[str, Any]:
        """Force close a position via MultiAccount"""
        try:
            # Get the price range signature
            price_range_result = self.fetch_price_range_signature(quote_id)
            price_sig = self.format_price_range_signature(price_range_result)
            
            # Combine price_sig and settlement_sig into the expected format
            # Here we're building a combined signature object based on the ABI's expected structure
            combined_sig = {
                "reqId": price_sig["reqId"],
                "timestamp": price_sig["timestamp"],
                "symbolId": price_sig["symbolId"],
                "highest": price_sig["highest"],
                "lowest": price_sig["lowest"],
                "averagePrice": price_sig["averagePrice"],
                "startTime": price_sig["startTime"],
                "endTime": price_sig["endTime"],
                "upnlPartyB": price_sig["upnlPartyB"],
                "upnlPartyA": price_sig["upnlPartyA"],
                "currentPrice": price_sig["currentPrice"],
                "gatewaySignature": price_sig["gatewaySignature"],
                "sigs": price_sig["sigs"]
            }
            
            # Build the forceClosePosition transaction with just 2 arguments
            force_close_txn = self.diamond.functions.forceClosePosition(
                quote_id,
                combined_sig  # Just the combined signature structure
            ).build_transaction({
                "from": self.account.address,
                "gas": 2000000,
                "gasPrice": int(self.w3.eth.gas_price * 1.5),
                "nonce": 0,  # This will be ignored when sending via MultiAccount
            })
            
            # Get the encoded function call
            encoded_force_close = force_close_txn["data"]
            
            # Build the MultiAccount _call transaction
            txn = self.multiaccount.functions._call(
                Web3.to_checksum_address(self.config["sub_account_address"]),
                [encoded_force_close]
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 3000000,  # Higher gas limit for complex transaction
                "gasPrice": int(self.w3.eth.gas_price * 1.5),  # Increase gas price by 50%
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
            print(f"Error forcing to close position: {e}")
            raise

def main():
    """Main function to demonstrate forcing to close a position via MultiAccount"""
    client = MultiAccountForceClosePositionClient(CONFIG)
    
    # Replace with the actual quote ID
    quote_id = 2220
    
    print(f"Force closing position for quote ID: {quote_id}")
    receipt = client.force_close_position_via_multiaccount(quote_id)
    print(f"Force close position transaction receipt: {receipt}")

if __name__ == "__main__":
    main()
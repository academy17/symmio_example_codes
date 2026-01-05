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

class MultiAccountSettleAndForceClosePositionClient:
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
            "requestedClosePrice": int(quote[18]),  # requestedClosePrice is at index 18
            "partyB": Web3.to_checksum_address(quote[15]),  # partyB is at index 15
            "deadline": int(quote[24]),  # deadline is at index 24
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
    
    def get_updated_prices(self, result: Dict[str, Any], quotes_settlements_data: List[Tuple[int, int, int]]) -> List[int]:
        """Extract updated prices from the price range API response and match them to quotesSettlementsData"""
        if "pricesA" in result["result"]["data"]["result"]:
            # Convert all prices to integers
            all_prices = [int(price) for price in result["result"]["data"]["result"]["pricesA"]]
            
            # Match prices to quotesSettlementsData
            if len(all_prices) >= len(quotes_settlements_data):
                return all_prices[:len(quotes_settlements_data)]
        
        return []  # Return empty array if no prices are available


    
    def fetch_settlement_signature(self, quote_id: int) -> Dict[str, Any]:
        """Fetch settlement signature from Muon API"""
        party_a = self.config["sub_account_address"]
        
        url = (
            f"{self.config['muon_base_url']}?app=symmio&method=settle_upnl"
            f"&params[partyA]={party_a}"
            f"&params[chainId]={self.config['chain_id']}"
            f"&params[symmio]={self.config['diamond_address']}"
            f"&params[quoteIds]=[{quote_id}]"
        )
        
        print(f"Fetching settlement signature from: {url}")
        response = requests.get(url)
        
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
        
        result = response.json()
        
        if not result.get("success", False):
            raise Exception(f"API returned error: {result}")
        
        return result
        
    def format_settlement_signature(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Format the API response into SettlementSig structure as a dictionary for web3.py"""
        req_id = result["result"]["reqId"]
        timestamp = int(result["result"]["data"]["timestamp"])
        gateway_signature = result["result"]["nodeSignature"]
        
        # Get quoteSettlementData and format it properly as tuples
        quotes_settlements_data = []
        if "quoteSettlementData" in result["result"]["data"]["result"]:
            raw_settlement_data = result["result"]["data"]["result"]["quoteSettlementData"]
            for data in raw_settlement_data:
                if isinstance(data, list) and len(data) >= 2:
                    quote_settlement = (
                        int(data[0]),  # quoteId
                        int(data[1]),  # price
                        int(data[2]) if len(data) > 2 else 0  # quantity
                    )
                    quotes_settlements_data.append(quote_settlement)
        
        # Get upnlPartyBs
        upnl_party_bs = []
        if "upnlPartyBs" in result["result"]["data"]["result"]:
            upnl_party_bs = [int(upnl) for upnl in result["result"]["data"]["result"]["upnlPartyBs"]]
        
        # Get uPnlA
        upnl_party_a = 0
        if "uPnlA" in result["result"]["data"]["result"]:
            upnl_party_a = int(result["result"]["data"]["result"]["uPnlA"])
        
        # SchnorrSign structure - this is critical for verification
        signature = int(result["result"]["signatures"][0]["signature"], 16)
        owner = Web3.to_checksum_address(result["result"]["signatures"][0]["owner"])
        nonce = Web3.to_checksum_address(result["result"]["data"]["init"]["nonceAddress"])

        # Convert hex strings to bytes for web3.py
        req_id_bytes = Web3.to_bytes(hexstr=req_id)
        gateway_signature_bytes = Web3.to_bytes(hexstr=gateway_signature)

        # Debug print
        print(f"Signature format: {signature}, {owner}, {nonce}")
        print(f"Settlement data format: Quotes={quotes_settlements_data}, upnlPartyBs={upnl_party_bs}")

        # Format as dictionary matching the SettlementSig structure
        settlement_sig = {
            "reqId": req_id_bytes,
            "timestamp": timestamp,
            "quotesSettlementsData": quotes_settlements_data,
            "upnlPartyBs": upnl_party_bs,
            "upnlPartyA": upnl_party_a,
            "gatewaySignature": gateway_signature_bytes,
            "sigs": {
                "signature": signature,
                "owner": owner,
                "nonce": nonce
            }
        }
        
        return settlement_sig
    
    def settle_and_force_close_position_via_multiaccount(self, quote_id: int) -> Dict[str, Any]:
        """Settle and force close a position via MultiAccount"""
        try:
            # Get the price range signature
            price_range_result = self.fetch_price_range_signature(quote_id)
            price_sig = self.format_price_range_signature(price_range_result)
            
            # Get the settlement signature
            settlement_result = self.fetch_settlement_signature(quote_id)
            settlement_sig = self.format_settlement_signature(settlement_result)
            
            # Get the updated prices, ensuring they match quotesSettlementsData
            updated_prices = self.get_updated_prices(price_range_result, settlement_sig["quotesSettlementsData"])
            
            # Debugging: Print lengths
            print(f"Length of quotesSettlementsData: {len(settlement_sig['quotesSettlementsData'])}")
            print(f"Length of updatedPrices: {len(updated_prices)}")
            
            # Build the settleAndForceClosePosition transaction
            settle_force_close_txn = self.diamond.functions.settleAndForceClosePosition(
                quote_id,
                price_sig,
                settlement_sig,
                updated_prices
            ).build_transaction({
                "from": self.account.address,
                "gas": 2000000,
                "gasPrice": int(self.w3.eth.gas_price * 1.5),
                "nonce": 0,  # This will be ignored when sending via MultiAccount
            })
            
            # Get the encoded function call
            encoded_settle_force_close = settle_force_close_txn["data"]
            
            # Build the MultiAccount _call transaction
            txn = self.multiaccount.functions._call(
                Web3.to_checksum_address(self.config["sub_account_address"]),
                [encoded_settle_force_close]
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
            print(f"Error settling and forcing to close position: {e}")
            raise

def main():
    """Main function to demonstrate settling and forcing to close a position via MultiAccount"""
    client = MultiAccountSettleAndForceClosePositionClient(CONFIG)
    
    # Replace with the actual quote ID
    quote_id = 2222
    
    print(f"Settling and force closing position for quote ID: {quote_id}")
    receipt = client.settle_and_force_close_position_via_multiaccount(quote_id)
    print(f"Settle and force close position transaction receipt: {receipt}")

if __name__ == "__main__":
    main()
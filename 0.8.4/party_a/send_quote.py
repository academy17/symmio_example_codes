from dotenv import load_dotenv
import os
import json
import requests
import time
from web3 import Web3
from decimal import Decimal
from typing import Dict, List, Tuple, Union, Optional, Any

# Load environment variables
load_dotenv()

# Configuration
CONFIG = {
    "rpc_url": os.getenv("RPC_URL"),
    "private_key": os.getenv("PRIVATE_KEY"),
    "diamond_address": os.getenv("DIAMOND_ADDRESS"),
    "chain_id": os.getenv("CHAIN_ID", "137"),
    "muon_base_url": os.getenv("MUON_BASE_URL", "https://muon-oracle1.rasa.capital/v1/"),
    "hedger_url": os.getenv("HEDGER_URL", "https://base-hedger82.rasa.capital/"),
    
    # Trade settings
    "symbol_id": 4,
    "party_b_whitelist": ["0x5044238ea045585C704dC2C6387D66d29eD56648"],
    "quantity": "6",
    "leverage": 1,
    "position_type": 0,  # 0=LONG, 1=SHORT
    "order_type": 1,     # 0=LIMIT, 1=MARKET
    "slippage": "2"      # Percentage
}

class SendQuoteClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Load ABI
        abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
        with open(abi_path, "r") as abi_file:
            self.abi = json.load(abi_file)
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))
        self.account = self.w3.eth.account.from_key(config["private_key"])
        self.diamond = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["diamond_address"]), 
            abi=self.abi
        )
    
    def api_request(self, url: str, error_message: str = "API request failed") -> Dict:
        """Make API request with error handling"""
        print(f"Request: {url}")
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"{error_message}: {response.text}")
        result = response.json()
        if isinstance(result, dict) and not result.get("success", True):
            raise Exception(f"{error_message}: {result}")
        return result
    
    def fetch_market(self, symbol_id: int) -> Dict:
        """Fetch market information by symbol_id"""
        url = f"{self.config['hedger_url']}contract-symbols"
        markets_data = self.api_request(url, "Failed to fetch market symbols")
        
        filtered_markets = [
            {
                "id": market["symbol_id"],
                "name": market["name"],
                "symbol": market["symbol"],
                "asset": market["asset"],
                "pricePrecision": market["price_precision"],
                "quantityPrecision": market["quantity_precision"],
                "isValid": market["is_valid"],
                "minAcceptableQuoteValue": market["min_acceptable_quote_value"],
                "minAcceptablePortionLF": market["min_acceptable_portion_lf"],
                "tradingFee": market["trading_fee"],
                "maxLeverage": market["max_leverage"],
                "maxNotionalValue": market["max_notional_value"],
                "maxFundingRate": market["max_funding_rate"],
                "rfqAllowed": market["rfq_allowed"],
                "hedgerFeeOpen": market["hedger_fee_open"],
                "hedgerFeeClose": market["hedger_fee_close"],
            }
            for market in markets_data["symbols"]
            if market["symbol_id"] == symbol_id
        ]
        
        if not filtered_markets:
            raise Exception(f"Symbol ID {symbol_id} not found in markets")
        
        return filtered_markets[0]
    
    def fetch_locked_params(self, pair: str, leverage: int) -> Dict:
        """Fetch locked parameters for a symbol and leverage"""
        url = f"{self.config['hedger_url']}get_locked_params/{pair}?leverage={leverage}"
        data = self.api_request(url, "Failed to fetch locked params")
        
        return {
            "cva": data["cva"],
            "partyAmm": data["partyAmm"],
            "lf": data["lf"],
            "leverage": data["leverage"],
            "partyBmm": data["partyBmm"]
        }
    
    def fetch_upnl_sig(self, symbol_id: int) -> Tuple:
        """Fetch SingleUpnlAndPriceSig from Muon API"""
        url_params = {
            "app": "symmio",
            "method": "uPnl_A_withSymbolPrice",
            "params[partyA]": self.account.address,
            "params[chainId]": self.config["chain_id"],
            "params[symmio]": self.config["diamond_address"],
            "params[symbolId]": symbol_id
        }
        
        url = f"{self.config['muon_base_url']}?{'&'.join([f'{k}={v}' for k, v in url_params.items()])}"
        result = self.api_request(url, "Failed to fetch Muon signature")
        
        # Format signature for contract call
        req_id = result["result"]["reqId"]
        timestamp = int(result["result"]["data"]["timestamp"]) if result["result"]["data"].get("timestamp") else 0
        upnl = int(result["result"]["data"]["result"].get("uPnl", "0"))
        price = int(result["result"]["data"]["result"].get("price", "0"))
        gateway_signature = result["result"]["nodeSignature"]
        
        signature = int(result["result"]["signatures"][0]["signature"], 16)
        owner = Web3.to_checksum_address(result["result"]["signatures"][0]["owner"])
        nonce = Web3.to_checksum_address(result["result"]["data"]["init"]["nonceAddress"])
        
        req_id_bytes = Web3.to_bytes(hexstr=req_id)
        gateway_signature_bytes = Web3.to_bytes(hexstr=gateway_signature)
        
        schnorr_sign = (signature, owner, nonce)
        upnl_sig = (req_id_bytes, timestamp, upnl, price, gateway_signature_bytes, schnorr_sign)
        
        return upnl_sig, price
    
    def calculate_adjusted_price(self, price: int, position_type: int, slippage: str) -> int:
        """Calculate price with slippage"""
        slippage_percent = float(slippage)
        if position_type == 1:  # SHORT
            return int(price * (1 - slippage_percent / 100))
        else:  # LONG
            return int(price * (1 + slippage_percent / 100))
    
    def calculate_margins(self, notional_value: Decimal, locked_params: Dict) -> Dict:
        """Calculate all margin values"""
        leverage = Decimal(locked_params["leverage"])
        
        cva_wei = int(notional_value * Decimal(locked_params["cva"]) / 
                     (Decimal(100) * leverage * Decimal(10**18)))
        
        lf_wei = int(notional_value * Decimal(locked_params["lf"]) / 
                    (Decimal(100) * leverage * Decimal(10**18)))
        
        party_a_mm_wei = int(notional_value * Decimal(locked_params["partyAmm"]) / 
                           (Decimal(100) * leverage * Decimal(10**18)))
        
        party_b_mm_wei = int(notional_value * Decimal(locked_params["partyBmm"]) / 
                           (Decimal(100) * Decimal(10**18)))
        
        return {
            "cva": cva_wei,
            "lf": lf_wei,
            "partyAmm": party_a_mm_wei,
            "partyBmm": party_b_mm_wei
        }
    
    def send_quote(self) -> int:
        """Execute sendQuote function"""
        try:
            # 1. Fetch market info
            market = self.fetch_market(self.config["symbol_id"])
            print(f"Market: {market['name']} (ID: {market['id']})")
            
            # 2. Fetch locked parameters
            locked_params = self.fetch_locked_params(market["name"], self.config["leverage"])
            print(f"Locked params fetched")
            
            # 3. Get Muon signature and price
            upnl_sig, original_price = self.fetch_upnl_sig(market["id"])
            print(f"Original price: {original_price}")
            
            # 4. Calculate adjusted price with slippage
            adjusted_price = self.calculate_adjusted_price(
                original_price, 
                self.config["position_type"], 
                self.config["slippage"]
            )
            print(f"Adjusted price: {adjusted_price}")
            
            # 5. Convert parameters
            party_bs_white_list = [Web3.to_checksum_address(addr) for addr in self.config["party_b_whitelist"]]
            quantity_wei = self.w3.to_wei(self.config["quantity"], "ether")
            
            # 6. Calculate notional value and margins
            notional_value = Decimal(quantity_wei) * Decimal(adjusted_price)
            margins = self.calculate_margins(notional_value, locked_params)
            print(f"Notional: {notional_value}, CVA: {margins['cva']}")
            
            # 7. Set max funding rate and deadline
            max_funding_rate = self.w3.to_wei("200", "ether")
            deadline = int(time.time()) + 86400  # 24 hours
            
            # 8. Build and send transaction
            txn = self.diamond.functions.sendQuote(
                party_bs_white_list,
                market["id"],
                self.config["position_type"],
                self.config["order_type"],
                adjusted_price,
                quantity_wei,
                margins["cva"],
                margins["lf"],
                margins["partyAmm"],
                margins["partyBmm"],
                max_funding_rate,
                deadline,
                upnl_sig
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 800000,
                "gasPrice": self.w3.eth.gas_price,
            })
            
            signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.config["private_key"])
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"Transaction sent: {tx_hash.hex()}")

            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Transaction confirmed.")
            return 0  # Return 0 or any placeholder value if needed
                                                
        except Exception as e:
            print(f"Error: {e}")
            raise

def main():
    """Main function to demonstrate SDK usage"""
    client = SendQuoteClient(CONFIG)
    
    # Example: Modify configuration as needed
    # client.config["slippage"] = "1" 
    # client.config["position_type"] = 1  # Change to SHORT
    
    client.send_quote()
    print("Quote creation process completed.")

if __name__ == "__main__":
    main()
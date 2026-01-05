from dotenv import load_dotenv
import os
import json
import requests
from web3 import Web3
from typing import Dict, Any, List, Tuple


load_dotenv()

CONFIG = {
    "rpc_url": os.getenv("RPC_URL"),
    "private_key": os.getenv("PRIVATE_KEY"),
    "diamond_address": os.getenv("DIAMOND_ADDRESS"),
    "chain_id": os.getenv("CHAIN_ID", "137"),
    "muon_base_url": os.getenv("MUON_BASE_URL", "https://polygon-testnet-oracle.rasa.capital/v1/"),
}

class SettleUpnlClient:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        
        symmio_abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
        
        with open(symmio_abi_path, "r") as abi_file:
            self.symmio_abi = json.load(abi_file)
        
        
        self.w3 = Web3(Web3.HTTPProvider(config["rpc_url"]))
        self.account = self.w3.eth.account.from_key(config["private_key"])
        self.diamond = self.w3.eth.contract(
            address=Web3.to_checksum_address(config["diamond_address"]),
            abi=self.symmio_abi
        )
    
    def fetch_settlement_signature(self, party_a: str, quote_ids: List[int]) -> Dict[str, Any]:
        """Fetch settlement signature from Muon API"""
        
        quote_ids_str = f"[{','.join(map(str, quote_ids))}]"
        
        url = (
            f"{self.config['muon_base_url']}?app=symmio&method=settle_upnl"
            f"&params[partyA]={party_a}"
            f"&params[chainId]={self.config['chain_id']}"
            f"&params[symmio]={self.config['diamond_address']}"
            f"&params[quoteIds]={quote_ids_str}"
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
        
        
        quotes_settlements_data = []
        if "quoteSettlementData" in result["result"]["data"]["result"]:
            raw_settlement_data = result["result"]["data"]["result"]["quoteSettlementData"]
            for data in raw_settlement_data:
                if isinstance(data, list) and len(data) >= 2:
                    quote_settlement = (
                        int(data[0]),  
                        int(data[1]),  
                        int(data[2]) if len(data) > 2 else 0  
                    )
                    quotes_settlements_data.append(quote_settlement)
        
        
        upnl_party_bs = []
        if "upnlPartyBs" in result["result"]["data"]["result"]:
            upnl_party_bs = [int(upnl) for upnl in result["result"]["data"]["result"]["upnlPartyBs"]]
        
        
        upnl_party_a = 0
        if "uPnlA" in result["result"]["data"]["result"]:
            upnl_party_a = int(result["result"]["data"]["result"]["uPnlA"])
        
        
        signature = int(result["result"]["signatures"][0]["signature"], 16)
        owner = Web3.to_checksum_address(result["result"]["signatures"][0]["owner"])
        nonce = Web3.to_checksum_address(result["result"]["data"]["init"]["nonceAddress"])

        
        req_id_bytes = Web3.to_bytes(hexstr=req_id)
        gateway_signature_bytes = Web3.to_bytes(hexstr=gateway_signature)

        
        print(f"Signature format: {signature}, {owner}, {nonce}")
        print(f"Settlement data format: Quotes={quotes_settlements_data}, upnlPartyBs={upnl_party_bs}")

        
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
    
    def get_updated_prices(self, result: Dict[str, Any]) -> List[int]:
        """Extract updated prices from the settlement API response"""
        updated_prices = []
        
        
        if "quoteSettlementData" in result["result"]["data"]["result"]:
            for data in result["result"]["data"]["result"]["quoteSettlementData"]:
                if isinstance(data, list) and len(data) >= 2:
                    updated_prices.append(int(data[1]))  
        
        return updated_prices
    
    def settle_upnl(self, party_a: str, quote_ids: List[int]) -> Dict[str, Any]:
        """Settle upnl for the specified quotes"""
        try:
            
            settlement_result = self.fetch_settlement_signature(party_a, quote_ids)
            settlement_sig = self.format_settlement_signature(settlement_result)
            
            
            updated_prices = self.get_updated_prices(settlement_result)
            
            
            print(f"Length of quotesSettlementsData: {len(settlement_sig['quotesSettlementsData'])}")
            print(f"Length of updatedPrices: {len(updated_prices)}")
            
            
            settle_upnl_txn = self.diamond.functions.settleUpnl(
                settlement_sig,
                updated_prices,
                Web3.to_checksum_address(party_a)
            ).build_transaction({
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "gas": 2000000,
                "gasPrice": int(self.w3.eth.gas_price * 1.5),
            })
            
            
            signed_txn = self.w3.eth.account.sign_transaction(settle_upnl_txn, private_key=self.config["private_key"])
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            print(f"Transaction sent: {tx_hash.hex()}")
            
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print("Transaction confirmed.")
            return receipt
        except Exception as e:
            print(f"Error settling upnl: {e}")
            raise

def main():
    """Main function to demonstrate settling upnl"""
    client = SettleUpnlClient(CONFIG)
    
    
    party_a = "0x4921a5fC974d5132b4eba7F8697236fc5851a3fA"
    quote_ids = [2223]  
    
    print(f"Settling upnl for party A: {party_a} and quote IDs: {quote_ids}")
    receipt = client.settle_upnl(party_a, quote_ids)
    print(f"Settle upnl transaction receipt: {receipt}")

if __name__ == "__main__":
    main()
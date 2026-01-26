from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from web3 import Web3


def _load_diamond_abi() -> list[dict]:
	abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
	with open(abi_path, "r", encoding="utf-8") as abi_file:
		return json.load(abi_file)


def _split_addresses(value: str) -> list[str]:
	return [a.strip() for a in (value or "").split(",") if a.strip()]


def main() -> None:
	load_dotenv()

	rpc_url = os.getenv("RPC_URL")
	private_key = os.getenv("PRIVATE_KEY")
	diamond_address = os.getenv("SYMMIO_DIAMOND_ADDRESS") or os.getenv("DIAMOND_ADDRESS")
	collateral_address = os.getenv("COLLATERAL_ADDRESS")
	party_a = os.getenv("PARTY_A_ADDRESS") or os.getenv("ACTIVE_ACCOUNT") or os.getenv("WALLET_ADDRESS")
	party_bs = _split_addresses(os.getenv("PARTY_BS", "") or os.getenv("PARTY_B_ADDRESS", ""))

	if not rpc_url or not private_key or not diamond_address or not collateral_address or not party_a or not party_bs:
		raise SystemExit(
			"Missing env vars: RPC_URL, PRIVATE_KEY, DIAMOND_ADDRESS, COLLATERAL_ADDRESS, PARTY_A_ADDRESS, PARTY_BS (comma-separated)"
		)

	w3 = Web3(Web3.HTTPProvider(rpc_url))
	account = w3.eth.account.from_key(private_key)
	diamond = w3.eth.contract(address=Web3.to_checksum_address(diamond_address), abi=_load_diamond_abi())

	chain_id = int(os.getenv("CHAIN_ID", "0") or "0")
	party_bs_cs = [Web3.to_checksum_address(a) for a in party_bs]

	# syncBalances(collateral, partyA, partyBs)
	tx = diamond.functions.syncBalances(
		Web3.to_checksum_address(collateral_address),
		Web3.to_checksum_address(party_a),
		party_bs_cs,
	).build_transaction(
		{
			"from": account.address,
			"nonce": w3.eth.get_transaction_count(account.address),
			"gasPrice": w3.eth.gas_price,
			**({"chainId": chain_id} if chain_id else {}),
		}
	)
	tx.setdefault("gas", 500_000)
	signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
	tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
	print(f"syncBalances tx sent: {tx_hash.hex()}")


if __name__ == "__main__":
	main()

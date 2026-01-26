from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from web3 import Web3


def _load_diamond_abi() -> list[dict]:
	abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
	with open(abi_path, "r", encoding="utf-8") as f:
		return json.load(f)


def main() -> None:
	load_dotenv()
	rpc_url = os.getenv("RPC_URL")
	private_key = os.getenv("PRIVATE_KEY")
	diamond_address = os.getenv("SYMMIO_DIAMOND_ADDRESS") or os.getenv("DIAMOND_ADDRESS")
	party = os.getenv("PARTY_ADDRESS")
	counter_party = os.getenv("COUNTERPARTY_ADDRESS")
	collateral = os.getenv("COLLATERAL_ADDRESS")
	amount = os.getenv("AMOUNT_WEI")

	if not rpc_url or not private_key or not diamond_address or not party or not counter_party or not collateral or amount is None:
		raise SystemExit(
			"Missing env vars: RPC_URL, PRIVATE_KEY, DIAMOND_ADDRESS, PARTY_ADDRESS, COUNTERPARTY_ADDRESS, COLLATERAL_ADDRESS, AMOUNT_WEI"
		)

	w3 = Web3(Web3.HTTPProvider(rpc_url))
	acct = w3.eth.account.from_key(private_key)
	diamond = w3.eth.contract(Web3.to_checksum_address(diamond_address), abi=_load_diamond_abi())
	chain_id = int(os.getenv("CHAIN_ID", "0") or "0")

	# allocateFromReserveToCross(party, counterParty, collateral, amount) - requires CLEARING_HOUSE_ROLE
	tx = diamond.functions.allocateFromReserveToCross(
		Web3.to_checksum_address(party),
		Web3.to_checksum_address(counter_party),
		Web3.to_checksum_address(collateral),
		int(amount),
	).build_transaction(
		{
			"from": acct.address,
			"nonce": w3.eth.get_transaction_count(acct.address),
			"gasPrice": w3.eth.gas_price,
			**({"chainId": chain_id} if chain_id else {}),
		}
	)
	tx.setdefault("gas", 600_000)
	signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
	h = w3.eth.send_raw_transaction(signed.raw_transaction)
	print(f"allocateFromReserveToCross tx sent: {h.hex()}")


if __name__ == "__main__":
	main()

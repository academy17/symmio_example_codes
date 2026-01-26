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
	liquidation_id = os.getenv("LIQUIDATION_ID")
	amount = os.getenv("AMOUNT_WEI")
	party = os.getenv("PARTY_ADDRESS")
	counter_party = os.getenv("COUNTERPARTY_ADDRESS")
	margin_type = os.getenv("MARGIN_TYPE")

	if (
		not rpc_url
		or not private_key
		or not diamond_address
		or liquidation_id is None
		or amount is None
		or not party
		or not counter_party
		or margin_type is None
	):
		raise SystemExit(
			"Missing env vars: RPC_URL, PRIVATE_KEY, DIAMOND_ADDRESS, LIQUIDATION_ID, AMOUNT_WEI, PARTY_ADDRESS, COUNTERPARTY_ADDRESS, MARGIN_TYPE"
		)

	w3 = Web3(Web3.HTTPProvider(rpc_url))
	acct = w3.eth.account.from_key(private_key)
	diamond = w3.eth.contract(Web3.to_checksum_address(diamond_address), abi=_load_diamond_abi())
	chain_id = int(os.getenv("CHAIN_ID", "0") or "0")

	# confiscate(liquidationId, amount, party, counterParty, marginType) - requires CLEARING_HOUSE_ROLE
	tx = diamond.functions.confiscate(
		int(liquidation_id),
		int(amount),
		Web3.to_checksum_address(party),
		Web3.to_checksum_address(counter_party),
		int(margin_type),
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
	print(f"confiscate tx sent: {h.hex()}")


if __name__ == "__main__":
	main()

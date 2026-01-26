from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from web3 import Web3


def _load_diamond_abi() -> list[dict]:
	abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
	with open(abi_path, "r", encoding="utf-8") as f:
		return json.load(f)


def _split(value: str) -> list[str]:
	return [x.strip() for x in (value or "").split(",") if x.strip()]


def main() -> None:
	load_dotenv()
	rpc_url = os.getenv("RPC_URL")
	private_key = os.getenv("PRIVATE_KEY")
	diamond_address = os.getenv("SYMMIO_DIAMOND_ADDRESS") or os.getenv("DIAMOND_ADDRESS")
	liquidation_id = os.getenv("LIQUIDATION_ID")
	party_b = os.getenv("PARTY_B_ADDRESS")
	collateral = os.getenv("COLLATERAL_ADDRESS")
	margin_type = os.getenv("MARGIN_TYPE")
	party_as = _split(os.getenv("PARTY_AS", ""))
	amounts = _split(os.getenv("AMOUNTS", ""))

	if (
		not rpc_url
		or not private_key
		or not diamond_address
		or liquidation_id is None
		or not party_b
		or not collateral
		or margin_type is None
		or not party_as
		or not amounts
	):
		raise SystemExit(
			"Missing env vars: RPC_URL, PRIVATE_KEY, DIAMOND_ADDRESS, LIQUIDATION_ID, PARTY_B_ADDRESS, COLLATERAL_ADDRESS, MARGIN_TYPE, PARTY_AS, AMOUNTS"
		)
	if len(party_as) != len(amounts):
		raise SystemExit("PARTY_AS and AMOUNTS must have same length")

	w3 = Web3(Web3.HTTPProvider(rpc_url))
	acct = w3.eth.account.from_key(private_key)
	diamond = w3.eth.contract(Web3.to_checksum_address(diamond_address), abi=_load_diamond_abi())
	chain_id = int(os.getenv("CHAIN_ID", "0") or "0")

	party_as_cs = [Web3.to_checksum_address(a) for a in party_as]
	amounts_u = [int(a) for a in amounts]

	# distributeCollateral(liquidationId, partyB, collateral, marginType, partyAs, amounts) - requires CLEARING_HOUSE_ROLE
	tx = diamond.functions.distributeCollateral(
		int(liquidation_id),
		Web3.to_checksum_address(party_b),
		Web3.to_checksum_address(collateral),
		int(margin_type),
		party_as_cs,
		amounts_u,
	).build_transaction(
		{
			"from": acct.address,
			"nonce": w3.eth.get_transaction_count(acct.address),
			"gasPrice": w3.eth.gas_price,
			**({"chainId": chain_id} if chain_id else {}),
		}
	)
	tx.setdefault("gas", 900_000)
	signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
	h = w3.eth.send_raw_transaction(signed.raw_transaction)
	print(f"distributeCollateral tx sent: {h.hex()}")


if __name__ == "__main__":
	main()

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from web3 import Web3


def _load_diamond_abi() -> list[dict]:
	abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
	with open(abi_path, "r", encoding="utf-8") as abi_file:
		return json.load(abi_file)


def _to_bytes(hex_str: str) -> bytes:
	value = (hex_str or "").strip()
	if not value:
		return b""
	if value.startswith("0x"):
		return Web3.to_bytes(hexstr=value)
	return value.encode("utf-8")


def main() -> None:
	load_dotenv()

	rpc_url = os.getenv("RPC_URL")
	private_key = os.getenv("PRIVATE_KEY")
	diamond_address = os.getenv("SYMMIO_DIAMOND_ADDRESS") or os.getenv("DIAMOND_ADDRESS")
	collateral_address = os.getenv("COLLATERAL_ADDRESS")
	to_address = os.getenv("TO_ADDRESS") or os.getenv("ACTIVE_ACCOUNT") or os.getenv("WALLET_ADDRESS")
	provider_address = os.getenv("PROVIDER_ADDRESS")
	user_data = os.getenv("USER_DATA", "")

	if (
		not rpc_url
		or not private_key
		or not diamond_address
		or not collateral_address
		or not to_address
		or not provider_address
	):
		raise SystemExit(
			"Missing env vars: RPC_URL, PRIVATE_KEY, DIAMOND_ADDRESS, COLLATERAL_ADDRESS, TO_ADDRESS, PROVIDER_ADDRESS"
		)

	w3 = Web3(Web3.HTTPProvider(rpc_url))
	account = w3.eth.account.from_key(private_key)
	diamond = w3.eth.contract(address=Web3.to_checksum_address(diamond_address), abi=_load_diamond_abi())

	amount = int(os.getenv("AMOUNT_WEI", str(w3.to_wei(1, "ether"))))
	chain_id = int(os.getenv("CHAIN_ID", "0") or "0")

	# initiateExpressWithdraw(collateral, amount, to, provider, userData)
	tx = diamond.functions.initiateExpressWithdraw(
		Web3.to_checksum_address(collateral_address),
		amount,
		Web3.to_checksum_address(to_address),
		Web3.to_checksum_address(provider_address),
		_to_bytes(user_data),
	).build_transaction(
		{
			"from": account.address,
			"nonce": w3.eth.get_transaction_count(account.address),
			"gasPrice": w3.eth.gas_price,
			**({"chainId": chain_id} if chain_id else {}),
		}
	)
	tx.setdefault("gas", 350_000)
	signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
	tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
	print(f"initiateExpressWithdraw tx sent: {tx_hash.hex()}")


if __name__ == "__main__":
	main()

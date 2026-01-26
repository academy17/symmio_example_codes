from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from web3 import Web3


ERC20_ABI = [
	{
		"constant": False,
		"inputs": [
			{"name": "_spender", "type": "address"},
			{"name": "_value", "type": "uint256"},
		],
		"name": "approve",
		"outputs": [{"name": "", "type": "bool"}],
		"type": "function",
	},
]


def _load_diamond_abi() -> list[dict]:
	abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
	with open(abi_path, "r", encoding="utf-8") as abi_file:
		return json.load(abi_file)


def main() -> None:
	load_dotenv()

	rpc_url = os.getenv("RPC_URL")
	private_key = os.getenv("PRIVATE_KEY")
	diamond_address = os.getenv("SYMMIO_DIAMOND_ADDRESS") or os.getenv("DIAMOND_ADDRESS")
	collateral_address = os.getenv("COLLATERAL_ADDRESS")

	if not rpc_url or not private_key or not diamond_address or not collateral_address:
		raise SystemExit("Missing env vars: RPC_URL, PRIVATE_KEY, DIAMOND_ADDRESS (or SYMMIO_DIAMOND_ADDRESS), COLLATERAL_ADDRESS")

	w3 = Web3(Web3.HTTPProvider(rpc_url))
	account = w3.eth.account.from_key(private_key)
	diamond = w3.eth.contract(address=Web3.to_checksum_address(diamond_address), abi=_load_diamond_abi())
	erc20 = w3.eth.contract(address=Web3.to_checksum_address(collateral_address), abi=ERC20_ABI)

	amount = int(os.getenv("AMOUNT_WEI", str(w3.to_wei(1, "ether"))))
	chain_id = int(os.getenv("CHAIN_ID", "0") or "0")

	# 1) Approve collateral transfer to Diamond
	approve_tx = erc20.functions.approve(Web3.to_checksum_address(diamond_address), amount).build_transaction(
		{
			"from": account.address,
			"nonce": w3.eth.get_transaction_count(account.address),
			"gasPrice": w3.eth.gas_price,
			**({"chainId": chain_id} if chain_id else {}),
		}
	)
	approve_tx.setdefault("gas", 60_000)
	signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key=private_key)
	approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
	print(f"approve tx sent: {approve_hash.hex()}")
	w3.eth.wait_for_transaction_receipt(approve_hash)
	print("approve confirmed")

	# 2) deposit(collateral, amount)
	deposit_tx = diamond.functions.deposit(Web3.to_checksum_address(collateral_address), amount).build_transaction(
		{
			"from": account.address,
			"nonce": w3.eth.get_transaction_count(account.address),
			"gasPrice": w3.eth.gas_price,
			**({"chainId": chain_id} if chain_id else {}),
		}
	)
	deposit_tx.setdefault("gas", 200_000)
	signed_deposit = w3.eth.account.sign_transaction(deposit_tx, private_key=private_key)
	deposit_hash = w3.eth.send_raw_transaction(signed_deposit.raw_transaction)
	print(f"deposit tx sent: {deposit_hash.hex()}")


if __name__ == "__main__":
	main()

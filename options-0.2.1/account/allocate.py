from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from web3 import Web3
from web3.exceptions import ContractCustomError, ContractLogicError


def _load_diamond_abi() -> list[dict]:
	abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
	with open(abi_path, "r", encoding="utf-8") as abi_file:
		return json.load(abi_file)


def _build_error_selector_map(abi: list[dict]) -> dict[bytes, dict]:
	selectors: dict[bytes, dict] = {}
	for item in abi:
		if item.get("type") != "error":
			continue
		name = item.get("name")
		inputs = item.get("inputs", [])
		types = [i.get("type") for i in inputs]
		signature = f"{name}({','.join(types)})"
		selector = Web3.keccak(text=signature)[:4]
		selectors[selector] = {
			"signature": signature,
			"inputs": inputs,
			"types": types,
		}
	return selectors


def _decode_custom_error(abi: list[dict], revert_data: str) -> str:
	data = (revert_data or "").strip()
	if not data.startswith("0x") or len(data) < 10:
		return f"Custom error (unrecognized data): {data!r}"

	selector = bytes.fromhex(data[2:10])
	selectors = _build_error_selector_map(abi)
	meta = selectors.get(selector)
	if not meta:
		return f"Custom error: 0x{selector.hex()} (not found in ABI)"

	types = meta["types"]
	inputs = meta["inputs"]
	payload_hex = data[10:]
	payload = bytes.fromhex(payload_hex) if payload_hex else b""

	try:
		decoded = Web3.codec.decode(types, payload) if types else ()
	except Exception:
		return meta["signature"]

	parts: list[str] = [meta["signature"]]
	for inp, val in zip(inputs, decoded, strict=False):
		name = inp.get("name") or "arg"
		parts.append(f"{name}={val}")
	return " | ".join(parts)


def main() -> None:
	load_dotenv()

	rpc_url = os.getenv("RPC_URL")
	private_key = os.getenv("PRIVATE_KEY")
	diamond_address = os.getenv("SYMMIO_DIAMOND_ADDRESS") or os.getenv("DIAMOND_ADDRESS")
	collateral_address = os.getenv("COLLATERAL_ADDRESS")
	# allocate() expects a PartyB / counterparty address. Prefer PARTY_B_ADDRESS to avoid
	# accidentally setting COUNTERPARTY_ADDRESS to the user's own wallet address.
	counter_party = os.getenv("PARTY_B_ADDRESS") or os.getenv("COUNTERPARTY_ADDRESS")

	if not rpc_url or not private_key or not diamond_address or not collateral_address or not counter_party:
		raise SystemExit(
			"Missing env vars: RPC_URL, PRIVATE_KEY, DIAMOND_ADDRESS (or SYMMIO_DIAMOND_ADDRESS), COLLATERAL_ADDRESS, PARTY_B_ADDRESS (or COUNTERPARTY_ADDRESS)"
		)

	w3 = Web3(Web3.HTTPProvider(rpc_url))
	account = w3.eth.account.from_key(private_key)
	abi = _load_diamond_abi()
	diamond = w3.eth.contract(address=Web3.to_checksum_address(diamond_address), abi=abi)

	amount = int(os.getenv("AMOUNT_WEI", str(w3.to_wei(1, "ether"))))
	chain_id = int(os.getenv("CHAIN_ID", "0") or "0")
	gas_limit = int(os.getenv("GAS", os.getenv("GAS_LIMIT", "300000")) or "300000")

	# allocate(collateral, counterParty, amount)
	fn = diamond.functions.allocate(
		Web3.to_checksum_address(collateral_address),
		Web3.to_checksum_address(counter_party),
		amount,
	)

	# Preflight call to surface the revert reason without spending gas.
	try:
		fn.call({"from": account.address})
	except ContractCustomError as e:
		# web3 usually provides the revert data as the first arg.
		revert_data = e.args[0] if e.args else ""
		msg = _decode_custom_error(abi, str(revert_data))
		raise SystemExit(f"allocate() reverted: {msg}")
	except ContractLogicError as e:
		raise SystemExit(f"allocate() reverted: {e}")

	tx = fn.build_transaction(
		{
			"from": account.address,
			"nonce": w3.eth.get_transaction_count(account.address),
			"gas": gas_limit,
			"gasPrice": w3.eth.gas_price,
			**({"chainId": chain_id} if chain_id else {}),
		}
	)
	signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
	tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
	print(f"allocate tx sent: {tx_hash.hex()}")


if __name__ == "__main__":
	main()

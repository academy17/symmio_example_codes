from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from web3 import Web3


def _load_diamond_abi() -> list[dict]:
	abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
	with open(abi_path, "r", encoding="utf-8") as f:
		return json.load(f)


def _split_addresses(value: str) -> list[str]:
	return [x.strip() for x in (value or "").split(",") if x.strip()]


def _to_bytes(value: str) -> bytes:
	val = (value or "").strip()
	if not val:
		return b""
	if val.startswith("0x"):
		return Web3.to_bytes(hexstr=val)
	return val.encode("utf-8")


def _env_int(name: str, *, required: bool = True, default: int | None = None) -> int:
	raw = os.getenv(name)
	if raw is None or raw.strip() == "":
		if required and default is None:
			raise SystemExit(f"Missing env var: {name}")
		return int(default or 0)
	return int(raw)


def main() -> None:
	load_dotenv()

	rpc_url = os.getenv("RPC_URL")
	private_key = os.getenv("PRIVATE_KEY")
	diamond_address = os.getenv("SYMMIO_DIAMOND_ADDRESS") or os.getenv("DIAMOND_ADDRESS")

	party_bs = _split_addresses(os.getenv("PARTY_BS_WHITELIST", "") or os.getenv("PARTY_BS", ""))
	symbol_id = _env_int("SYMBOL_ID")
	price = _env_int("PRICE")
	quantity = _env_int("QUANTITY")
	strike_price = _env_int("STRIKE_PRICE")
	expiration_timestamp = _env_int("EXPIRATION_TIMESTAMP")
	mm = _env_int("MM")
	trade_side = _env_int("TRADE_SIDE")  # enum TradeSide as uint8
	margin_type = _env_int("MARGIN_TYPE")  # enum MarginType as uint8

	exercise_fee_rate = _env_int("EXERCISE_FEE_RATE")
	exercise_fee_cap = _env_int("EXERCISE_FEE_CAP")

	solver_open_fee = _env_int("SOLVER_OPEN_FEE")
	solver_close_fee = _env_int("SOLVER_CLOSE_FEE")

	deadline = _env_int("DEADLINE")
	fee_token = os.getenv("FEE_TOKEN")
	affiliate = os.getenv("AFFILIATE", "0x0000000000000000000000000000000000000000")
	user_data = os.getenv("USER_DATA", "")

	if not rpc_url or not private_key or not diamond_address:
		raise SystemExit("Missing env vars: RPC_URL, PRIVATE_KEY, DIAMOND_ADDRESS (or SYMMIO_DIAMOND_ADDRESS)")
	if not party_bs:
		raise SystemExit("Missing env var: PARTY_BS_WHITELIST (comma-separated addresses)")
	if not fee_token:
		raise SystemExit("Missing env var: FEE_TOKEN")

	w3 = Web3(Web3.HTTPProvider(rpc_url))
	acct = w3.eth.account.from_key(private_key)
	diamond = w3.eth.contract(Web3.to_checksum_address(diamond_address), abi=_load_diamond_abi())
	chain_id = int(os.getenv("CHAIN_ID", "0") or "0")

	party_bs_cs = [Web3.to_checksum_address(a) for a in party_bs]
	exercise_fee = (exercise_fee_rate, exercise_fee_cap)
	solver_fee = (solver_open_fee, solver_close_fee)

	# sendOpenIntent(
	#   partyBsWhiteList, symbolId, price, quantity, strikePrice, expirationTimestamp, mm,
	#   tradeSide, marginType, exerciseFee, solverFee, deadline, feeToken, affiliate, userData
	# )
	tx = diamond.functions.sendOpenIntent(
		party_bs_cs,
		symbol_id,
		price,
		quantity,
		strike_price,
		expiration_timestamp,
		mm,
		trade_side,
		margin_type,
		exercise_fee,
		solver_fee,
		deadline,
		Web3.to_checksum_address(fee_token),
		Web3.to_checksum_address(affiliate),
		_to_bytes(user_data),
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
	print(f"sendOpenIntent tx sent: {h.hex()}")


if __name__ == "__main__":
	main()

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from web3 import Web3


def _load_diamond_abi() -> list[dict]:
	abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
	with open(abi_path, "r", encoding="utf-8") as f:
		return json.load(f)


def _split_ints(value: str) -> list[int]:
	parts = [x.strip() for x in (value or "").split(",") if x.strip()]
	return [int(x) for x in parts]


def _hex_to_bytes(value: str) -> bytes:
	v = (value or "").strip()
	if v.startswith("0x") or v.startswith("0X"):
		v = v[2:]
	if v == "":
		return b""
	return bytes.fromhex(v)


def _parse_settlement_price_sig(raw_json: str) -> dict[str, Any]:
	data = json.loads(raw_json)
	if not isinstance(data, dict):
		raise ValueError("SETTLEMENT_PRICE_SIG_JSON must be a JSON object")

	required = [
		"reqId",
		"timestamp",
		"symbolId",
		"settlementPrice",
		"settlementTimestamp",
		"collateralPrice",
		"gatewaySignature",
		"sigs",
	]
	for k in required:
		if k not in data:
			raise ValueError(f"SETTLEMENT_PRICE_SIG_JSON missing key: {k}")

	sigs = data["sigs"]
	if not isinstance(sigs, dict):
		raise ValueError("SETTLEMENT_PRICE_SIG_JSON.sigs must be a JSON object")
	for k in ["signature", "owner", "nonce"]:
		if k not in sigs:
			raise ValueError(f"SETTLEMENT_PRICE_SIG_JSON.sigs missing key: {k}")

	return {
		"reqId": _hex_to_bytes(str(data["reqId"])),
		"timestamp": int(data["timestamp"]),
		"symbolId": int(data["symbolId"]),
		"settlementPrice": int(data["settlementPrice"]),
		"settlementTimestamp": int(data["settlementTimestamp"]),
		"collateralPrice": int(data["collateralPrice"]),
		"gatewaySignature": _hex_to_bytes(str(data["gatewaySignature"])),
		"sigs": {
			"signature": int(sigs["signature"]),
			"owner": Web3.to_checksum_address(str(sigs["owner"])),
			"nonce": Web3.to_checksum_address(str(sigs["nonce"])),
		},
	}


def main() -> None:
	load_dotenv()

	rpc_url = os.getenv("RPC_URL")
	private_key = os.getenv("PRIVATE_KEY")
	diamond_address = os.getenv("SYMMIO_DIAMOND_ADDRESS") or os.getenv("DIAMOND_ADDRESS")
	trade_ids = _split_ints(os.getenv("TRADE_IDS", ""))
	settlement_price_sig_json = os.getenv("SETTLEMENT_PRICE_SIG_JSON")

	if not rpc_url or not private_key or not diamond_address or not trade_ids or not settlement_price_sig_json:
		raise SystemExit(
			"Missing env vars: RPC_URL, PRIVATE_KEY, DIAMOND_ADDRESS (or SYMMIO_DIAMOND_ADDRESS), TRADE_IDS, SETTLEMENT_PRICE_SIG_JSON"
		)

	settlement_price_sig = _parse_settlement_price_sig(settlement_price_sig_json)

	w3 = Web3(Web3.HTTPProvider(rpc_url))
	acct = w3.eth.account.from_key(private_key)
	diamond = w3.eth.contract(Web3.to_checksum_address(diamond_address), abi=_load_diamond_abi())
	chain_id = int(os.getenv("CHAIN_ID", "0") or "0")

	# executeTrades(tradeIds, settlementPriceSig)
	tx = diamond.functions.executeTrades(trade_ids, settlement_price_sig).build_transaction(
		{
			"from": acct.address,
			"nonce": w3.eth.get_transaction_count(acct.address),
			"gasPrice": w3.eth.gas_price,
			**({"chainId": chain_id} if chain_id else {}),
		}
	)
	tx.setdefault("gas", 1_200_000)
	signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
	h = w3.eth.send_raw_transaction(signed.raw_transaction)
	print(f"executeTrades tx sent: {h.hex()}")


if __name__ == "__main__":
	main()

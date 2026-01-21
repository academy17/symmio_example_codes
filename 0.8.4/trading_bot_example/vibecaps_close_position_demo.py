"""Vibecaps Demo (Base): Instant Close

Run (interactive prompts)
- python trading_bot_example/vibecaps_close_position_demo.py

Inputs (prompted if missing)
- quote_id, quantity, position_type (0=long, 1=short)

Required .env
- PRIVATE_KEY
- VIBE_SUBACCOUNT (or SUB_ACCOUNT_ADDRESS)

Optional .env
- VIBE_SOLVER_URL
- VIBE_CHAIN_ID
- VIBE_DIAMOND_ADDRESS
- MUON_BASE_URL
- VIBE_SYMBOL_ID
- VIBE_CLOSE_SLIPPAGE
- VIBE_CLOSE_DEADLINE_OFFSET
- VIBE_CLOSE_ORDER_TYPE
"""

import argparse
import json
import os
import time
import traceback
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN

import requests
from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3


def prompt_str(label: str, default: str | None = None) -> str:
	if default is None:
		value = input(f"{label}: ").strip()
		return value
	value = input(f"{label} [{default}]: ").strip()
	return value if value else default


def prompt_int(label: str, default: int | None = None, *, min_value: int | None = None) -> int:
	while True:
		raw = prompt_str(label, str(default) if default is not None else None)
		try:
			value = int(raw)
		except ValueError:
			print("  Invalid integer, try again.")
			continue
		if min_value is not None and value < min_value:
			print(f"  Must be >= {min_value}.")
			continue
		return value


def prompt_decimal(label: str, default: str | None = None, *, min_value: Decimal | None = None) -> Decimal:
	while True:
		raw = prompt_str(label, default)
		try:
			value = Decimal(raw)
		except Exception:
			print("  Invalid decimal, try again.")
			continue
		if min_value is not None and value < min_value:
			print(f"  Must be >= {min_value}.")
			continue
		return value


def utc_iso_ms_z(dt: datetime) -> str:
	return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_siwe_message(
	*,
	domain: str,
	address: str,
	statement: str,
	uri: str,
	version: str,
	chain_id: int,
	nonce: str,
	issued_at: str,
	expiration_time: str,
) -> str:
	return f"""{domain} wants you to sign in with your Ethereum account:
{address}

{statement}

URI: {uri}
Version: {version}
Chain ID: {chain_id}
Nonce: {nonce}
Issued At: {issued_at}
Expiration Time: {expiration_time}"""


def get_nonce(solver_base_url: str, account_address: str) -> str:
	url = f"{solver_base_url}/nonce/{account_address}"
	print(f"[NONCE] {url}")
	resp = requests.get(url, timeout=30)
	resp.raise_for_status()
	return resp.json()["nonce"]


def login(*, solver_base_url: str, chain_id: int, active_account: str, wallet: Account) -> str:
	login_uri = f"{solver_base_url}/login"

	issued_at = utc_iso_ms_z(datetime.now(timezone.utc))
	expiration_time = utc_iso_ms_z(datetime.now(timezone.utc) + timedelta(hours=24))

	nonce = get_nonce(solver_base_url, active_account)
	msg = build_siwe_message(
		domain="localhost",
		address=wallet.address,
		statement=f"msg: {active_account}",
		uri=login_uri,
		version="1",
		chain_id=chain_id,
		nonce=nonce,
		issued_at=issued_at,
		expiration_time=expiration_time,
	)
	print(f"[LOGIN] SIWE Message:\n{msg}\n")

	message = encode_defunct(text=msg)
	signed = wallet.sign_message(message)
	signature = "0x" + signed.signature.hex()

	body = {
		"account_address": active_account,
		"expiration_time": expiration_time,
		"issued_at": issued_at,
		"signature": signature,
		"nonce": nonce,
	}
	headers = {
		"Content-Type": "application/json",
		"Origin": "http://localhost:3000",
		"Referer": "http://localhost:3000",
	}

	print(f"[LOGIN] POST {login_uri}")
	resp = requests.post(login_uri, json=body, headers=headers, timeout=30)
	print(f"[LOGIN] Response: {resp.text}")
	resp.raise_for_status()

	token = resp.json().get("access_token")
	if not token:
		raise ValueError("No access_token in login response")
	return token


def get_muon_url(muon_base_url: str, *, party_a: str, chain_id: int, symmio: str, symbol_id: int) -> str:
	return (
		f"{muon_base_url}?app=symmio&method=uPnl_A_withSymbolPrice"
		f"&params[partyA]={party_a}"
		f"&params[chainId]={chain_id}"
		f"&params[symmio]={symmio}"
		f"&params[symbolId]={symbol_id}"
	)


def fetch_muon_price(*, muon_base_url: str, party_a: str, chain_id: int, symmio: str, symbol_id: int) -> Decimal:
	url = get_muon_url(muon_base_url, party_a=party_a, chain_id=chain_id, symmio=symmio, symbol_id=symbol_id)
	print(f"[MUON] {url}")
	resp = requests.get(url, timeout=30)
	resp.raise_for_status()
	data = resp.json()
	price_wei = data["result"]["data"]["result"]["price"]
	if not price_wei:
		raise ValueError("Muon price not found")
	return Decimal(price_wei) / Decimal("1e18")


def fetch_symbol_info(solver_base_url: str, symbol_id: int) -> dict:
	url = f"{solver_base_url}/contract-symbols"
	print(f"[SYMBOLS] {url}")
	resp = requests.get(url, timeout=30)
	resp.raise_for_status()
	payload = resp.json()

	symbols: list[dict] = []
	if isinstance(payload, list):
		symbols = [s for s in payload if isinstance(s, dict)]
	elif isinstance(payload, dict):
		candidate = None
		for key in ("symbols", "data", "result", "items", "contract_symbols"):
			val = payload.get(key)
			if isinstance(val, list):
				candidate = val
				break
			if isinstance(val, dict):
				nested = val.get("symbols") or val.get("data") or val.get("result")
				if isinstance(nested, list):
					candidate = nested
					break
		if isinstance(candidate, list):
			symbols = [s for s in candidate if isinstance(s, dict)]
		else:
			values = list(payload.values())
			if values and all(isinstance(v, dict) for v in values):
				symbols = values

	def _coerce_int(v):
		try:
			return int(v)
		except (TypeError, ValueError):
			return None

	for sym in symbols:
		sym_id = _coerce_int(sym.get("symbol_id")) or _coerce_int(sym.get("symbolId")) or _coerce_int(sym.get("id"))
		if sym_id == symbol_id:
			return sym

	raise ValueError(f"Symbol ID {symbol_id} not found in contract-symbols")


def format_decimal(value: Decimal, precision: int) -> str:
	quantizer = Decimal(10) ** -precision
	return str(value.quantize(quantizer, rounding=ROUND_DOWN))


def instant_close(
	*,
	solver_base_url: str,
	token: str,
	quote_id: int,
	quantity_to_close: str,
	close_price: str,
	deadline: int,
	order_type: int,
) -> dict:
	url = f"{solver_base_url}/instant_close"
	payload = {
		"quote_id": int(quote_id),
		"quantity_to_close": str(quantity_to_close),
		"close_price": str(close_price),
		"deadline": int(deadline),
		"order_type": int(order_type),
	}
	headers = {
		"Content-Type": "application/json",
		"Authorization": f"Bearer {token}",
	}
	print(f"[CLOSE] POST {url}")
	print(f"[CLOSE] Payload: {json.dumps(payload, indent=2)}")
	resp = requests.post(url, json=payload, headers=headers, timeout=30)
	print(f"[CLOSE] Status: {resp.status_code}")
	print(f"[CLOSE] Response: {resp.text}")
	resp.raise_for_status()
	return resp.json() if resp.text else {}


def main() -> None:
	load_dotenv()

	parser = argparse.ArgumentParser(description="Vibecaps instant close demo")
	parser.add_argument("--quote-id", type=int, help="Quote ID to close")
	parser.add_argument("--quantity", help="Quantity to close (string/decimal)")
	parser.add_argument("--position-type", type=int, choices=[0, 1], help="0=Long, 1=Short")
	parser.add_argument("--symbol-id", type=int, default=int(os.getenv("VIBE_SYMBOL_ID", "1")))
	parser.add_argument(
		"--deadline",
		type=int,
		help="Unix timestamp deadline (seconds). Default: now + DEADLINE_OFFSET.",
	)
	parser.add_argument(
		"--order-type",
		type=int,
		default=int(os.getenv("VIBE_CLOSE_ORDER_TYPE", "1")),
		help="Order type (market=1). Default 1.",
	)
	parser.add_argument(
		"--deadline-offset",
		type=int,
		default=int(os.getenv("VIBE_CLOSE_DEADLINE_OFFSET", "3600")),
		help="Deadline offset in seconds when prompting (default 3600).",
	)
	parser.add_argument(
		"--slippage",
		default=os.getenv("VIBE_CLOSE_SLIPPAGE", "1.0"),
		help="Slippage as fraction (e.g. 1.0 for 100%%). Close long decreases; close short increases.",
	)
	parser.add_argument(
		"--prompt",
		action="store_true",
		help="Prompt for any missing inputs (default behavior when args are omitted).",
	)
	parser.add_argument(
		"--no-prompt",
		action="store_true",
		help="Disable prompting; error if required inputs are missing.",
	)
	args = parser.parse_args()

	# Default behavior: prompt for all fields (with defaults) unless --no-prompt is passed.
	should_prompt = (not args.no_prompt) and (args.prompt or True)

	if should_prompt:
		print("\nEnter close parameters (press Enter to accept defaults):")
		args.quote_id = prompt_int("Quote ID", default=args.quote_id, min_value=1)
		args.quantity = prompt_str("Quantity to close", args.quantity)
		args.position_type = prompt_int("Position Type (0=Long, 1=Short)", default=args.position_type or 0, min_value=0)
		if args.position_type not in (0, 1):
			raise ValueError("Position Type must be 0 or 1")

		args.symbol_id = prompt_int("Symbol ID", default=args.symbol_id, min_value=0)
		args.slippage = prompt_str("Slippage (fraction, e.g. 0.05)", str(args.slippage))

		default_deadline = int(time.time()) + int(args.deadline_offset)
		args.deadline = prompt_int("Deadline (unix seconds)", default=args.deadline or default_deadline, min_value=1)
		args.order_type = prompt_int("Order Type (market=1)", default=args.order_type, min_value=1)
	else:
		# Non-interactive mode: validate required inputs
		missing = [
			name
			for name, val in (
				("--quote-id", args.quote_id),
				("--quantity", args.quantity),
				("--position-type", args.position_type),
				("--deadline", args.deadline),
			)
			if val is None
		]
		if missing:
			raise ValueError(f"Missing required inputs in --no-prompt mode: {', '.join(missing)}")

	private_key = os.getenv("PRIVATE_KEY")
	if not private_key:
		raise ValueError("PRIVATE_KEY is required")

	active_account = os.getenv("VIBE_SUBACCOUNT") or os.getenv("ACTIVE_ACCOUNT") or os.getenv("SUB_ACCOUNT_ADDRESS")
	if not active_account:
		raise ValueError("VIBE_SUBACCOUNT (or ACTIVE_ACCOUNT / SUB_ACCOUNT_ADDRESS) is required")
	active_account = Web3.to_checksum_address(active_account)

	solver_base_url = os.getenv("VIBE_SOLVER_URL")
	chain_id = int(os.getenv("VIBE_CHAIN_ID", "8453"))
	diamond = Web3.to_checksum_address(
		os.getenv("VIBE_DIAMOND_ADDRESS", "0xC6a7cc26fd84aE573b705423b7d1831139793025")
	)
	muon_base_url = os.getenv("MUON_BASE_URL", "https://muon-oracle1.rasa.capital/v1/")

	wallet = Account.from_key(private_key)

	print("=" * 60)
	print("Vibecaps Demo: Login -> Instant Close")
	print("=" * 60)
	print(f"Solver: {solver_base_url}")
	print(f"Chain ID: {chain_id}")
	print(f"Active Account: {active_account}")
	print(f"Wallet: {wallet.address}")
	print(
		f"Quote ID: {args.quote_id} | Qty: {args.quantity} | PositionType: {args.position_type} | "
		f"OrderType: {args.order_type} | Deadline: {args.deadline}"
	)
	print("=" * 60)

	token = login(solver_base_url=solver_base_url, chain_id=chain_id, active_account=active_account, wallet=wallet)
	print("✅ Logged in")

	symbol_info = fetch_symbol_info(solver_base_url, args.symbol_id)
	price_precision = int(symbol_info.get("price_precision", 6))
	quantity_precision = int(symbol_info.get("quantity_precision", 6))

	muon_price = fetch_muon_price(
		muon_base_url=muon_base_url,
		party_a=active_account,
		chain_id=chain_id,
		symmio=diamond,
		symbol_id=args.symbol_id,
	)
	slippage = Decimal(str(args.slippage))
	if slippage < 0:
		raise ValueError("slippage must be non-negative")

	if args.position_type == 0:
		# CLOSE LONG: decrease price by slippage
		adjusted_price = muon_price * (Decimal("1") - slippage)
		slippage_label = f"-{slippage}"
	else:
		# CLOSE SHORT: increase price by slippage
		adjusted_price = muon_price * (Decimal("1") + slippage)
		slippage_label = f"+{slippage}"

	close_price = format_decimal(adjusted_price, price_precision)
	quantity_to_close = format_decimal(Decimal(str(args.quantity)), quantity_precision)

	print(f"[PRICE] Muon: {muon_price} | Slippage: {slippage_label} | Close Price: {close_price}")
	print(f"[QTY] Quantity to close formatted: {quantity_to_close}")

	instant_close(
		solver_base_url=solver_base_url,
		token=token,
		quote_id=args.quote_id,
		quantity_to_close=quantity_to_close,
		close_price=close_price,
		deadline=int(args.deadline),
		order_type=int(args.order_type),
	)
	print("✅ Close request sent")


if __name__ == "__main__":
	try:
		main()
	except Exception as e:
		print(f"❌ Fatal Error: {e}")
		traceback.print_exc()

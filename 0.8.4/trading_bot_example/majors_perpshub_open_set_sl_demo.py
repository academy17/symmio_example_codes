"""PerpsHub Majors Demo (Base/Vibe): Instant Open + Stop Loss

Run
- python trading_bot_example/majors_perpshub_open_set_sl_demo.py

Required .env
- PRIVATE_KEY
- MAJORS_SUBACCOUNT (or SUB_ACCOUNT_ADDRESS)

Optional .env (endpoints)
- PERPSHUB_BASE_URL
- PERPSHUB_CHAIN_ID
- MUON_BASE_URL
- PERPSHUB_SYMMIO_DIAMOND_ADDRESS

Optional .env (trade params)
- MAJORS_SYMBOL_NAME, MAJORS_SYMBOL_ID
- MAJORS_POSITION_TYPE, MAJORS_QUANTITY, MAJORS_LEVERAGE
- MAJORS_OPEN_SLIPPAGE, MAJORS_MAX_FUNDING_RATE
- MAJORS_DEADLINE_OFFSET, MAJORS_STATUS_TIMEOUT_SECONDS, MAJORS_STATUS_POLL_INTERVAL
- MAJORS_SL_PCT
"""

import os
import time
import json
import traceback
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN

import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from dotenv import load_dotenv
from web3 import Web3


load_dotenv()


CONFIG = {
	"SYMBOL_NAME": os.getenv("MAJORS_SYMBOL_NAME", "XRPUSDT"),
	"SYMBOL_ID": 4,  # XRP
	"POSITION_TYPE": 0,  # 0 = LONG, 1 = SHORT
	"ORDER_TYPE": 1,  # 1 = Market
	"LEVERAGE": os.getenv("MAJORS_LEVERAGE", "1"),
	"QUANTITY": os.getenv("MAJORS_QUANTITY", "5.5"),
	"MAX_FUNDING_RATE": os.getenv("MAJORS_MAX_FUNDING_RATE", "200"),
	"DEADLINE_OFFSET": int(os.getenv("MAJORS_DEADLINE_OFFSET", "3600")),
	"STATUS_POLL_INTERVAL": float(os.getenv("MAJORS_STATUS_POLL_INTERVAL", "0.5")),
	"STATUS_TIMEOUT_SECONDS": int(os.getenv("MAJORS_STATUS_TIMEOUT_SECONDS", "60")),
	"SL_PCT": Decimal(os.getenv("MAJORS_SL_PCT", "0.20")),
	"OPEN_SLIPPAGE": Decimal(os.getenv("MAJORS_OPEN_SLIPPAGE", "0.01")),  # 1%
}


PRIVATE_KEY = os.getenv("PRIVATE_KEY")
if not PRIVATE_KEY:
	raise ValueError("Missing PRIVATE_KEY")

_MAJORS_SUBACCOUNT_RAW = os.getenv("MAJORS_SUBACCOUNT")
_FALLBACK_SUBACCOUNT_RAW = os.getenv("SUB_ACCOUNT_ADDRESS")

ACTIVE_ACCOUNT_RAW = _MAJORS_SUBACCOUNT_RAW or _FALLBACK_SUBACCOUNT_RAW
if not ACTIVE_ACCOUNT_RAW:
	raise ValueError(
		"Missing subaccount address. Set MAJORS_SUBACCOUNT (preferred) or SUB_ACCOUNT_ADDRESS."
	)
ACTIVE_ACCOUNT = Web3.to_checksum_address(ACTIVE_ACCOUNT_RAW)

wallet = Account.from_key(PRIVATE_KEY)


# Use a single PerpsHub base URL for all actions.
PERPSHUB_BASE_URL = os.getenv(
	"PERPSHUB_BASE_URL",
	"https://www.perps-streaming.com/v1/8453a/0x95605c64356572eb5C076Cb9c027c88b527A2059/",
)
if not PERPSHUB_BASE_URL.endswith("/"):
	PERPSHUB_BASE_URL += "/"

CHAIN_ID = int(os.getenv("PERPSHUB_CHAIN_ID", "8453"))

# Only needed if you want Muon-based price and the backend expects a price in instant_open.
MUON_BASE_URL = os.getenv("MUON_BASE_URL", "https://muon-oracle1.rasa.capital/v1/")
SYMMIO_DIAMOND_ADDRESS = os.getenv(
	"PERPSHUB_SYMMIO_DIAMOND_ADDRESS",
	os.getenv("VIBE_DIAMOND_ADDRESS", "0x91Cf2D8Ed503EC52768999aA6D8DBeA6e52dbe43"),
)
SYMMIO_DIAMOND_ADDRESS = Web3.to_checksum_address(SYMMIO_DIAMOND_ADDRESS)


DOMAIN = "localhost"
ORIGIN = "http://localhost:3000"


def _iso_utc_ms(dt: datetime) -> str:
	return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def build_siwe_message(
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


def http_get_json(url: str, headers: dict | None = None, timeout: int = 30):
	resp = requests.get(url, headers=headers, timeout=timeout)
	resp.raise_for_status()
	return resp.json()


def http_post_json(url: str, body: dict, headers: dict | None = None, timeout: int = 30):
	resp = requests.post(url, json=body, headers=headers, timeout=timeout)
	resp.raise_for_status()
	return resp.json()


def get_nonce(party_a: str) -> str:
	url = f"{PERPSHUB_BASE_URL}nonce/{party_a}"
	print(f"[NONCE] {url}")
	data = http_get_json(url)
	nonce = data.get("nonce")
	if not nonce:
		raise ValueError(f"No nonce in response: {data}")
	return str(nonce)


def login() -> str:
	issued_at = _iso_utc_ms(datetime.now(timezone.utc))
	expiration_time = _iso_utc_ms(datetime.now(timezone.utc) + timedelta(hours=24))

	nonce = get_nonce(ACTIVE_ACCOUNT)
	login_uri = f"{PERPSHUB_BASE_URL}login"

	# This matches the style used by the solver login you already have.
	message_string = build_siwe_message(
		domain=DOMAIN,
		address=wallet.address,
		statement=f"msg: {ACTIVE_ACCOUNT}",
		uri=login_uri,
		version="1",
		chain_id=CHAIN_ID,
		nonce=nonce,
		issued_at=issued_at,
		expiration_time=expiration_time,
	)

	message = encode_defunct(text=message_string)
	signed_message = wallet.sign_message(message)
	signature = "0x" + signed_message.signature.hex()

	body = {
		"account_address": ACTIVE_ACCOUNT,
		"issued_at": issued_at,
		"expiration_time": expiration_time,
		"nonce": nonce,
		"signature": signature,
	}
	headers = {
		"Content-Type": "application/json",
		"Origin": ORIGIN,
		"Referer": ORIGIN,
	}

	print(f"[LOGIN] POST {login_uri}")
	resp = requests.post(login_uri, json=body, headers=headers, timeout=30)
	print(f"[LOGIN] Status={resp.status_code} Body={resp.text}")
	resp.raise_for_status()

	token = (resp.json() or {}).get("access_token")
	if not token:
		raise ValueError("No access_token in login response")
	return token


def get_muon_url(party_a: str, chain_id: int, symmio: str, symbol_id: int) -> str:
	return (
		f"{MUON_BASE_URL}?app=symmio&method=uPnl_A_withSymbolPrice"
		f"&params[partyA]={party_a}"
		f"&params[chainId]={chain_id}"
		f"&params[symmio]={symmio}"
		f"&params[symbolId]={symbol_id}"
	)


def fetch_muon_price(symbol_id: int) -> Decimal:
	url = get_muon_url(ACTIVE_ACCOUNT, CHAIN_ID, SYMMIO_DIAMOND_ADDRESS, symbol_id)
	print(f"[MUON] {url}")
	data = http_get_json(url)
	price_wei = (((data or {}).get("result") or {}).get("data") or {}).get("result", {}).get("price")
	if not price_wei:
		raise ValueError(f"Muon price not found: {data}")
	return Decimal(price_wei) / Decimal("1e18")


def fetch_symbol_info(symbol_id: int) -> dict:
	url = f"{PERPSHUB_BASE_URL}contract-symbols"
	print(f"[SYMBOLS] {url}")
	try:
		payload = http_get_json(url)
	except Exception as e:
		print(f"[SYMBOLS] Warning: failed to fetch symbol info ({e}); using defaults")
		return {"symbol_id": symbol_id, "price_precision": 6, "quantity_precision": 6}

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
		if isinstance(candidate, list):
			symbols = [s for s in candidate if isinstance(s, dict)]
		else:
			values = list(payload.values())
			if values and all(isinstance(v, dict) for v in values):
				symbols = values

	def _coerce_int(val):
		try:
			return int(val)
		except Exception:
			return None

	for sym in symbols:
		sym_id = _coerce_int(sym.get("symbol_id")) or _coerce_int(sym.get("symbolId")) or _coerce_int(sym.get("id"))
		if sym_id == symbol_id:
			return sym

	print("[SYMBOLS] Warning: symbol not found; using defaults")
	return {"symbol_id": symbol_id, "price_precision": 6, "quantity_precision": 6}


def format_decimal(value: Decimal, precision: int) -> str:
	quantizer = Decimal(10) ** -int(precision)
	return str(value.quantize(quantizer, rounding=ROUND_DOWN))



def fetch_locked_params(symbol_name: str, leverage: str) -> dict:
	url = f"{PERPSHUB_BASE_URL}get_locked_params/{symbol_name}?leverage={leverage}"
	print(f"[PARAMS] {url}")
	data = http_get_json(url)
	if not isinstance(data, dict) or "cva" not in data:
		raise ValueError(f"Unexpected locked params payload: {data}")
	return data


def calculate_normalized_locked_value(
	notional: Decimal,
	locked_param: str,
	leverage: Decimal,
	apply_leverage: bool = True,
) -> str:
	locked = Decimal(str(locked_param))
	if apply_leverage:
		val = notional * locked / (Decimal("100") * leverage)
	else:
		val = notional * locked / Decimal("100")
	s = "{:f}".format(val)
	if "." in s:
		s = s.rstrip("0").rstrip(".")
	return s


def instant_open(token: str) -> tuple[int, str, str]:
	symbol_id = int(CONFIG["SYMBOL_ID"])
	symbol_name = str(CONFIG.get("SYMBOL_NAME") or "").strip()
	if not symbol_name:
		raise ValueError("Missing CONFIG['SYMBOL_NAME'] (e.g. XRPUSDT)")
	symbol_info = fetch_symbol_info(symbol_id)
	price_precision = int(symbol_info.get("price_precision", 6))
	quantity_precision = int(symbol_info.get("quantity_precision", 6))

	muon_price = fetch_muon_price(symbol_id)

	# For LONG: buy slightly above; for SHORT: sell slightly below
	slippage = CONFIG["OPEN_SLIPPAGE"]
	if int(CONFIG["POSITION_TYPE"]) == 0:
		requested_price = muon_price * (Decimal("1") + slippage)
	else:
		requested_price = muon_price * (Decimal("1") - slippage)

	requested_price_str = format_decimal(requested_price, price_precision)
	quantity = Decimal(str(CONFIG["QUANTITY"]))
	quantity_str = format_decimal(quantity, quantity_precision)

	locked_params = fetch_locked_params(symbol_name, str(CONFIG["LEVERAGE"]))
	leverage = Decimal(str(locked_params.get("leverage", CONFIG["LEVERAGE"])))

	notional = Decimal(requested_price_str) * Decimal(quantity_str)
	normalized_cva = calculate_normalized_locked_value(notional, locked_params["cva"], leverage, True)
	normalized_lf = calculate_normalized_locked_value(notional, locked_params["lf"], leverage, True)
	normalized_party_amm = calculate_normalized_locked_value(notional, locked_params["partyAmm"], leverage, True)
	normalized_party_bmm = calculate_normalized_locked_value(notional, locked_params["partyBmm"], leverage, False)

	deadline = int(time.time()) + int(CONFIG["DEADLINE_OFFSET"])
	payload = {
		"symbolId": symbol_id,
		"positionType": int(CONFIG["POSITION_TYPE"]),
		"orderType": int(CONFIG["ORDER_TYPE"]),
		"price": requested_price_str,
		"quantity": quantity_str,
		"cva": normalized_cva,
		"lf": normalized_lf,
		"partyAmm": normalized_party_amm,
		"partyBmm": normalized_party_bmm,
		"maxFundingRate": str(CONFIG["MAX_FUNDING_RATE"]),
		"deadline": deadline,
	}

	headers = {
		"Content-Type": "application/json",
		"Authorization": f"Bearer {token}",
	}

	url = f"{PERPSHUB_BASE_URL}instant_open"
	print(f"[OPEN] POST {url}")
	print(f"[OPEN] Payload: {json.dumps(payload, indent=2)}")
	resp = requests.post(url, json=payload, headers=headers, timeout=30)
	print(f"[OPEN] Status={resp.status_code} Body={resp.text}")
	resp.raise_for_status()
	result = resp.json() or {}

	temp_quote_id = result.get("temp_quote_id") or result.get("quote_id")
	if temp_quote_id is None:
		raise ValueError(f"No temp_quote_id/quote_id in response: {result}")
	return int(temp_quote_id), requested_price_str, quantity_str


def poll_quote_status(token: str, temp_quote_id: int) -> int:
	"""Poll PerpsHub until we can determine a permanent quote_id.

	PerpsHub status: GET {base}/instant_open/{ACTIVE_ACCOUNT}
	"""

	headers = {"Authorization": f"Bearer {token}"}
	timeout_s = int(CONFIG["STATUS_TIMEOUT_SECONDS"])
	interval = float(CONFIG["STATUS_POLL_INTERVAL"])
	end_time = time.time() + timeout_s

	fallback_url = f"{PERPSHUB_BASE_URL}instant_open/{ACTIVE_ACCOUNT}"

	print(f"[STATUS] Waiting for confirmation: temp_quote_id={temp_quote_id}")
	attempt = 0
	while time.time() < end_time:
		attempt += 1
		quotes = None
		try:
			resp = requests.get(fallback_url, headers=headers, timeout=30)
			if resp.status_code == 200:
				data = resp.json()
				if isinstance(data, dict) and "quotes" in data:
					quotes = data.get("quotes")
				elif isinstance(data, list):
					quotes = data
			else:
				print(f"[STATUS] Attempt {attempt}: status={resp.status_code} body={resp.text}")
		except Exception as e:
			print(f"[STATUS] Attempt {attempt}: error polling ({e})")

		if not quotes:
			print(f"[STATUS] Attempt {attempt}: no quotes yet")
			time.sleep(interval)
			continue

		# Try: first match by temp_quote_id (if present), else any positive quote_id.
		for q in quotes:
			if not isinstance(q, dict):
				continue
			q_temp = q.get("temp_quote_id")
			qid = q.get("quote_id")

			try:
				if q_temp is not None and int(q_temp) == int(temp_quote_id):
					if qid is not None and int(qid) > 0:
						print(f"[STATUS] ✓ CONFIRMED (matched temp): quote_id={int(qid)}")
						return int(qid)
			except Exception:
				pass

		for q in quotes:
			if not isinstance(q, dict):
				continue
			qid = q.get("quote_id")
			try:
				if qid is not None and int(qid) > 0:
					print(f"[STATUS] ✓ CONFIRMED (any positive): quote_id={int(qid)}")
					return int(qid)
			except Exception:
				continue

		print(f"[STATUS] Attempt {attempt}: quotes present but not confirmed")
		time.sleep(interval)

	raise TimeoutError("Timed out waiting for a permanent quote_id")


def set_stop_loss(token: str, quote_id: int, requested_price_str: str) -> None:
	"""Set stop loss using the PerpsHub stop-loss endpoint.

	POST /stop_loss or /stop-loss
	Body:
	  userAddress, accountAddress, positionSide, symbolId, requestedPrice, quoteId, tpPrice, slPrice, timestamp
	"""

	symbol_id = int(CONFIG["SYMBOL_ID"])
	symbol_info = fetch_symbol_info(symbol_id)
	price_precision = int(symbol_info.get("price_precision", 6))

	current_price = fetch_muon_price(symbol_id)

	sl_pct = Decimal(str(CONFIG["SL_PCT"]))
	if int(CONFIG["POSITION_TYPE"]) == 0:
		sl_price = current_price * (Decimal("1") - sl_pct)
	else:
		sl_price = current_price * (Decimal("1") + sl_pct)
	sl_price_str = format_decimal(sl_price, price_precision)

	body = {
		"userAddress": wallet.address,
		"accountAddress": ACTIVE_ACCOUNT,
		"positionSide": int(CONFIG["POSITION_TYPE"]),
		"symbolId": symbol_id,
		"requestedPrice": str(requested_price_str),
		"quoteId": int(quote_id),
		"tpPrice": "",
		"slPrice": sl_price_str,
		"timestamp": int(time.time() * 1000),
	}

	headers = {
		"Content-Type": "application/json",
		"Authorization": f"Bearer {token}",
	}

	url_dash = f"{PERPSHUB_BASE_URL}stop-loss"
	url_underscore = f"{PERPSHUB_BASE_URL}stop_loss"

	print(f"[SL] Setting SL @ {sl_price_str} (current={current_price})")
	print(f"[SL] Payload: {json.dumps(body, indent=2)}")
	print(f"[SL] POST {url_dash}")
	resp = requests.post(url_dash, json=body, headers=headers, timeout=30)
	if resp.status_code == 404:
		print(f"[SL] 404 on /stop-loss, trying /stop_loss")
		resp = requests.post(url_underscore, json=body, headers=headers, timeout=30)

	print(f"[SL] Status={resp.status_code} Body={resp.text}")
	resp.raise_for_status()


def main():
	print("=" * 60)
	print("Majors (PerpsHub): Login -> Instant Open -> Stop Loss")
	print("=" * 60)
	print(f"EOA: {wallet.address}")
	print(f"Active account: {ACTIVE_ACCOUNT}")
	print(f"PerpsHub base: {PERPSHUB_BASE_URL}")
	print(f"SymbolId: {CONFIG['SYMBOL_ID']} (XRP)")
	print(f"PositionType: {CONFIG['POSITION_TYPE']} (0=LONG,1=SHORT)")
	print("=" * 60)

	try:
		token = login()
		print("✅ Logged in")

		temp_quote_id, requested_price_str, quantity_str = instant_open(token)
		print(f"✅ Open requested. temp_quote_id={temp_quote_id} price={requested_price_str} qty={quantity_str}")

		quote_id = poll_quote_status(token, temp_quote_id)
		print(f"✅ Confirmed. quote_id={quote_id}")

		set_stop_loss(token, quote_id, requested_price_str)
		print("✅ Stop loss set")

	except Exception as e:
		print(f"❌ Fatal error: {e}")
		traceback.print_exc()


if __name__ == "__main__":
	main()


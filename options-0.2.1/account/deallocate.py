from __future__ import annotations

import json
import os
from typing import Any, Dict

import requests
from dotenv import load_dotenv
from web3 import Web3


def _load_diamond_abi() -> list[dict]:
    abi_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "abi", "symmio.json"))
    with open(abi_path, "r", encoding="utf-8") as abi_file:
        return json.load(abi_file)


def _to_bytes(value: str) -> bytes:
    val = (value or "").strip()
    if not val:
        return b""
    if val.startswith("0x"):
        return Web3.to_bytes(hexstr=val)
    return val.encode("utf-8")


def _as_int(x: Any, default: int = 0) -> int:
    if x is None or x == "":
        return default
    if isinstance(x, int):
        return x
    if isinstance(x, str):
        # allow "0x..." or decimal strings
        try:
            return int(x, 16) if x.lower().startswith("0x") else int(x)
        except Exception:
            return default
    return default


def _fetch_muon(method: str, muon_base_url: str, params: Dict[str, str]) -> dict:
    # Muon endpoints typically look like:
    #   {MUON_BASE_URL}?app=symmio&method=uPnl_A&params[partyA]=...&params[chainId]=...&params[symmio]=...
    query = {"app": "symmio", "method": method}
    for k, v in params.items():
        query[f"params[{k}]"] = v

    resp = requests.get(muon_base_url, params=query, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success", False):
        raise RuntimeError(f"Muon error response: {payload}")
    return payload


def _format_upnl_sig(muon_payload: dict) -> Any:
    """
    Formats the Muon response into the ABI tuple shape expected by options-0.2.1 deallocate():
      (
        reqId: bytes,
        partyUpnl: int,
        counterPartyUpnl: int,
        collateralPrice: int,
        timestamp: int,
        gatewaySignature: bytes,
        (signature: int, owner: address, nonce: address)
      )
    """
    r = muon_payload.get("result", {})
    req_id = _to_bytes(r.get("reqId", ""))

    # Different Muon gateways nest values slightly differently; handle common layouts.
    data = r.get("data", {}) or {}
    data_result = data.get("result", {}) or {}

    # Try to read the newer fields; fall back to older "uPnl" layout.
    party_upnl = _as_int(data_result.get("partyUpnl", None), default=_as_int(data_result.get("uPnl", "0")))
    counter_upnl = _as_int(data_result.get("counterPartyUpnl", "0"))
    collateral_price = _as_int(data_result.get("collateralPrice", "0"))
    timestamp = _as_int(data.get("timestamp", None), default=_as_int(data_result.get("timestamp", "0")))

    # Node/gateway signature
    gateway_sig = r.get("nodeSignature") or r.get("gatewaySignature") or ""
    gateway_sig_bytes = _to_bytes(gateway_sig)

    # Schnorr signature bundle
    sigs0 = (r.get("signatures") or [{}])[0]
    sig_hex_or_int = sigs0.get("signature", 0)
    signature_int = _as_int(sig_hex_or_int, default=0)
    owner = Web3.to_checksum_address(sigs0.get("owner", "0x0000000000000000000000000000000000000000"))

    # Nonce address usually comes from data.init.nonceAddress (as in your 0.8.4 script)
    init_obj = data.get("init", {}) or {}
    nonce_addr = Web3.to_checksum_address(init_obj.get("nonceAddress", "0x0000000000000000000000000000000000000000"))

    return (
        req_id,
        int(party_upnl),
        int(counter_upnl),
        int(collateral_price),
        int(timestamp),
        gateway_sig_bytes,
        (int(signature_int), owner, nonce_addr),
    )


def main() -> None:
    load_dotenv()

    rpc_url = os.getenv("RPC_URL")
    private_key = os.getenv("PRIVATE_KEY")
    diamond_address = os.getenv("SYMMIO_DIAMOND_ADDRESS") or os.getenv("DIAMOND_ADDRESS")
    collateral_address = os.getenv("COLLATERAL_ADDRESS")
    counter_party = os.getenv("COUNTERPARTY_ADDRESS") or os.getenv("PARTY_B_ADDRESS")
    is_party_b = (os.getenv("IS_PARTY_B", "false").strip().lower() in {"1", "true", "yes"})

    chain_id_str = os.getenv("CHAIN_ID", "0") or "0"
    chain_id = int(chain_id_str)

    muon_base_url = os.getenv("MUON_BASE_URL", "https://polygon-testnet-oracle.rasa.capital/v1/")
    muon_method = os.getenv("MUON_METHOD")  # optional override
    if not muon_method:
        # Deployment-specific method name (per user): upnl_a
        muon_method = "upnl_a"

    if not rpc_url or not private_key or not diamond_address or not collateral_address or not counter_party:
        raise SystemExit(
            "Missing env vars: RPC_URL, PRIVATE_KEY, DIAMOND_ADDRESS (or SYMMIO_DIAMOND_ADDRESS), COLLATERAL_ADDRESS, "
            "COUNTERPARTY_ADDRESS (or PARTY_B_ADDRESS)"
        )

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    account = w3.eth.account.from_key(private_key)

    diamond = w3.eth.contract(address=Web3.to_checksum_address(diamond_address), abi=_load_diamond_abi())

    amount = int(os.getenv("AMOUNT_WEI", str(w3.to_wei(1, "ether"))))

    # Build Muon params. For PartyA flows, partyA=caller. For PartyB flows, partyA=counterParty.
    party_a = Web3.to_checksum_address(counter_party) if is_party_b else account.address
    muon_params = {
        "partyA": party_a,
        "chainId": str(chain_id),
        "symmio": Web3.to_checksum_address(diamond_address),
    }
    # Some deployments also expect "collateral"; harmless if ignored by the gateway.
    muon_params["collateral"] = Web3.to_checksum_address(collateral_address)

    print(f"Fetching Muon signature: method={muon_method} partyA={party_a} chainId={chain_id} symmio={diamond_address}")
    muon_payload = _fetch_muon(muon_method, muon_base_url, muon_params)
    upnl_sig = _format_upnl_sig(muon_payload)

    # deallocate(collateral, counterParty, amount, isPartyB, upnlSig)
    tx = diamond.functions.deallocate(
        Web3.to_checksum_address(collateral_address),
        Web3.to_checksum_address(counter_party),
        amount,
        is_party_b,
        upnl_sig,
    ).build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address, "pending"),
            "gasPrice": w3.eth.gas_price,
            **({"chainId": chain_id} if chain_id else {}),
            # IMPORTANT: set gas here to avoid estimateGas revert masking the real error
            "gas": int(os.getenv("GAS", "600000")),
        }
    )

    signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"deallocate tx sent: {tx_hash.hex()}")


if __name__ == "__main__":
    main()
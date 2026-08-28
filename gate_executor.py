# ============================================================
#  gate_executor.py – Eksekusi order ke Gate.io Futures TESTNET
#  [UPDATE] konsolidasi kredensial ke config.py (single source of truth)
#  secrets_testnet.py sudah tidak dipakai lagi mulai sekarang.
# ============================================================
import logging
from gate_api import ApiClient, Configuration, FuturesApi, FuturesOrder
from gate_api.exceptions import ApiException, GateApiException

from config import GATE_TESTNET_API_KEY, GATE_TESTNET_API_SECRET, GATE_TESTNET_HOST, EXECUTE_TESTNET

logger = logging.getLogger(__name__)

SETTLE = "usdt"  # settle currency untuk USDT-margined futures contracts

_configuration = Configuration(
    host=GATE_TESTNET_HOST,
    key=GATE_TESTNET_API_KEY,
    secret=GATE_TESTNET_API_SECRET,
)
_api_client = ApiClient(_configuration)
_futures_api = FuturesApi(_api_client)


def get_account_balance():
    """Ambil info akun futures testnet (balance, margin, unrealized PnL, dll)."""
    try:
        account = _futures_api.list_futures_accounts(settle=SETTLE)
        result = {
            "total": account.total,
            "available": account.available,
            "currency": account.currency,
            "unrealised_pnl": account.unrealised_pnl,
            "position_margin": account.position_margin,
            "order_margin": account.order_margin,
        }
        logger.info(f"[gate_executor] Testnet account balance OK: {result}")
        return {"ok": True, "data": result}
    except GateApiException as e:
        logger.error(f"[gate_executor] GateApiException: label={e.label}, message={e.message}")
        return {"ok": False, "error": f"Gate API error: {e.label} - {e.message}"}
    except ApiException as e:
        logger.error(f"[gate_executor] ApiException: {e}")
        return {"ok": False, "error": f"API error: {e}"}
    except Exception as e:
        logger.error(f"[gate_executor] Unexpected error: {e}")
        return {"ok": False, "error": f"Unexpected error: {e}"}


def place_order(symbol: str, signal: str, size: float, sl: float = None, tp: float = None, reduce_only: bool = False):
    """
    Eksekusi market order ke Gate.io Futures TESTNET berdasarkan sinyal scanner.

    symbol : contoh "BTC_USDT" (Gate.io pakai underscore, bukan "BTCUSDT")
    signal : "BUY" atau "SELL" (atau string sinyal panjang dari scanner, cukup
             deteksi awalannya)
    size   : ukuran kontrak. POSITIF untuk long/BUY, NEGATIF untuk short/SELL
             (kalau kamu kasih size positif untuk SELL, kita otomatis balik jadi negatif)

    Return: dict {"ok": True, "data": {...}} atau {"ok": False, "error": "..."}
    """
    if not EXECUTE_TESTNET and not reduce_only:
        logger.warning(f"[gate_executor] EXECUTE_TESTNET=False, order TIDAK dikirim (dry-run). {symbol} {signal} size={size}")
        return {"ok": False, "error": "EXECUTE_TESTNET is False — set True di config.py untuk eksekusi beneran"}

    gate_symbol = symbol.replace("USDT", "_USDT") if "_" not in symbol else symbol
    is_buy = str(signal).upper().startswith("BUY")
    final_size = abs(size) if is_buy else -abs(size)

    try:
        order = FuturesOrder(
            contract=gate_symbol,
            size=int(final_size),
            price="0",       # "0" = market order
            tif="ioc",        # immediate-or-cancel, dipakai untuk market order
            reduce_only=reduce_only,
        )
        result = _futures_api.create_futures_order(SETTLE, order)
        logger.info(f"[gate_executor] Order berhasil: {gate_symbol} size={final_size} id={result.id}")
        return {
            "ok": True,
            "data": {
                "id": result.id,
                "contract": result.contract,
                "size": result.size,
                "status": result.status,
                "fill_price": result.fill_price,
            },
        }
    except GateApiException as e:
        logger.error(f"[gate_executor] Order GAGAL: label={e.label}, message={e.message}")
        return {"ok": False, "error": f"Gate API error: {e.label} - {e.message}"}
    except ApiException as e:
        logger.error(f"[gate_executor] Order ApiException: {e}")
        return {"ok": False, "error": f"API error: {e}"}
    except Exception as e:
        logger.error(f"[gate_executor] Order unexpected error: {e}")
        return {"ok": False, "error": f"Unexpected error: {e}"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = get_account_balance()
    print(result)


def get_contract_specs(symbol):
    """Ambil spesifikasi contract (multiplier, min/max size) dari Gate.io."""
    gate_symbol = symbol.replace("USDT", "_USDT") if "_" not in symbol else symbol
    try:
        c = _futures_api.get_futures_contract(SETTLE, gate_symbol)
        return {
            "quanto_multiplier": float(c.quanto_multiplier),
            "order_size_min": c.order_size_min,
            "order_size_max": c.order_size_max,
        }
    except Exception as e:
        logger.error(f"[gate_executor] Gagal ambil contract specs {gate_symbol}: {e}")
        return None


def usd_to_contracts(symbol, usd_amount, price):
    """Konversi nominal USD -> jumlah contract (integer) sesuai spesifikasi pair."""
    specs = get_contract_specs(symbol)
    if not specs or price <= 0 or specs["quanto_multiplier"] <= 0:
        return 0
    size = int(usd_amount / (price * specs["quanto_multiplier"]))
    size = max(size, specs["order_size_min"])
    if specs.get("order_size_max"):
        size = min(size, specs["order_size_max"])
    return size


def execute_signal(sig: dict):
    """
    Terima dict sinyal (symbol, signal, entry, position_size dalam USD)
    dan eksekusi market order REAL ke Gate.io Futures Testnet.
    """
    symbol   = sig.get("symbol")
    signal   = sig.get("signal", "")
    entry    = sig.get("entry", 0)
    usd_size = sig.get("position_size", 0)

    if not symbol or entry <= 0 or usd_size <= 0:
        return {"ok": False, "error": f"Data sinyal tidak lengkap: symbol={symbol} entry={entry} size={usd_size}"}

    contracts = usd_to_contracts(symbol, usd_size, entry)
    if contracts <= 0:
        return {"ok": False, "error": f"Contract size terhitung 0 (usd={usd_size}, entry={entry})"}

    return place_order(symbol, signal, size=contracts)

# ============================================================
#  gate_executor.py – Eksekusi order ke Gate.io Futures TESTNET
#  [UPDATE] konsolidasi kredensial ke config.py (single source of truth)
#  secrets_testnet.py sudah tidak dipakai lagi mulai sekarang.
# ============================================================
import logging
from gate_api import ApiClient, Configuration, FuturesApi, FuturesOrder
from gate_api.exceptions import ApiException, GateApiException

from gate_api import FuturesInitialOrder, FuturesPriceTrigger, FuturesPriceTriggeredOrder
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



def set_leverage(symbol: str, leverage: int):
    """Set leverage untuk sebuah contract SEBELUM buka posisi. [FIX 2026-09-25]
    Sebelumnya tidak pernah dipanggil sama sekali -- bot akan pakai leverage
    default/terakhir yang di-set manual di akun, bukan dikontrol dari sini.
    Ini bahaya kalau akun kebetulan ter-set leverage tinggi tanpa disadari."""
    gate_symbol = symbol.replace("USDT", "_USDT") if "_" not in symbol else symbol
    try:
        result = _futures_api.update_position_leverage(SETTLE, gate_symbol, str(leverage))
        logger.info(f"[gate_executor] Leverage {gate_symbol} diset ke {leverage}x")
        return {"ok": True, "data": result}
    except (GateApiException, ApiException) as e:
        logger.error(f"[gate_executor] Gagal set leverage {gate_symbol}: {e}")
        return {"ok": False, "error": str(e)}


def place_sl_order(symbol: str, is_buy: bool, sl_price: float):
    """Pasang stop-loss di SISI EXCHANGE (price-triggered order), bukan cuma
    dipantau dari exit_monitor.py. [FIX 2026-09-25] Sebelumnya place_order()
    TIDAK PERNAH mengirim SL ke exchange sama sekali -- kalau bot/HP mati,
    koneksi putus, atau app force-close, posisi terbuka TANPA proteksi apapun.
    rule=2 (harga <= trigger) untuk BUY, rule=1 (harga >= trigger) untuk SELL --
    keduanya trigger saat harga bergerak ke ARAH RUGI dari posisi."""
    gate_symbol = symbol.replace("USDT", "_USDT") if "_" not in symbol else symbol
    rule = 2 if is_buy else 1
    try:
        initial = FuturesInitialOrder(
            contract=gate_symbol, size=0, price="0", tif="ioc", close=True,
        )
        trigger = FuturesPriceTrigger(
            strategy_type=0, price_type=0, price=str(sl_price),
            rule=rule, expiration=86400,
        )
        order = FuturesPriceTriggeredOrder(initial=initial, trigger=trigger)
        result = _futures_api.create_price_triggered_order(SETTLE, order)
        logger.info(f"[gate_executor] SL terpasang di exchange: {gate_symbol} @ {sl_price}")
        return {"ok": True, "data": {"id": result.id}}
    except (GateApiException, ApiException) as e:
        logger.error(f"[gate_executor] Gagal pasang SL exchange {gate_symbol}: {e}")
        return {"ok": False, "error": str(e)}

def place_order(symbol: str, signal: str, size: float, sl: float = None, tp: float = None, reduce_only: bool = False, leverage: int = 2):
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

    if not reduce_only:
        lev_result = set_leverage(symbol, leverage)
        if not lev_result.get("ok"):
            logger.error(f"[gate_executor] Gagal set leverage, order DIBATALKAN (fail-safe): {lev_result.get('error')}")
            return {"ok": False, "error": f"Gagal set leverage, order dibatalkan: {lev_result.get('error')}"}

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

        sl_result = None
        if sl is not None and not reduce_only:
            sl_result = place_sl_order(symbol, is_buy, sl)
            if sl_result.get("ok"):
                logger.info(f"[gate_executor] SL terpasang setelah order: {gate_symbol} @ {sl}")
            else:
                logger.error(f"[gate_executor] PERINGATAN: order market BERHASIL tapi SL GAGAL dipasang! {gate_symbol} error={sl_result.get('error')}")

        return {
            "ok": True,
            "data": {
                "id": result.id,
                "contract": result.contract,
                "size": result.size,
                "status": result.status,
                "fill_price": result.fill_price,
                "sl_order": sl_result,
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
    # [FIX 2026-09-25] Sebelumnya max(size, order_size_min) MEMAKSA posisi
    # naik ke minimum exchange kalau hasil kalkulasi lebih kecil -- untuk
    # modal kecil ini bisa bikin posisi jauh lebih besar dari rencana risk.
    # Sekarang: kalau di bawah minimum, TOLAK (return 0), jangan dipaksa naik.
    if size < specs["order_size_min"]:
        return 0
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
    sl       = sig.get("sl")
    tp       = sig.get("tp")
    leverage = sig.get("leverage", 2)

    if not symbol or entry <= 0 or usd_size <= 0:
        return {"ok": False, "error": f"Data sinyal tidak lengkap: symbol={symbol} entry={entry} size={usd_size}"}

    contracts = usd_to_contracts(symbol, usd_size, entry)
    if contracts <= 0:
        return {"ok": False, "error": f"Contract size terhitung 0 (usd={usd_size}, entry={entry})"}

    return place_order(symbol, signal, size=contracts, sl=sl, tp=tp, leverage=leverage)

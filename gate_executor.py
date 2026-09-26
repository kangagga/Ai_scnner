# ============================================================
#  gate_executor.py – Eksekusi order ke Gate.io Futures TESTNET
#  [UPDATE] konsolidasi kredensial ke config.py (single source of truth)
#  secrets_testnet.py sudah tidak dipakai lagi mulai sekarang.
# ============================================================
import logging
from gate_api import ApiClient, Configuration, FuturesApi, FuturesOrder
from gate_api.exceptions import ApiException, GateApiException

from gate_api import FuturesInitialOrder, FuturesPriceTrigger, FuturesPriceTriggeredOrder
from config import GATE_TESTNET_API_KEY, GATE_TESTNET_API_SECRET, GATE_TESTNET_HOST, EXECUTE_TESTNET, LIVE_ACCOUNT_BALANCE, LIVE_LEVERAGE

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


def _round_to_tick(symbol: str, price: float) -> float:
    """Bulatkan harga ke tick size (order_price_round) yang valid untuk contract ini.
    [FIX 2026-09-26] Ditemukan lewat testing testnet: Gate.io menolak trigger
    price yang bukan kelipatan tick size contract (error AUTO_INVALID_PARAM_TRIGGER_PRICE).
    Tick size beda-beda per pair (ETH_USDT=0.05, dll), jadi harus dicek dari API,
    bukan diasumsikan/hardcode."""
    gate_symbol = symbol.replace("USDT", "_USDT") if "_" not in symbol else symbol
    try:
        c = _futures_api.get_futures_contract(SETTLE, gate_symbol)
        tick = float(c.order_price_round)
        if tick > 0:
            rounded = round(price / tick) * tick
            # Hindari floating point residue (misal 2610.0000000004)
            decimals = max(0, len(str(tick).split(".")[-1])) if "." in str(tick) else 0
            return round(rounded, decimals)
    except (GateApiException, ApiException) as e:
        logger.warning(f"[gate_executor] Gagal ambil tick size {gate_symbol}, pakai harga asli: {e}")
    return price


def place_sl_order(symbol: str, is_buy: bool, sl_price: float):
    """Pasang stop-loss di SISI EXCHANGE (price-triggered order), bukan cuma
    dipantau dari exit_monitor.py. [FIX 2026-09-25] Sebelumnya place_order()
    TIDAK PERNAH mengirim SL ke exchange sama sekali -- kalau bot/HP mati,
    koneksi putus, atau app force-close, posisi terbuka TANPA proteksi apapun.
    rule=2 (harga <= trigger) untuk BUY, rule=1 (harga >= trigger) untuk SELL --
    keduanya trigger saat harga bergerak ke ARAH RUGI dari posisi."""
    gate_symbol = symbol.replace("USDT", "_USDT") if "_" not in symbol else symbol
    rule = 2 if is_buy else 1
    sl_price = _round_to_tick(symbol, sl_price)
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

def get_open_position(symbol: str):
    """Baca posisi AKTUAL yang lagi terbuka di Gate.io untuk symbol ini.
    [ADD 2026-09-25] Dipakai sebagai dasar hitungan partial-close (TP1/TP2/TP3)
    supaya persentase yang ditutup dihitung dari ukuran posisi SEBENARNYA di
    exchange, bukan dari catatan lokal bot yang bisa saja sudah tidak sinkron.
    Return: {"ok": True, "data": {"size": int, "entry_price": float, ...}} atau
    {"ok": True, "data": None} kalau tidak ada posisi terbuka, atau {"ok": False, "error": ...}."""
    gate_symbol = symbol.replace("USDT", "_USDT") if "_" not in symbol else symbol
    try:
        pos = _futures_api.get_position(SETTLE, gate_symbol)
        size = int(pos.size)
        if size == 0:
            return {"ok": True, "data": None}
        return {
            "ok": True,
            "data": {
                "size": size,
                "entry_price": float(pos.entry_price) if pos.entry_price else None,
                "leverage": pos.leverage,
                "unrealised_pnl": float(pos.unrealised_pnl) if pos.unrealised_pnl else None,
            },
        }
    except (GateApiException, ApiException) as e:
        logger.error(f"[gate_executor] Gagal baca posisi {gate_symbol}: {e}")
        return {"ok": False, "error": str(e)}


def close_position_partial(symbol: str, pct_closed: float):
    """Tutup SEBAGIAN posisi yang lagi terbuka di Gate.io (reduce-only market order).
    [ADD 2026-09-25] Dipakai untuk TP1/TP2/TP3 partial-close. pct_closed dihitung
    dari ukuran posisi AKTUAL (lewat get_open_position()), bukan dari catatan lokal.

    symbol     : contoh "BTC_USDT"
    pct_closed : persentase dari SISA posisi sekarang yang mau ditutup (0-100)

    Return: {"ok": True, "data": {...}} atau {"ok": False, "error": "..."}
    """
    if pct_closed <= 0 or pct_closed > 100:
        return {"ok": False, "error": f"pct_closed tidak valid: {pct_closed} (harus 0-100)"}

    pos_result = get_open_position(symbol)
    if not pos_result.get("ok"):
        return {"ok": False, "error": f"Gagal baca posisi sebelum partial-close: {pos_result.get('error')}"}

    pos_data = pos_result.get("data")
    if not pos_data:
        return {"ok": False, "error": f"Tidak ada posisi terbuka untuk {symbol}, tidak ada yang bisa ditutup"}

    current_size = pos_data["size"]  # positif = long, negatif = short
    is_long = current_size > 0

    close_size = int(round(abs(current_size) * (pct_closed / 100.0)))
    if close_size <= 0:
        return {"ok": False, "error": f"Ukuran hasil hitung 0 (posisi={current_size}, pct={pct_closed})"}
    if close_size > abs(current_size):
        close_size = abs(current_size)  # safety cap, jangan pernah lebih dari posisi aktual

    # Untuk close: kalau posisi LONG, kirim size NEGATIF (jual). Kalau SHORT, size POSITIF (beli balik).
    order_size = -close_size if is_long else close_size

    return place_order(
        symbol,
        signal="SELL" if is_long else "BUY",
        size=abs(order_size),
        reduce_only=True,
    )


def update_sl_order(symbol: str, is_buy: bool, new_sl_price: float):
    """Geser SL yang sudah terpasang di exchange ke harga baru (trailing stop /
    breakeven). [FIX 2026-09-26 v3] Gate.io TIDAK MENDUKUNG update in-place untuk
    trigger order (SL) yang dibuat lewat API -- dikonfirmasi via error resmi server
    code 1077 APIOrderNotSupportUpdateTouchOrder (bukan bug versi library/path).
    Solusi: cancel SL lama, baru pasang SL baru (bukan amend). Kalau cancel
    berhasil tapi pasang baru gagal, di-retry otomatis sekali; kalau tetap gagal,
    posisi jadi TANPA SL SAMA SEKALI dan ditandai lewat sl_removed=True di return.

    symbol       : contoh "BTC_USDT"
    is_buy       : True untuk posisi LONG, False untuk SHORT
    new_sl_price : harga SL baru (hasil trailing/breakeven dari exit_monitor)

    Return: {"ok": True, "data": {...}} atau
            {"ok": False, "error": "...", "sl_removed": bool}
            sl_removed=True berarti SL LAMA SUDAH DIBATALKAN dan SL baru GAGAL
            dipasang (2x percobaan) -- posisi TANPA proteksi, butuh tindakan segera.
    """
    gate_symbol = symbol.replace("USDT", "_USDT") if "_" not in symbol else symbol
    try:
        open_orders = _futures_api.list_price_triggered_orders(SETTLE, status="open", contract=gate_symbol)
    except (GateApiException, ApiException) as e:
        logger.error(f"[gate_executor] Gagal ambil daftar trigger order {gate_symbol}: {e}")
        return {"ok": False, "error": f"Gagal ambil daftar SL lama: {e}"}

    if not open_orders:
        logger.warning(f"[gate_executor] Tidak ada trigger order aktif untuk {gate_symbol}, pasang SL baru dari nol")
        return place_sl_order(symbol, is_buy, new_sl_price)

    old_order_id = open_orders[0].id

    try:
        _futures_api.cancel_price_triggered_order(SETTLE, old_order_id)
        logger.info(f"[gate_executor] SL lama dibatalkan: {gate_symbol} order_id={old_order_id}")
    except (GateApiException, ApiException) as e:
        logger.error(f"[gate_executor] Gagal cancel SL lama {gate_symbol} order_id={old_order_id}: {e} -- SL lama kemungkinan masih aktif (aman)")
        return {"ok": False, "error": f"Gagal cancel SL lama: {e}"}
    except ValueError as e:
        # [FIX 2026-09-26] Bug dikenal di library gate_api: response DELETE dari
        # testnet kadang berisi field pos_margin_mode dengan nilai tidak valid
        # (misal "|single"), bikin parsing model Python crash SETELAH request
        # DELETE sendiri sudah diterima server. Jangan asumsikan sukses ATAU
        # gagal dari exception ini saja -- verifikasi langsung ke server.
        logger.warning(f"[gate_executor] cancel_price_triggered_order lempar ValueError saat parsing response (kemungkinan bug pos_margin_mode, request DELETE kemungkinan sudah sukses): {e} -- memverifikasi manual...")
        try:
            still_open = _futures_api.list_price_triggered_orders(SETTLE, status="open", contract=gate_symbol)
        except (GateApiException, ApiException) as e2:
            logger.critical(f"[gate_executor] Tidak bisa verifikasi status SL lama {gate_symbol} order_id={old_order_id} setelah ValueError: {e2}")
            return {"ok": False, "error": f"Cancel SL lama tidak bisa diverifikasi setelah ValueError ({e}), dan verifikasi juga gagal ({e2}). Status SL lama TIDAK DIKETAHUI, cek manual sebelum lanjut."}
        still_exists = any(str(o.id) == str(old_order_id) for o in still_open)
        if still_exists:
            logger.error(f"[gate_executor] Verifikasi: SL lama {gate_symbol} order_id={old_order_id} MASIH AKTIF, cancel gagal beneran (bukan cuma bug parsing)")
            return {"ok": False, "error": f"Cancel SL lama gagal (order_id={old_order_id} masih terdaftar aktif setelah percobaan cancel)"}
        logger.info(f"[gate_executor] Verifikasi: SL lama {gate_symbol} order_id={old_order_id} sudah tidak ada di server (cancel sebenarnya berhasil, ValueError cuma bug parsing) -- lanjut pasang SL baru")

    new_result = place_sl_order(symbol, is_buy, new_sl_price)
    if new_result.get("ok"):
        logger.info(f"[gate_executor] SL berhasil digeser (cancel+recreate): {gate_symbol} order_id_baru={new_result['data']['id']} @ {new_sl_price}")
        return new_result

    logger.error(f"[gate_executor] BAHAYA: SL lama sudah dibatalkan tapi SL baru GAGAL dipasang! {gate_symbol}. Retry sekali... error={new_result.get('error')}")
    retry_result = place_sl_order(symbol, is_buy, new_sl_price)
    if retry_result.get("ok"):
        logger.info(f"[gate_executor] Retry berhasil, SL terpasang: {gate_symbol} order_id_baru={retry_result['data']['id']} @ {new_sl_price}")
        return retry_result

    logger.critical(f"[gate_executor] RETRY JUGA GAGAL. Posisi {gate_symbol} SEKARANG TANPA SL SAMA SEKALI. error_pertama={new_result.get('error')} error_retry={retry_result.get('error')}")
    return {
        "ok": False,
        "sl_removed": True,
        "error": (
            f"SL LAMA SUDAH DIBATALKAN DAN SL BARU GAGAL DIPASANG (2x percobaan). "
            f"Posisi {gate_symbol} TANPA SL SEKARANG. Error awal: {new_result.get('error')} | "
            f"Error retry: {retry_result.get('error')}"
        ),
    }


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
            "order_size_min": int(c.order_size_min),
            "order_size_max": int(c.order_size_max) if c.order_size_max else None,
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


def scale_to_live_size(paper_position_size: float, paper_capital: float = 100.0) -> float:
    """Skalakan position_size dari paper trading (asumsi modal $100) ke modal
    LIVE asli (LIVE_ACCOUNT_BALANCE). [ADD 2026-09-25]
    Proporsi antar sinyal tetap sama, cuma diskalakan turun ke modal real."""
    if paper_capital <= 0:
        return 0.0
    return paper_position_size * (LIVE_ACCOUNT_BALANCE / paper_capital)


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

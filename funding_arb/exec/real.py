import os, time, json
import ccxt
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BINANCE_USDM_API_KEY")
API_SECRET = os.getenv("BINANCE_USDM_API_SECRET")

class BinanceUSDM_TestnetTrader:
    """
    Thin wrapper over ccxt.binanceusdm for TESTNET.
    - Places post-only limit (maker) or market (taker) orders
    - Waits up to deadline for maker fills; if not, cancels and crosses
    """
    def __init__(self):
        if not API_KEY or not API_SECRET:
            raise RuntimeError("Set BINANCE_USDM_API_KEY / BINANCE_USDM_API_SECRET in .env")
        self.ex = ccxt.binanceusdm({
            "apiKey": API_KEY,
            "secret": API_SECRET,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
        self.ex.set_sandbox_mode(True)           # testnet
        self.ex.load_markets(reload=True)

    # ---------- helpers ----------
    def _ensure_symbol(self, symbol: str):
        if symbol not in self.ex.markets:
            self.ex.load_markets(reload=True)
            if symbol not in self.ex.markets:
                avail = ", ".join(list(self.ex.symbols)[:10])
                raise ccxt.BadSymbol(f"Symbol {symbol} not found on Binance USDM testnet. "
                                     f"First few available: {avail} ...")

    def _min_notional_usdt(self, symbol: str, ref_price: float) -> float:
        """
        Compute a conservative min notional requirement:
        - Use exchange min amount * price if available
        - Enforce Binance testnet opening-floor of ~20 USDT
        """
        m = self.ex.market(symbol)
        min_amt = (m.get("limits", {}).get("amount", {}) or {}).get("min") or 0.0
        approx = float(min_amt) * float(ref_price) if (min_amt and ref_price) else 0.0
        # Testnet opening orders floor (reduce-only may be below this):
        floor = 20.0
        return max(approx, floor)

    def _qty_from_notional(self, symbol: str, price: float, notional_usdt: float) -> float:
        self._ensure_symbol(symbol)
        if price <= 0:
            raise ValueError("price must be > 0")
        # amount respecting min amount, then precision
        m = self.ex.market(symbol)
        min_amt = (m.get("limits", {}).get("amount", {}) or {}).get("min") or 0.0
        qty = max(notional_usdt / price, float(min_amt))
        qty = float(self.ex.amount_to_precision(symbol, qty))
        if qty < float(min_amt):
            qty = float(min_amt)
            qty = float(self.ex.amount_to_precision(symbol, qty))
        return max(qty, 0.0)

    def _post_only_params(self, reduce_only: bool):
        return {"postOnly": True, "timeInForce": "GTX", "reduceOnly": reduce_only}

    def _market_params(self, reduce_only: bool):
        return {"reduceOnly": reduce_only}

    # ---------- public ----------
    def best_bid_ask(self, symbol: str):
        self._ensure_symbol(symbol)
        ob = self.ex.fetch_order_book(symbol, limit=5)
        bid = ob["bids"][0][0] if ob["bids"] else None
        ask = ob["asks"][0][0] if ob["asks"] else None
        return bid, ask

    def set_leverage(self, symbol: str, leverage: int = 1):
        try:
            self._ensure_symbol(symbol)
            self.ex.set_leverage(leverage, symbol)
        except Exception:
            pass

    def execute_action(self, action: int, symbol: str, side: str, notional_usdt: float,
                       deadline_ms: int = 800, reduce_only: bool = False):
        """
        action: 0 maker_inside, 1 post_only_edge, 2 taker_now, 3 wait (no-op)
        side: "buy" or "sell"
        """
        self._ensure_symbol(symbol)

        if action == 3:  # wait
            return {"status": "noop", "price": None, "order": None}

        bid, ask = self.best_bid_ask(symbol)
        if not (bid and ask):
            return {"status": "no_book", "price": None, "order": None}
        mid = (bid + ask) / 2.0

        # choose order type/price
        if action == 2:  # taker_now
            order_type = "market"
            price = None
            params = self._market_params(reduce_only)
        else:
            order_type = "limit"
            if side == "buy":
                px = bid + (ask - bid) * (0.5 if action == 0 else 0.0)
            else:
                px = ask - (ask - bid) * (0.5 if action == 0 else 0.0)
            price = float(px)
            params = self._post_only_params(reduce_only)

        # ensure notional meets exchange min
        min_notional = self._min_notional_usdt(symbol, (price or mid))
        if notional_usdt < min_notional and not reduce_only:
            print(f"[note] bumping notional from {notional_usdt:.2f} to {min_notional:.2f} USDT to satisfy min notional")
            notional_usdt = min_notional

        qty = self._qty_from_notional(symbol, (price or mid), notional_usdt)
        if qty <= 0:
            return {"status": "qty_zero", "price": None, "order": None}

        # try place once; on -4164, retry at 25 USDT
        def _place(order_type, side, qty, price, params):
            try:
                return self.ex.create_order(symbol, order_type, side, qty, price, params), None
            except Exception as e:
                return None, e

        o, err = _place(order_type, side, qty, price, params)
        if err:
            msg = str(err)
            if "code\":-4164" in msg and not reduce_only:
                bump = max(25.0, min_notional + 5.0)
                print(f"[note] retrying due to -4164 with notional={bump:.2f} USDT")
                qty = self._qty_from_notional(symbol, (price or mid), bump)
                o, err = _place(order_type, side, qty, price, params)
            if err:
                return {"status": f"order_error: {msg}", "price": None, "order": None}

        # market: done
        if order_type == "market":
            try:
                info = self.ex.fetch_order(o["id"], symbol)
                avg = info.get("average") or info.get("price") or (ask if side == "buy" else bid)
            except Exception:
                avg = (ask if side == "buy" else bid)
            return {"status": "filled", "price": float(avg), "order": o, "mid": mid}

        # maker: wait briefly, then cross if not filled
        t_end = time.time() + (deadline_ms / 1000.0)
        while time.time() < t_end:
            try:
                info = self.ex.fetch_order(o["id"], symbol)
                filled = float(info.get("filled") or 0.0)
                if filled > 0:
                    avg = info.get("average") or price
                    return {"status": "filled", "price": float(avg), "order": o, "mid": mid}
            except Exception:
                pass
            time.sleep(0.15)

        try:
            self.ex.cancel_order(o["id"], symbol)
        except Exception:
            pass

        try:
            o2 = self.ex.create_order(symbol, "market", side, qty, None, self._market_params(reduce_only))
            info2 = self.ex.fetch_order(o2["id"], symbol)
            avg2 = info2.get("average") or (ask if side == "buy" else bid)
            return {"status": "filled_after_cross", "price": float(avg2), "order": o2, "mid": mid}
        except Exception as e:
            return {"status": f"cross_error: {e}", "price": None, "order": None}
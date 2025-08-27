import sqlite3

def main():
    con = sqlite3.connect("funding_arb.db")
    cur = con.cursor()

    def count(tbl):
        try:
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            return cur.fetchone()[0]
        except sqlite3.OperationalError:
            return 0

    ft = count("funding_ticks")
    st = count("signal_ticks")
    ps = count("position_snaps")
    print("funding_ticks:", ft)
    print("signal_ticks:", st)
    print("position_snaps:", ps)

    if ft > 0:
        cur.execute("SELECT AVG(bps_day_net) FROM funding_ticks")
        avg_bpsd = cur.fetchone()[0] or 0.0
        print(f"\navg net bps/day: {avg_bpsd:.2f}")

    if st > 0:
        print("\nsignal distribution:")
        try:
            cur.execute("SELECT decision, COUNT(*) FROM signal_ticks GROUP BY decision ORDER BY COUNT(*) DESC")
            for dec, c in cur.fetchall():
                print(f"  {dec}: {c}")
        except sqlite3.OperationalError:
            pass

    if ps > 0:
        cur.execute("SELECT AVG(est_pnl_usdt) FROM position_snaps WHERE is_open=1")
        inpos = cur.fetchone()[0]
        print(f"\navg est pnl while open (USDT): {0.0 if inpos is None else inpos:.6f}")

    con.close()

if __name__ == "__main__":
    main()
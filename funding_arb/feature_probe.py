import sqlite3, json
from funding_arb.ml.features import FeatureBuilder

def main():
    fb = FeatureBuilder()
    con = sqlite3.connect("funding_arb.db")
    cur = con.cursor()
    cur.execute("SELECT ts_ms, bid_px, bid_sz, ask_px, ask_sz FROM lob_snapshots ORDER BY ts_ms ASC LIMIT 400")
    rows = cur.fetchall()
    con.close()

    printed = 0
    for ts_ms, bid_px, bid_sz, ask_px, ask_sz in rows:
        # SQLite stores JSON as text; if needed, parse
        if isinstance(bid_px, str):
            bid_px = json.loads(bid_px)
            bid_sz = json.loads(bid_sz)
            ask_px = json.loads(ask_px)
            ask_sz = json.loads(ask_sz)
        feats = fb.push_and_compute(ts_ms, bid_px, ask_px, bid_sz, ask_sz, last_action=0)
        if feats and printed < 10:
            print(feats)
            printed += 1

if __name__ == "__main__":
    main()
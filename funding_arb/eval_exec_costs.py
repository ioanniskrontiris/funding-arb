import sqlite3

def main():
    con = sqlite3.connect("funding_arb.db")
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM exec_outcomes")
    n = cur.fetchone()[0]
    print("rows in exec_outcomes:", n)
    if n == 0:
        print("No data yet. Run exec_demo first.")
        return

    # avg cost per action
    print("\nAverage realized execution cost (bps) by action:")
    print("0=maker_inside, 1=post_only_edge, 2=taker_now, 3=wait")
    for a in (0,1,2,3):
        cur.execute("SELECT AVG(realized_cost_bps) FROM exec_outcomes WHERE action=?", (a,))
        avg = cur.fetchone()[0]
        print(f"action {a}: {avg:.3f} bps" if avg is not None else f"action {a}: no samples")
    con.close()

if __name__ == "__main__":
    main()
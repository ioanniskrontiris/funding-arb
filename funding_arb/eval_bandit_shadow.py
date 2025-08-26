import sqlite3

def main():
    con = sqlite3.connect("funding_arb.db")
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM bandit_shadow")
    n = cur.fetchone()[0]
    print("bandit_shadow rows:", n)
    if n == 0:
        print("No shadow data. Run bandit_shadow_demo first.")
        return

    # Simple sanity: avg baseline cost (bandit learns from it)
    cur.execute("SELECT AVG(realized_cost_bps) FROM bandit_shadow")
    avg_cost = cur.fetchone()[0]
    print(f"Avg baseline realized cost (bps): {avg_cost:.3f}")

    # Action distribution suggested by bandit
    print("Bandit suggested action distribution:")
    for a in (0,1,2,3):
        cur.execute("SELECT COUNT(*) FROM bandit_shadow WHERE action_bandit=?", (a,))
        c = cur.fetchone()[0]
        print(f"  action {a}: {c}")

    con.close()

if __name__ == "__main__":
    main()
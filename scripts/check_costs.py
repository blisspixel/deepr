import sqlite3

conn = sqlite3.connect('.deepr/queue.db')
c = conn.cursor()

rows = c.execute('SELECT id, status, cost FROM research_queue ORDER BY submitted_at DESC').fetchall()
print("Recent jobs:")
for r in rows[:10]:
    cost_str = f"${r[2]:.4f}" if r[2] else "$0.00"
    print(f"{r[0][:8]} | {r[1]:12} | {cost_str}")

total = c.execute('SELECT SUM(cost) FROM research_queue WHERE cost IS NOT NULL').fetchone()[0]
print(f"\nTotal cost in DB: ${total if total else 0}")

conn.close()

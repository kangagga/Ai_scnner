#!/usr/bin/env python3
import sqlite3
import sys

if len(sys.argv) < 2:
    print("Usage: python3 query.py 'SQL QUERY'")
    sys.exit(1)

conn = sqlite3.connect('/home/userland/ai-scanner/signals.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute(sys.argv[1])
rows = cur.fetchall()

if rows:
    # print header
    print("|".join(rows[0].keys()))
    for row in rows:
        print("|".join(str(x) for x in row))
else:
    print("(no rows)")

conn.close()

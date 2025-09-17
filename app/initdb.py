import sqlite3

conn = sqlite3.connect("data/conso.db")
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS conso (
        timestamp TEXT PRIMARY KEY,
        watts INTEGER
    )
""")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS coupures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        start TEXT,
        end TEXT
    )
""")

conn.commit()
conn.close()
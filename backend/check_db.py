import sqlite3
conn = sqlite3.connect('eduscan.db')
print([r[0] for r in conn.execute(
    'SELECT name FROM sqlite_master WHERE type=\'table\'').fetchall()])

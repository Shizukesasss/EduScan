import sqlite3

conn = sqlite3.connect('data/eduscan.db')
cursor = conn.cursor()
cursor.execute('SELECT id, first_name, surname, middle_name, name_extension FROM persons')
rows = cursor.fetchall()
for row in rows:
    person_id, first, surname, middle, ext = row
    
    parts = []
    if surname:
        parts.append(surname + ",")
    parts.append(first)
    if middle:
        parts.append(f"{middle.strip()[0].upper()}.")
    if ext:
        parts.append(ext)
    
    full_name = " ".join(parts).strip()
    cursor.execute('UPDATE persons SET full_name = ? WHERE id = ?', (full_name, person_id))

conn.commit()
conn.close()
print("Updated all full_names")

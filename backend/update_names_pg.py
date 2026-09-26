import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import engine, SessionLocal
from app.models import Person

db = SessionLocal()
persons = db.query(Person).all()

for person in persons:
    parts = []
    if person.surname:
        parts.append(person.surname.strip() + ",")
    if person.first_name:
        parts.append(person.first_name.strip())
    if person.middle_name and person.middle_name.strip():
        parts.append(f"{person.middle_name.strip()[0].upper()}.")
    if person.name_extension and person.name_extension.strip():
        parts.append(person.name_extension.strip())
        
    person.full_name = " ".join(parts).strip()

db.commit()
db.close()
print(f"Updated {len(persons)} persons.")

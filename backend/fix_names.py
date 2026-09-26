import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from app.database import engine, SessionLocal
from app.models import Person

db = SessionLocal()
persons = db.query(Person).all()

for person in persons:
    if not person.surname:
        # We need to parse first_name
        name = person.first_name.strip()
        
        if ',' in name:
            # Format: Surname, First Name Middle Initial
            parts = [p.strip() for p in name.split(',', 1)]
            person.surname = parts[0]
            rest = parts[1].split(' ')
            if len(rest) > 1 and rest[-1].endswith('.'):
                person.middle_name = rest[-1].replace('.', '')
                person.first_name = ' '.join(rest[:-1])
            else:
                person.first_name = parts[1]
        else:
            # Format: First Name Surname
            parts = name.split(' ')
            if len(parts) > 1:
                person.surname = parts[-1]
                person.first_name = ' '.join(parts[:-1])
            else:
                person.first_name = name
    
    # Reconstruct full_name
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
print("Names parsed and updated successfully.")

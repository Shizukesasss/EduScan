import sys
sys.path.append('.')
from app.database import SessionLocal
from app.models import Subject

db = SessionLocal()
mapeh = db.query(Subject).filter(Subject.name == 'MAPEH').first()
if mapeh:
    mapeh.active = False
    db.commit()
    print("Successfully deactivated the old MAPEH subject.")
else:
    print("Old MAPEH subject not found.")

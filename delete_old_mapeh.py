import sys
sys.path.append('.')
from app.database import SessionLocal
from app.models import Subject, Gradebook

db = SessionLocal()

# Find the general MAPEH subject (not the sub-subjects)
mapeh = db.query(Subject).filter(Subject.name == 'MAPEH').first()
if mapeh:
    print(f"Found subject: {mapeh.name} (ID: {mapeh.id})")
    
    # Find any gradebooks associated with this subject
    books = db.query(Gradebook).filter(Gradebook.subject_id == mapeh.id).all()
    print(f"Found {len(books)} old MAPEH gradebooks to delete.")
    
    for b in books:
        db.delete(b)
    
    # Delete the subject itself
    db.delete(mapeh)
    
    db.commit()
    print("Successfully deleted the old MAPEH subject and its gradebooks.")
else:
    print("Old MAPEH subject not found.")

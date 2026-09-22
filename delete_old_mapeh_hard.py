import sys
sys.path.append('.')
from app.database import SessionLocal
from app.models import Subject, Gradebook, GradebookAuditEntry
from app.models_grading import GradebookComponent

db = SessionLocal()

mapeh = db.query(Subject).filter(Subject.name == 'MAPEH').first()
if not mapeh:
    print("No old MAPEH subject found.")
    sys.exit(0)

books = db.query(Gradebook).filter(Gradebook.subject_id == mapeh.id).all()
print(f'Found {len(books)} old MAPEH gradebooks.')

for b in books:
    # Delete audit entries
    db.query(GradebookAuditEntry).filter(GradebookAuditEntry.gradebook_id == b.id).delete()
    # Let cascade handle the rest (gradebook_components have ondelete CASCADE, etc.)
    db.delete(b)

# Finally delete the subject
db.delete(mapeh)

db.commit()
print('Successfully deleted old MAPEH gradebooks and the subject entirely.')

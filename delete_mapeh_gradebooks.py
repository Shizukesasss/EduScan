import sys
sys.path.append('.')
from app.database import SessionLocal
from app.models import Gradebook
from app.models_grading import GradingPolicy

db = SessionLocal()

# Find all MAPEH gradebooks
books = db.query(Gradebook).filter(Gradebook.subject_name.like('MAPEH - %')).all()
print(f"Found {len(books)} MAPEH gradebooks.")

# Find the correct policy
policy = db.query(GradingPolicy).filter(GradingPolicy.id == 3).first()
print(f"Found policy: {policy.name} (ID: {policy.id})")

# Delete existing gradebooks
for b in books:
    db.delete(b)
db.commit()
print("Deleted existing MAPEH gradebooks.")

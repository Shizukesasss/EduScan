import sys
sys.path.append('.')
from app.database import SessionLocal
from app.models import Gradebook
from app.models_grading import GradebookComponent

db = SessionLocal()

# Find all MAPEH gradebooks
books = db.query(Gradebook).filter(Gradebook.subject_name.like('MAPEH - %')).all()
print(f"Updating {len(books)} MAPEH gradebooks...")

for b in books:
    # Update policy ID to 3 (MAPEH policy)
    b.grading_policy_id = 3
    
    # Update components
    components = db.query(GradebookComponent).filter(GradebookComponent.gradebook_id == b.id).all()
    for c in components:
        if "Written Work" in c.name:
            c.weight = 20.0
        elif "Performance" in c.name:
            c.weight = 60.0
        elif "Quarterly" in c.name:
            c.weight = 20.0

db.commit()
print("Done! MAPEH gradebooks updated to 20/60/20 computation.")

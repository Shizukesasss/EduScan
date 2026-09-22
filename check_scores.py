import sys
sys.path.append('.')
from app.database import SessionLocal
from app.services.grading import get_gradebook_full

db = SessionLocal()
for gbid in [103, 104, 105, 106]:
    full = get_gradebook_full(db, gbid)
    items = []
    for c in full["components"]:
        for i in c.get("items", []):
            items.append(i["id"])
    
    print("Gradebook " + str(gbid) + ":")
    print("Item IDs: " + str(items))
    
    for s in full["students"]:
        if s.get("scores"):
            print("Student scores: " + str(s["scores"]))
            break

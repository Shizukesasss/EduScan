import sys
import json
sys.path.append('.')
from app.database import SessionLocal
from app.models_grading import GradingPolicy
db = SessionLocal()
policies = db.query(GradingPolicy).all()
for p in policies:
    print(f"Policy: {p.name} (ID: {p.id})")
    for c in json.loads(p.component_definitions_json):
        print(f"  - {c.get('name')}: {c.get('weight')}%")

import re

with open("backend/app/services/reports.py", "r", encoding="utf-8") as f:
    original = f.read()

with open("new_func.py", "r", encoding="utf-8") as f:
    new_func = f.read()

# Find the start of the function
start_marker = "def generate_gradebook_report_xlsx(db: Session, gradebook_id: int, region: str = \"\", division: str = \"\", school_id: str = \"\") -> Path:"
start_idx = original.find(start_marker)

# Find the end of the function (the return statement)
end_marker = "    return target"
end_idx = original.find(end_marker, start_idx) + len(end_marker)

if start_idx == -1 or end_idx < len(end_marker):
    print("Could not find function bounds!")
else:
    new_content = original[:start_idx] + new_func + original[end_idx:]
    with open("backend/app/services/reports.py", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Successfully replaced generate_gradebook_report_xlsx!")

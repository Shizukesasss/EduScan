import urllib.request
import json
import sys

def main():
    # 1. Login to get token
    login_data = json.dumps({"username": "admin", "password": "admin123"}).encode('utf-8')
    req = urllib.request.Request("http://127.0.0.1:8000/api/auth/login", data=login_data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            token = json.loads(response.read().decode())['access_token']
    except Exception as e:
        print("Login failed:", e)
        sys.exit(1)

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    # 2. Get Academic Structure to get grade levels, sections, etc.
    req = urllib.request.Request("http://127.0.0.1:8000/api/admin/academic-structure?context=grading", headers=headers)
    with urllib.request.urlopen(req) as response:
        struct = json.loads(response.read().decode())

    school_years = struct['school_years']
    grading_periods = struct['grading_periods']
    sections = struct['sections']

    # Active Grades 7 to 10
    target_grade_names = ["7", "8", "9", "10"]
    target_grades = [g for g in struct['grade_levels'] if str(g['name']).replace('Grade ', '').strip() in target_grade_names and g['active']]
    target_grade_ids = [g['id'] for g in target_grades]

    print(f"Target grade IDs (7-10): {target_grade_ids}")

    # 3. Create MAPEH Subjects
    new_subjects = [
        {"code": "MAPEH-MUSIC", "name": "MAPEH - MUSIC", "active": True},
        {"code": "MAPEH-ARTS", "name": "MAPEH - ARTS", "active": True},
        {"code": "MAPEH-PE", "name": "MAPEH - PE", "active": True},
        {"code": "MAPEH-HEALTH", "name": "MAPEH - HEALTH", "active": True},
    ]

    for sub in new_subjects:
        # Check if already exists
        if any(s['code'] == sub['code'] for s in struct['subjects']):
            print(f"Subject {sub['code']} already exists.")
            continue
        req = urllib.request.Request("http://127.0.0.1:8000/api/admin/subjects", data=json.dumps(sub).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                print("Created subject:", sub['name'])
        except urllib.error.HTTPError as e:
             if e.code == 409:
                 print(f"Subject {sub['code']} exists (conflict)")
             else:
                 print(f"Failed to create {sub['code']}: {e.read().decode()}")

    # Fetch structure again to get the new subject IDs
    req = urllib.request.Request("http://127.0.0.1:8000/api/admin/academic-structure?context=grading", headers=headers)
    with urllib.request.urlopen(req) as response:
        struct = json.loads(response.read().decode())

    mapeh_subjects = [s for s in struct['subjects'] if s['code'].startswith('MAPEH-')]
    print(f"Found {len(mapeh_subjects)} MAPEH subjects: {[s['name'] for s in mapeh_subjects]}")

    # 4. Create Gradebooks
    created = 0
    errors = 0
    for sy in school_years:
        for gp in [g for g in grading_periods if g['school_year_id'] == sy['id']]:
            for sec in sections:
                if sec['grade_level_id'] in target_grade_ids:
                    for subj in mapeh_subjects:
                        payload = {
                            "school_year_id": sy['id'],
                            "grading_period_id": gp['id'],
                            "grade_level_id": sec['grade_level_id'],
                            "section_id": sec['id'],
                            "subject_id": subj['id'],
                            "grading_policy_id": None
                        }
                        try:
                            req = urllib.request.Request("http://127.0.0.1:8000/api/gradebooks", data=json.dumps(payload).encode(), headers=headers)
                            with urllib.request.urlopen(req) as response:
                                created += 1
                                print(f"Created gradebook for {sy['name']} Q{gp['quarter']} Section {sec['name']} {subj['name']}")
                        except Exception as e:
                            errors += 1
                            print(f"Error creating gradebook for {sy['name']} Q{gp['quarter']} Section {sec['name']} {subj['name']}: {e}")

    print(f"\nDone! Successfully requested creation of {created} gradebooks. Errors: {errors}")

if __name__ == "__main__":
    main()

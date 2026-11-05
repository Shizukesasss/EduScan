import os
import sys
from pathlib import Path

# Set up paths so we can import from app
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert
from app.models import User, Person
from app.config import settings

def migrate_data():
    print("Connecting to local SQLite database...")
    engine_sqlite = create_engine("sqlite:///./data/eduscan.db")
    SessionLocalSQLite = sessionmaker(autocommit=False, autoflush=False, bind=engine_sqlite)
    
    print("Connecting to Supabase PostgreSQL database...")
    engine_pg = create_engine(settings.database_url)
    SessionLocalPG = sessionmaker(autocommit=False, autoflush=False, bind=engine_pg)
    
    db_sqlite = SessionLocalSQLite()
    db_pg = SessionLocalPG()
    
    try:
        # Migrate Users
        print("Migrating Users...")
        sqlite_users = db_sqlite.query(User).all()
        for u in sqlite_users:
            # Check if user already exists in PG
            existing = db_pg.query(User).filter(User.username == u.username).first()
            if not existing:
                print(f" -> Migrating user: {u.username} ({u.full_name})")
                new_user = User(
                    username=u.username,
                    password_hash=u.password_hash,
                    role=u.role,
                    full_name=u.full_name,
                    active=u.active,
                    must_change_password=u.must_change_password,
                    failed_login_count=u.failed_login_count,
                )
                db_pg.add(new_user)
            else:
                print(f" -> User {u.username} already exists in Supabase. Skipping.")
        
        # Migrate Persons (Students, etc)
        print("Migrating Persons (Students & Teachers)...")
        sqlite_persons = db_sqlite.query(Person).all()
        for p in sqlite_persons:
            # We can match by external_id or full_name
            existing = db_pg.query(Person).filter(
                (Person.external_id == p.external_id) if p.external_id else (Person.full_name == p.full_name)
            ).first()
            
            if not existing:
                print(f" -> Migrating person: {p.full_name} (Role: {p.role})")
                new_person = Person(
                    external_id=p.external_id,
                    lrn=p.lrn,
                    full_name=p.full_name,
                    surname=p.surname,
                    first_name=p.first_name,
                    middle_name=p.middle_name,
                    name_extension=p.name_extension,
                    sex=p.sex,
                    role=p.role,
                    grade=p.grade,
                    section=p.section,
                    guardian_phone=p.guardian_phone,
                    biometric_consent=p.biometric_consent,
                    active=p.active,
                    enrollment_status=p.enrollment_status,
                )
                db_pg.add(new_person)
            else:
                print(f" -> Person {p.full_name} already exists in Supabase. Skipping.")
                
        print("Committing changes to Supabase...")
        db_pg.commit()
        print("Migration complete!")
        
    except Exception as e:
        print("Error during migration:", e)
        db_pg.rollback()
    finally:
        db_sqlite.close()
        db_pg.close()

if __name__ == "__main__":
    migrate_data()

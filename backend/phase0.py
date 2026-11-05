import time
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DATABASE_URL', 'sqlite:///./data/eduscan.db')
os.environ.setdefault('EDUSCAN_SECRET_KEY', 'demo-seed-secret-change-before-production')
os.environ.setdefault('BIOMETRIC_ENABLED', 'true')

from app.database import engine, SessionLocal
from sqlalchemy import event, text
from app.services.biometrics import biometric_service
from app.services.attendance import record_gate_match

query_count = 0
query_time = 0.0

@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.perf_counter()

@event.listens_for(engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    global query_count, query_time
    total = time.perf_counter() - context._query_start_time
    query_count += 1
    query_time += total

def run_phase0():
    global query_count, query_time
    db = SessionLocal()
    
    # 1. Measure DB Ping
    t0 = time.perf_counter()
    db.execute(text('SELECT 1'))
    db_ping = (time.perf_counter() - t0) * 1000

    # reset counters
    query_count = 0
    query_time = 0.0

    # 2. Simulate recognize_many (Scan path)
    try:
        with open('dummy.jpg', 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x0a\x00\x00\x00\x0a\x08\x02\x00\x00\x00\x02P\x15X\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe\x0c\x83\xa3\x00\x00\x00\x00IEND\xaeB`\x82')
        with open('dummy.jpg', 'rb') as f:
            frame_bytes = f.read()
    except:
        frame_bytes = b''

    print("--- Phase 0 Measurements ---")
    print(f"DB Round-trip latency (ping): {db_ping:.2f}ms")

    t_start = time.perf_counter()
    matches = biometric_service.recognize_many(db, frame_bytes)
    t_recognize = time.perf_counter() - t_start

    print(f"recognize_many time: {t_recognize*1000:.2f}ms")
    print(f"Queries during recognize_many: {query_count}")
    print(f"DB time inside recognize_many: {query_time*1000:.2f}ms")
    
    db.close()

if __name__ == "__main__":
    run_phase0()

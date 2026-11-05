import os
import sys
from pathlib import Path
import cv2
import numpy as np
from sqlalchemy import select

# Add backend directory to sys.path to import app modules
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Person, BiometricSample
from app.services.biometrics import biometric_service

def run_diagnostics():
    print("=== LBPH Diagnostic Tool ===")
    
    db = SessionLocal()
    try:
        persons = db.scalars(select(Person)).all()
        if not persons:
            print("No enrolled persons found in the database.")
            return

        for person in persons:
            samples = db.scalars(select(BiometricSample).where(BiometricSample.person_id == person.id)).all()
            if not samples:
                continue
                
            print(f"\n--- Checking Person: {person.full_name} ({len(samples)} samples) ---")
            
            for i, sample in enumerate(samples):
                encrypted_path = Path(sample.encrypted_path)
                if not encrypted_path.exists():
                    print(f"  [!] Missing file: {encrypted_path}")
                    continue
                    
                # Decrypt the sample image
                try:
                    encrypted_data = encrypted_path.read_bytes()
                    decrypted_data = biometric_service.fernet.decrypt(encrypted_data)
                    array = np.frombuffer(decrypted_data, dtype=np.uint8)
                    image = cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)
                    
                    if image is None:
                        print(f"  [{i+1}/{len(samples)}] [!] Failed to decode image: {sample.id}")
                        continue
                        
                    # 1. Size check
                    size_status = "OK" if image.shape == (200, 200) else f"FAIL {image.shape}"
                    
                    # 2. Brightness & Blur (Laplacian variance)
                    brightness = float(image.mean())
                    blur = float(cv2.Laplacian(image, cv2.CV_64F).var())
                    
                    print(f"  [{i+1}/{len(samples)}] Size: {size_status} | Brightness: {brightness:.1f} | Blur Var: {blur:.1f} | Score: {sample.quality_score}%")
                    
                    # (Optional) Display the image - Press any key to continue, 'q' to quit
                    # Uncomment these lines if running on a machine with a GUI
                    cv2.imshow(f"Enrolled Sample - {person.full_name}", image)
                    key = cv2.waitKey(0)
                    if key == ord('q'):
                        cv2.destroyAllWindows()
                        return
                        
                except Exception as e:
                    print(f"  [{i+1}/{len(samples)}] [!] Error processing sample: {e}")
                    
    finally:
        db.close()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    run_diagnostics()

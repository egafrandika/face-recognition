"""
Test script for PayrollFace API - no camera required.
Uses a sample face image generated with dlib's face generator or any local image.

Usage:
  python test_api.py register     # Register a test employee
  python test_api.py masuk        # Clock in
  python test_api.py pulang       # Clock out
  python test_api.py [image_path] # Use a specific face photo for all tests
"""

import sys
import os
import json
import base64
import requests
import numpy as np
from PIL import Image
import io

API_BASE = "http://localhost:5000"

def image_to_base64(img: Image.Image) -> str:
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    b64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"

def load_test_image(path=None):
    if path:
        return Image.open(path).convert("RGB")

    try:
        from urllib.request import urlopen
        url = "https://thispersondoesnotexist.com"
        print(f"Downloading random face from {url}...")
        data = urlopen(url).read()
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as e:
        print(f"Could not download face image: {e}")
        print("Generating a blank placeholder (face detection may fail)...")
        return Image.new("RGB", (400, 400), (200, 180, 160))

def test_register(image_b64):
    print("\n--- Register Employee ---")
    resp = requests.post(f"{API_BASE}/api/v1/face/register", json={
        "nama": "Test Karyawan",
        "gaji_pokok": 8500000,
        "tunjangan_tipe": "staff",
        "image": image_b64
    })
    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")

def test_verify(image_b64, absensi_type="Masuk"):
    print(f"\n--- Verify Attendance ({absensi_type}) ---")
    resp = requests.post(f"{API_BASE}/api/v1/verify-liveness", json={
        "image": image_b64,
        "type": absensi_type
    })
    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")

if __name__ == "__main__":
    image_path = None
    action = "all"

    for arg in sys.argv[1:]:
        if arg in ("register", "masuk", "pulang"):
            action = arg
        else:
            image_path = arg

    if not image_path:
        default = os.path.join(os.path.dirname(__file__), "test_images", "test_face.jpg")
        if os.path.exists(default):
            image_path = default

    img = load_test_image(image_path)
    image_b64 = image_to_base64(img)
    print(f"Image loaded ({img.size[0]}x{img.size[1]})")

    if action == "register":
        test_register(image_b64)
    elif action == "masuk":
        test_verify(image_b64, "Masuk")
    elif action == "pulang":
        test_verify(image_b64, "Pulang")
    else:
        test_register(image_b64)
        test_verify(image_b64, "Masuk")
        test_verify(image_b64, "Pulang")

import sys
import os

# Add project root to sys.path (script moved to scripts/ subdirectory)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from db import db
import model

with app.app_context():
    db.create_all()
    print(" All tables created successfully!")
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import init_db

if __name__ == "__main__":
    init_db()
    print("Database initialized with WAL mode and schema.")
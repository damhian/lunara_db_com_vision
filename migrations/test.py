import sys
import os

# Dynamically add the project root to `sys.path`
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import Base  # This import should now work
print(Base.metadata.tables)

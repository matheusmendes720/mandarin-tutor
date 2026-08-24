"""Test configuration for lingua package."""
import sys
from pathlib import Path

# Add project root to Python path so 'src.lingua' imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

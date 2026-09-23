import os
import sys

# Services live at the project root, not in a package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

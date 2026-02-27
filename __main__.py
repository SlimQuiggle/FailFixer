"""Allow running as: python -m failfixer"""
import sys
from .app.main import main

sys.exit(main())

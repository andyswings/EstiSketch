#!/usr/bin/env python3
import sys
import os

# Add the src directory to the python path so we can resolve the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from EstiSketch.main import main

if __name__ == "__main__":
    main()


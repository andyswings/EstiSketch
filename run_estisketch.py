#!/usr/bin/env python3
"""
Entry point wrapper for PyInstaller.
This allows main.py to use relative imports.
"""

if __name__ == '__main__':
    from EstiSketch import main
    main.main()

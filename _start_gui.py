"""Start CRUX GUI Cockpit"""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ui.gui_server import main

asyncio.run(main())

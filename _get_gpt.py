import asyncio
import os
import sys

os.chdir(r"C:\Users\huangjiancheng\agnes-smart-studio")
sys.path.insert(0, ".")
from chatgpt_reply_fetcher import fetch_reply_already_generated


async def main():
    reply = await fetch_reply_already_generated()
    print(reply)

asyncio.run(main())

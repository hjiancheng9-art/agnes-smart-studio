import asyncio
import os
import sys

os.chdir(r"C:\Users\huangjiancheng\agnes-smart-studio")
sys.path.insert(0, ".")
from chatgpt_reply_fetcher import fetch_reply_already_generated


async def main():
    try:
        reply = await fetch_reply_already_generated()
        print("========== GPT 回复 ==========")
        print(reply)
        print("========== 结束 ==========")
    except Exception as e:
        print(f"失败: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(main())

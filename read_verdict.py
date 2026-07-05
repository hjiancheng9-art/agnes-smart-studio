import sys
with open('output/chatgpt_p5_verdict.txt', 'rb') as f:
    data = f.read()
sys.stdout.buffer.write(data)
sys.stdout.flush()

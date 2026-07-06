import sys
with open('_gpt_msg16.txt', encoding='utf-8') as f:
    text = f.read()

# Print with manual chunking
chunk_size = 1500
for i in range(0, len(text), chunk_size):
    chunk = text[i:i+chunk_size]
    print(f"--- CHUNK {i//chunk_size} ({i}-{i+len(chunk)}) ---")
    print(chunk)
    print()

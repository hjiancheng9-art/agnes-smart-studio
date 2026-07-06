with open("ui_match_result.txt", encoding="utf-8") as f:
    content = f.read()
chunk_size = 2000
for i in range(0, len(content), chunk_size):
    print(content[i:i+chunk_size])
    print("---CHUNK---")

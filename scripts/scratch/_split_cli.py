"""One-shot: replace self-command methods in cli.py with delegation calls."""

path = 'C:/Users/huangjiancheng/CodeBuddy/crux-smart-studio/ui/cli.py'
with open(path, encoding='utf-8') as f:
    content = f.read()

# Marker: find the _self_heal definition
marker = '    def _self_heal(self, session: "ChatSession"):'
idx_start = content.find(marker)
if idx_start < 0:
    print("_self_heal not found")
    exit(1)

# Find the _self_diagnose definition (comes after _self_evolve)
diag_marker = '    def _self_diagnose(self, session: "ChatSession", arg: str):'
idx_diag = content.find(diag_marker, idx_start)
if idx_diag < 0:
    print("_self_diagnose not found")
    exit(1)

# Find _chat_matrix
matrix_marker = '    def _chat_matrix(self, session: "ChatSession"):'
idx_matrix = content.find(matrix_marker, idx_diag)
if idx_matrix < 0:
    print("_chat_matrix not found")
    exit(1)

# Find _chat_evolve (comes after _chat_matrix)
evolve_marker = '    def _chat_evolve(self, session: "ChatSession"):'
idx_evolve = content.find(evolve_marker, idx_matrix)
if idx_evolve < 0:
    print("_chat_evolve not found")
    exit(1)

# Old block: from _self_heal to just before _chat_evolve
old_block = content[idx_start:idx_evolve]
print(f"Old block: {len(old_block)} chars ({old_block.count(chr(10))} lines)")

# New block: delegation calls
new_block = '''    def _self_heal(self, session: "ChatSession"):
        from ui.self_commands import cmd_self_heal
        cmd_self_heal(self, session)

    def _self_evolve(self, session: "ChatSession"):
        from ui.self_commands import cmd_self_evolve
        cmd_self_evolve(self, session)

    def _self_diagnose(self, session: "ChatSession", arg: str):
        from ui.self_commands import cmd_self_diagnose
        cmd_self_diagnose(self, session, arg)

    def _chat_matrix(self, session: "ChatSession"):
        from ui.self_commands import cmd_self_matrix
        cmd_self_matrix(self, session)

'''
print(f"New block: {len(new_block)} chars ({new_block.count(chr(10))} lines)")

# Replace
new_content = content[:idx_start] + new_block + content[idx_evolve:]
with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"Saved: {len(content)} -> {len(new_content)} chars (saved {len(content)-len(new_content)})")

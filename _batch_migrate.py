"""Batch migrate subprocess.run -> run_subprocess across all remaining files."""
import re, ast, sys

FILES = [
    # (filepath, import_path)
    ('core/claude_mcp_bridge.py', 'core.mcp_servers._mcp_utils'),
    ('core/codex_tools.py', 'core.mcp_servers._mcp_utils'),
    ('core/copilot_tools.py', 'core.mcp_servers._mcp_utils'),
    ('core/three_way_coordinator.py', 'core.mcp_servers._mcp_utils'),
    ('core/skills.py', 'core.mcp_servers._mcp_utils'),
    ('core/file_tools.py', 'core.mcp_servers._mcp_utils'),
    ('core/sound_ux.py', 'core.mcp_servers._mcp_utils'),
    ('core/browser_tools.py', 'core.mcp_servers._mcp_utils'),
    ('core/code_review.py', 'core.mcp_servers._mcp_utils'),
    ('core/github_tools.py', 'core.mcp_servers._mcp_utils'),
    ('core/test_loop.py', 'core.mcp_servers._mcp_utils'),
    ('core/background.py', 'core.mcp_servers._mcp_utils'),
    ('core/git_workflow.py', 'core.mcp_servers._mcp_utils'),
    ('launcher.py', 'core.mcp_servers._mcp_utils'),
    ('core/audio_tools.py', 'core.mcp_servers._mcp_utils'),
]

def get_indent(line):
    return line[:len(line) - len(line.lstrip())]

def build_run_subprocess(node, source_lines):
    """Build the run_subprocess replacement call from an AST Call node."""
    first_line = source_lines[node.lineno - 1]
    indent = get_indent(first_line)
    
    # Get the prefix before subprocess.run( (e.g., "r = " or "return ")
    idx = first_line.index('subprocess.run(')
    prefix = first_line[:idx]
    
    args_parts = []
    for arg in node.args:
        args_parts.append(ast.get_source_segment('\n'.join(source_lines), arg))
    
    kwargs_parts = []
    for kw in node.keywords:
        v = ast.get_source_segment('\n'.join(source_lines), kw.value)
        if kw.arg in ('capture_output',):
            continue  # default True
        elif kw.arg in ('text',):
            continue  # default True
        elif kw.arg in ('encoding',):
            continue  # default utf-8
        elif kw.arg in ('errors',):
            continue  # default replace
        elif kw.arg == 'cwd':
            kwargs_parts.append(f"cwd={v}")
        elif kw.arg == 'timeout':
            kwargs_parts.append(f"timeout={v}")
        elif kw.arg == 'input':
            kwargs_parts.append(f"input_data={v}")
        elif kw.arg == 'env':
            extra = re.sub(r'^\{\s*\*\*os\.environ\s*,\s*', '{', v)
            kwargs_parts.append(f"env_add={extra}")
        elif kw.arg in ('shell', 'check'):
            if v != 'False':
                kwargs_parts.append(f"{kw.arg}={v}")
        elif kw.arg == 'stdin':
            kwargs_parts.append(f"stdin={v}")
        elif kw.arg == 'startupinfo':
            kwargs_parts.append(f"startupinfo={v}")
        else:
            kwargs_parts.append(f"{kw.arg}={v}")
    
    new_call = prefix + "run_subprocess("
    all_parts = args_parts + kwargs_parts
    new_call += ", ".join(all_parts)
    new_call += ")"
    return new_call, node.lineno - 1, node.end_lineno

for filepath, import_path in FILES:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
    except FileNotFoundError:
        continue
    
    source_lines = source.split('\n')
    
    # Parse twice: first check syntax, then find calls
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"SKIP {filepath}: syntax error before migration: {e}")
        continue
    
    # Find all subprocess.run calls
    nodes = []
    class FindCalls(ast.NodeVisitor):
        def visit_Call(self, node):
            if (isinstance(node.func, ast.Attribute) and 
                isinstance(node.func.value, ast.Name) and 
                node.func.value.id == 'subprocess' and 
                node.func.attr == 'run'):
                nodes.append(node)
            self.generic_visit(node)
    FindCalls().visit(tree)
    
    if not nodes:
        continue
    
    # Build replacements (sorted by end_lineno descending)
    replacements = []
    for node in nodes:
        new_call, start_idx, end_idx = build_run_subprocess(node, source_lines)
        replacements.append((start_idx, end_idx, new_call))
    
    replacements.sort(key=lambda x: x[1], reverse=True)
    
    # Apply replacements
    new_lines = list(source_lines)
    for start_idx, end_idx, new_call in replacements:
        new_lines[start_idx:end_idx] = [new_call]
    
    new_source = '\n'.join(new_lines)
    
    # Verify AST
    try:
        ast.parse(new_source)
    except SyntaxError as e:
        print(f"FAIL {filepath}: syntax after migration: L{e.lineno}: {e.msg}")
        # Show context
        err_lines = new_source.split('\n')
        for i in range(max(0, e.lineno-3), min(len(err_lines), e.lineno+2)):
            print(f"  {i+1}: {err_lines[i]}")
        continue
    
    # Add import if not present
    if 'run_subprocess' in new_source and f'from {import_path} import' not in new_source:
        import_line = f"from {import_path} import run_subprocess"
        nl = new_source.split('\n')
        last_import_idx = -1
        for i, line in enumerate(nl):
            if re.match(r'^(import\s+|from\s+\S+\s+import\s+)', line):
                last_import_idx = i
        nl.insert(last_import_idx + 1, import_line)
        new_source = '\n'.join(nl)
        
        try:
            ast.parse(new_source)
        except SyntaxError as e:
            print(f"FAIL {filepath}: import syntax error: {e}")
            continue
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_source)
    
    sr = new_source.count('subprocess.run(')
    rs = new_source.count('run_subprocess(')
    print(f"OK {filepath}: {sr} remaining, {rs} new")

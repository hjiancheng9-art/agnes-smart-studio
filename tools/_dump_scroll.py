with open('ui/message_pane.py', encoding='utf-8') as f:
    lines = f.readlines()
# Write _scroll method + scroll_up/scroll_down methods to a temp file
with open('ui/_scroll_methods.txt', 'w', encoding='utf-8') as out:
    in_method = False
    for i, l in enumerate(lines):
        if 'def _scroll(' in l or 'def scroll_up' in l or 'def scroll_down' in l or \
           'def scroll_page_up' in l or 'def scroll_page_down' in l:
            in_method = True
        if in_method:
            out.write(f"{i+1:4d}: {l}")
            # Check if next line is a new method (not indented)
            if i+1 < len(lines) and lines[i+1].strip() and not lines[i+1].startswith((' ', '\t')):
                if l.strip().startswith('def ') and 'scroll_' in l:
                    pass  # continue, same method
                elif l.strip().startswith('def ') and i > 0:
                    pass
            # Stop when we hit the next def or class at same indent
            if i+1 < len(lines) and lines[i+1].strip() and not lines[i+1].startswith((' ', '\t', '"""', '#')):
                if not l.strip().startswith(('    def ', '        def ', '        try:', '        except', '        with ', '            ')):
                    pass  # continue
                else:
                    pass

import sys; sys.path.insert(0,'.')
import core.encoding

core.encoding.setup()
import subprocess

from core.mcp_servers._mcp_utils import run_subprocess

r = run_subprocess(['ping','-n','1','bing.com'], timeout=8)
print('stdout:', repr(r.stdout[:200]))
print('stderr:', repr(r.stderr[:200]))
print('returncode:', r.returncode)

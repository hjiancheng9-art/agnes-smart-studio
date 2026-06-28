import sys; sys.path.insert(0,'.')
import core.encoding

core.encoding.setup()
import subprocess

r = subprocess.run(['ping','-n','1','bing.com'], capture_output=True, text=True, timeout=8)
print('stdout:', repr(r.stdout[:200]))
print('stderr:', repr(r.stderr[:200]))
print('returncode:', r.returncode)

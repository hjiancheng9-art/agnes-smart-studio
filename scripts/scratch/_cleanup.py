import os
import time

# Wait for file handles to release
time.sleep(0.5)
for f in ['_proxy_check.py','_px.py','_cb_install.py','_cb_probe.py','_enc_test.py',
          '_verify_fixes.py','_verify_tokens.py','_spot_audit.py','_simple.py',
          '_simple_env.py','_net_test.py','_use_tools_demo.py','_install_skill.py',
          '_split_cli.py','_check_comfyui.py','_check_tools.py',
          '_audit_check_imports.py','_audit_deep.py','_audit_runner.py',
          '_audit_smoke.py','_audit_syntax.py','p.py','t0.py']:
    try:
        os.remove(f)
        print(f'ok: {f}')
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f'fail: {f} - {e}')

import os

targets = ['_audit_check_imports.py','_audit_deep.py','_audit_runner.py','_audit_smoke.py',
           '_audit_syntax.py','_cb_install.py','_cb_probe.py','_check_comfyui.py',
           '_check_tools.py','_ck_test.py','_cleanup.py','_enc_test.py','_install_skill.py',
           '_net_test.py','_probe.py','_proxy_check.py','_px.py','_simple.py','_simple_env.py',
           '_split_cli.py','_spot_audit.py','_use_tools_demo.py','_verify_fixes.py','_verify_tokens.py']
[os.remove(f) for f in targets if os.path.exists(f)]
print(f'removed {sum(1 for f in targets if os.path.exists(f))} leftover, {sum(1 for f in targets if not os.path.exists(f))} already gone')

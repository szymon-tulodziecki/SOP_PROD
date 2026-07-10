import subprocess
import re
import sys

out = subprocess.check_output(["lualatex", "--version"], text=True)
m = re.search(r"Version (\d+\.\d+)", out)
ver = tuple(int(x) for x in m.group(1).split(".")) if m else (0, 0)
if ver < (1, 17):
    sys.exit(f'LuaLaTeX {m.group(1) if m else "?"} < 1.17.0 — CVE-2023-32700')

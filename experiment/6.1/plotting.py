from pathlib import Path
import subprocess, sys

for name in ['plot_fc.py', 'plot_dfs.py', 'plot_jtpc.py']:
    subprocess.run([sys.executable, str(Path(__file__).with_name(name))], check=True)

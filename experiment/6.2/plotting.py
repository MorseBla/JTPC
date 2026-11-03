from pathlib import Path
import subprocess, sys

for name in ['plot_rtr.py', 'plot_power.py', 'plot_utility.py']:
    subprocess.run([sys.executable, str(Path(__file__).with_name(name))], check=True)

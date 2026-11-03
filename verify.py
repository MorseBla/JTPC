"""Offline integrity and Figure 7(b) checks. Never invokes hardware collection."""
from pathlib import Path
import ast, hashlib, json, math, statistics, subprocess

ROOT = Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify():
    manifest = json.loads((ROOT / 'docs/source_manifest.json').read_text())
    for row in manifest:
        path = ROOT / row['destination']
        assert path.is_file(), f'Missing source asset: {path}'
        assert digest(path) == row['sha256'], f'Changed source asset: {path}'
    report = json.loads((ROOT / 'experiment/6.2/Figures/fig7b_statistics.json').read_text())
    assert report['fixed_rtr'] == 0.90
    independent = []
    for method, folder, prefix in [('JTPC', 'Full_LQR', 'LQR'), ('FC-GPU', 'Full_FC', 'FC_GPU'), ('DFS-only', 'Full_DFS', 'DFS')]:
        for i, power in enumerate(report['power_mw']):
            path = ROOT / f'experiment/6.2/logs/{folder}/hist_stereo_mm/setpoint_{power}_0.90_0.90_0.90/{prefix}_finalpowervalues.txt'
            values = [float(s) for s in path.read_text().split()]
            assert values and all(math.isfinite(v) for v in values)
            used = values[100:-1] if len(values) > 101 else values
            mean = statistics.mean(used) / 1000
            std = statistics.pstdev(used) / 1000
            assert abs(mean - report[method]['mean_w'][i]) < 1e-10
            assert abs(std - report[method]['std_w'][i]) < 1e-10
            independent.append(dict(method=method, power_mw=power, input_count=len(values), used_count=len(used), mean_w=mean, std_w=std, file=str(path.relative_to(ROOT)), sha256=digest(path)))
    for row in json.loads((ROOT / 'docs/plot_sources.json').read_text()):
        assert digest(ROOT / row['script']) == row['script_sha256'], row['script']
    assert digest(ROOT / 'experiment/Figures/fig7b_power_RTR090.pdf') == digest(ROOT / 'experiment/6.2/Figures/fig7b_power_RTR090.pdf')
    plot = ast.parse((ROOT / 'experiment/6.2/plot_power.py').read_text())
    fixed = [node.value.value for node in plot.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'FIXED_RTR' for t in node.targets)]
    assert fixed == [0.90]
    # Regression: the old 0.70 slice must not accidentally be accepted as the new data.
    old = ROOT / 'experiment/6.2/logs/Full_LQR/hist_stereo_mm/setpoint_11000_0.70_0.70_0.70/LQR_finalpowervalues.txt'
    v = [float(s) for s in old.read_text().split()]
    assert abs(statistics.mean(v[100:-1]) / 1000 - report['JTPC']['mean_w'][0]) > 0.001
    for f in ROOT.glob('experiment/**/*.sh'):
        subprocess.run(['bash', '-n', str(f)], check=True)
    for f in ROOT.glob('experiment/**/*.py'):
        ast.parse(f.read_text(), filename=str(f))
    for f in (ROOT / 'application').glob('*.cu'):
        assert '../scheduler/shared_header.hpp' not in f.read_text()
    figures = list((ROOT / 'experiment/Figures').glob('*.pdf'))
    assert len(figures) == 10, len(figures)
    for path in figures:
        assert path.read_bytes().startswith(b'%PDF-'), path
    for rel in ['README.md', 'INSTALL.md', 'PROJECT_GUIDE.md', 'experiment/README.md']:
        assert (ROOT / rel).is_file(), rel
    summary = dict(source_files_checked=len(manifest), figure7b_groups_checked=len(independent), figure7b=independent, collected_figures=len(figures), hardware_experiments_started=False)
    (ROOT / 'docs/verification.json').write_text(json.dumps(summary, indent=2))
    print(f'PASS: {len(manifest)} source assets; 15 Figure7b groups; 10 collected PDFs; shell/Python syntax.')

if __name__ == '__main__':
    verify()

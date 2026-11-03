#!/usr/bin/env python3
"""Generate/compile persistent workers by transforming the repository services.

The source transformation retains each workload's original kernel, constants,
allocation, initialization, launch geometry, two-job invocation, event timing,
and cleanup. Only scheduler handshake/periodic-loop plumbing is replaced.
"""
from __future__ import annotations
import argparse, re, subprocess
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
GEN = OUT / "generated"
SOURCES = {
    "hist": ROOT / "application/histogram_converted.cu",
    "mm": ROOT / "application/mm_converted.cu",
    "stereo": ROOT / "application/stereodisparity_converted.cu",
}

SHIM = r'''
#include <semaphore.h>
#include <iomanip>
#include <stdexcept>
struct SharedData { float executiontime[16]{}; float responsetime[16]{}; float newperiods[16]{}; };
inline SharedData* sharedData = nullptr;
class GpuSemaphore { sem_t* s_; public:
  GpuSemaphore(){ const char* n=getenv("JTPC_SI_SEMAPHORE"); if(!n)n="/jtpc_si_default"; s_=sem_open(n,O_CREAT,0666,1); if(s_==SEM_FAILED) throw std::runtime_error("sem_open failed"); }
  void lock(){int rc; do rc=sem_wait(s_); while(rc==-1 && errno==EINTR); if(rc==-1) throw std::runtime_error("sem_wait failed");}
  void unlock(){if(sem_post(s_)==-1) throw std::runtime_error("sem_post failed");} ~GpuSemaphore(){if(s_!=SEM_FAILED)sem_close(s_);}
};
class GpuLockGuard { GpuSemaphore& s_; public: explicit GpuLockGuard(GpuSemaphore&s):s_(s){s_.lock();} ~GpuLockGuard(){s_.unlock();} };
inline GpuSemaphore gpu_sem;
'''

LOOP = r'''
    std::string line;
    double previous_rt_ms = 0.0;
    bool have_previous = false;
    std::cout << "{\"ready\":true}" << std::endl;
    while (std::getline(std::cin, line)) {
        if (line == "quit") break;
        if (line.rfind("run ", 0) != 0) { std::cerr << "expected: run <release_s> [period_s] or quit\n"; continue; }
        std::istringstream in(line.substr(4)); double release = 0.0, period = 0.0; in >> release; if (!(in >> period)) period = 0.0;
        double carry_ms = 0.0; if (have_previous && period > 0.0) carry_ms = std::max(0.0, previous_rt_ms - period * 1000.0);
        timespec a{}, b{}; clock_gettime(CLOCK_MONOTONIC, &a);
        float rt_ms = kernellaunch(gridDim, blockDim, carry_ms);
        clock_gettime(CLOCK_MONOTONIC, &b);
        double start_s = a.tv_sec + 1e-9*a.tv_nsec, end_s = b.tv_sec + 1e-9*b.tv_nsec;
        double exec_s = (double)si_last_execution_ms / 1000.0;
        double response_s = (double)rt_ms / 1000.0;
        double wall_s = std::max(0.0, end_s - release);
        std::cout << std::setprecision(17) << "{\"start_s\":" << start_s << ",\"end_s\":" << end_s
                  << ",\"execution_s\":" << exec_s << ",\"response_s\":" << response_s
                  << ",\"wall_response_s\":" << wall_s << ",\"release_s\":" << release << ",\"ok\":true}" << std::endl;
        previous_rt_ms = rt_ms; have_previous = true;
    }
'''

def matching_brace(text: str, start: int) -> int:
    depth = 0; quote = None; esc = False
    for i in range(start, len(text)):
        c = text[i]
        if quote:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == quote: quote = None
            continue
        if c in "'\"": quote = c
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0: return i
    raise ValueError("unmatched brace")

def transform(name: str, parameters=None) -> str:
    src = SOURCES[name].read_text()
    assert "int jobs = 2;" in src, f"{name}: jobs anchor changed"
    assert "float service::kernellaunch" in src and "void service::runService" in src
    required = {
        "hist": ("histogram_kernel", "const unsigned int num_elements", "const unsigned int num_bins"),
        "mm": ("matMulKernel", "static int N = 700"),
        "stereo": ("stereoDisparityKernel", "const int w = 640", "const int h = 480"),
    }[name]
    for anchor in required:
        assert anchor in src, f"{name}: workload anchor missing: {anchor}"
    # Delete the unused append helper as a complete function, before removing calls.
    helper = src.index("static void append_locked(")
    helper_body = src.index("{", helper)
    helper_end = matching_brace(src, helper_body)
    src = src[:helper] + src[helper_end+1:]
    src = src.replace('#include "../Scheduler/shared_header.hpp"', SHIM)
    src, changed = re.subn(r"while \(cudaEventQuery\(stopEv\) == cudaErrorNotReady\) \{.*?\n\s*\}", "CUDA_CHECK(cudaEventSynchronize(stopEv));", src, count=1, flags=re.S)
    assert changed == 1 and "cudaEventQuery(stopEv)" not in src, f"{name}: event synchronization transform failed"
    rs = src.index("void service::runService()")
    body = src.index("{", rs); end = matching_brace(src, body)
    original_body = src[body+1:end]
    first = original_body.index("gotSIGHUP = 0;")
    # Keep exact source-derived allocation/setup before the controller handshake.
    # Drop handshake, log-file creation, and periodic release code entirely.
    cleanup_candidates = [x for x in (original_body.find("CUDA_CHECK(cudaDestroyTextureObject", first), original_body.find("CUDA_CHECK(cudaEventDestroy", first)) if x >= 0]
    assert cleanup_candidates, f"{name}: CUDA cleanup anchor missing"
    cleanup = min(cleanup_candidates)
    new_body = original_body[:first] + LOOP + original_body[cleanup:]
    new_body = re.sub(r"\s*append_locked\([^;]+;", "", new_body)
    new_body = re.sub(r"\s*std::filesystem::create_directories\([^;]+;", "", new_body)
    new_body = new_body.replace("        std::ofstream execFile(exec_log_path, std::ios::app);", "")
    new_body = new_body.replace("    std::ofstream execFile(exec_log_path, std::ios::app);", "")
    new_body = new_body.replace("    std::ofstream respFile(resp_log_path, std::ios::app);", "")
    src = src[:body+1] + new_body + src[end:]
    src = re.sub(r"\s*append_locked\([^;]+;", "", src)
    src = re.sub(r"\s*std::filesystem::create_directories\([^;]+;", "", src)
    # Preserve the exact event-measured execution time without subtracting a
    # carry term in the protocol layer.
    src = src.replace("    int jobs = 2;", "    int jobs = 2;\n    float si_last_execution_ms = 0.0f;", 1)
    src = src.replace("    float exec_ms = sum_kernel_ms;", "    float exec_ms = sum_kernel_ms;\n    si_last_execution_ms = exec_ms;", 1)
    main = src.index("int main(")
    replacement = r'''int main() {
    std::signal(SIGINT, handleSIGINT);
    int task = 0; if (const char* t = std::getenv("JTPC_SI_TASK_INDEX")) task = std::atoi(t);
    service svc(task, 0.0f, 1.0f, 0.0f, "", 0);
    svc.runService(); return 0;
}
'''
    src = src[:main] + replacement
    parameters = parameters or {}
    definitions = {
        'hist': {'num_elements': ('const unsigned int num_elements = 65536000 / 4;', 'const unsigned int num_elements'),
                 'num_bins': ('const unsigned int num_bins = 4096;', 'const unsigned int num_bins')},
        'mm': {'matrix_n': ('static int N = 700;', 'static int N')},
        'stereo': {'width': ('const int w = 640;', 'const int w'),
                   'height': ('const int h = 480;', 'const int h'),
                   'min_disparity': ('const int minDisp = -16;', 'const int minDisp'),
                   'max_disparity': ('const int maxDisp = 0;', 'const int maxDisp')}
    }[name]
    for key, value in parameters.items():
        if key not in definitions or type(value) is not int:
            raise ValueError('Unsupported/noninteger workload parameter: '+key)
        if 'disparity' not in key and value <= 0:
            raise ValueError('Workload sizes must be positive')
        anchor, declaration = definitions[key]
        if src.count(anchor) != 1:
            raise ValueError('Size declaration changed: '+anchor)
        src = src.replace(anchor, declaration+' = '+str(value)+';', 1)
    if name == 'stereo' and parameters.get('min_disparity', -16) > parameters.get('max_disparity', 0):
        raise ValueError('Invalid disparity range')
    # Ensure protocol parsing and formatting headers exist even where source did not include them.
    src = src.replace("#include <string>\n", "#include <string>\n#include <sstream>\n#include <iomanip>\n#include <vector>\n#include <cstdint>\n", 1)
    assert "std::future<float> asyncJob;" not in src
    assert src.count("append_locked(") == 0 and "shmget(" not in src and "kill(pids" not in src
    return src

def generate(name: str, parameters=None) -> Path:
    GEN.mkdir(parents=True, exist_ok=True)
    p = GEN / f"{name}_worker.cu"; p.write_text(transform(name, parameters)); return p

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--generate-only", action="store_true"); ap.add_argument("--config", default=str(OUT/"config.json")); ap.add_argument("--cuda", default="nvcc"); ap.add_argument("--task", choices=list(SOURCES), action="append"); args = ap.parse_args()
    config = json.loads(Path(args.config).read_text())
    configured = {t['name']: t.get('workload_parameters', {}) for t in config['tasks']}
    manifest = {'tasks': {}, 'compiled': not args.generate_only}
    for name in args.task or [n for n in SOURCES if n in configured]:
        src = GEN / f"{name}_worker.cu"; exe = OUT / "bin" / name
        cmd = [args.cuda, "-std=c++17", "-DJetson", "-arch=sm_110", "-I", str(ROOT/"Common"), "-o", str(exe), str(src), "-L", str(ROOT/"Common"), "-lcudart"]
        print(" ".join(cmd))
        print('workload_parameters='+json.dumps(configured.get(name, {}), sort_keys=True))
        if args.dry_run: continue
        generate(name, configured.get(name)); (OUT/"bin").mkdir(exist_ok=True)
        if not args.generate_only: subprocess.run(cmd, check=True)
        manifest['tasks'][name] = {'workload_parameters': configured.get(name, {}), 'command': cmd,
            'source_sha256': hashlib.sha256(SOURCES[name].read_bytes()).hexdigest(),
            'generated_sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
            'binary_sha256': hashlib.sha256(exe.read_bytes()).hexdigest() if not args.generate_only else None}
    if not args.dry_run:
        (OUT/('generated_manifest.json' if args.generate_only else 'build_manifest.json')).write_text(json.dumps(manifest, indent=2)+'\n')
    return 0
if __name__ == "__main__": raise SystemExit(main())

#include "jetson/tegrastats_monitor.hpp"
#include <cerrno>
#include <csignal>
#include <cstdio>
#include <limits>
#include <poll.h>
#include <sys/wait.h>
#include <unistd.h>
#include <string>

namespace jetson {
namespace {
std::optional<long long> parse_token_mw(const std::string& line, const std::string& token)
{
    const std::string padded = " " + line + " ";
    const auto pos = padded.find(token);
    if (pos == std::string::npos) return std::nullopt;
    size_t p = pos + token.size(); long long value = 0; bool any = false;
    while (p < padded.size() && padded[p] >= '0' && padded[p] <= '9') {
        any = true;
        if (value > (std::numeric_limits<long long>::max() - (padded[p] - '0')) / 10) return std::nullopt;
        value = value * 10 + (padded[p] - '0'); ++p;
    }
    if (!any || p + 1 >= padded.size() || padded[p] != 'm' || padded[p + 1] != 'W') return std::nullopt;
    return value;
}
}

TegrastatsMonitor::~TegrastatsMonitor() { stop(); }

std::optional<long long> TegrastatsMonitor::parse_mw_field(const std::string& line, const std::string& key)
{ return parse_token_mw(line, key); }

bool TegrastatsMonitor::start(int interval_ms)
{
    if (running_.load()) return true;
    if (worker_.joinable()) worker_.join();
    running_.store(true);
    { std::lock_guard<std::mutex> lock(state_mutex_); vdd_in_mw_.store(-1); last_total_at_ = {}; }
    worker_ = std::thread(&TegrastatsMonitor::run, this, interval_ms); return true;
}

void TegrastatsMonitor::stop()
{
    // The worker owns the descriptor and child: never close a descriptor from
    // another thread while poll/read may be using it.
    running_.store(false);
    if (worker_.joinable()) worker_.join();
}

TegrastatsPower TegrastatsMonitor::latest() const
{
    TegrastatsPower p; std::lock_guard<std::mutex> lock(state_mutex_);
    const auto now = std::chrono::steady_clock::now();
    const bool fresh = running_.load() && last_total_at_ != std::chrono::steady_clock::time_point{} && now - last_total_at_ <= std::chrono::seconds(2);
    p.vdd_in_mw = fresh ? vdd_in_mw_.load() : -1;
    p.vdd_cpu_gpu_cv_mw = vdd_cpu_gpu_cv_mw_.load(); p.vdd_soc_mw = vdd_soc_mw_.load(); return p;
}

void TegrastatsMonitor::run(int interval_ms)
{
    int fds[2]; if (::pipe(fds) != 0) { running_.store(false); return; }
    const std::string ms = std::to_string(interval_ms);
    const pid_t pid = ::fork();
    if (pid < 0) { ::close(fds[0]); ::close(fds[1]); running_.store(false); return; }
    if (pid == 0) {
        ::setpgid(0, 0); ::dup2(fds[1], STDOUT_FILENO); ::close(fds[0]); ::close(fds[1]);
        if (::geteuid() == 0)
            ::execlp("tegrastats", "tegrastats", "--interval", ms.c_str(), nullptr);
        else
            ::execlp("sudo", "sudo", "-n", "tegrastats", "--interval", ms.c_str(), nullptr);
        _exit(127);
    }
    ::setpgid(pid, pid); ::close(fds[1]);
    std::string pending; char buf[4096]; struct pollfd pfd{fds[0], POLLIN, 0};
    while (running_.load()) {
        const int rc = ::poll(&pfd, 1, 100); if (rc < 0 && errno == EINTR) continue; if (rc <= 0) continue;
        // A closed pipe may still contain the final output line.
        if (!(pfd.revents & POLLIN)) {
            if (pfd.revents & (POLLERR | POLLHUP | POLLNVAL)) break;
            continue;
        }
        const ssize_t n = ::read(fds[0], buf, sizeof(buf));
        if (n <= 0) break;
        pending.append(buf, static_cast<size_t>(n)); size_t end;
        while ((end = pending.find('\n')) != std::string::npos) {
            const std::string line = pending.substr(0, end); pending.erase(0, end + 1);
            auto total = parse_token_mw(line, " VIN "); if (!total) total = parse_token_mw(line, " VDD_IN ");
	    //auto total = parse_token_mw(line, " VDD_GPU ");
            std::lock_guard<std::mutex> lock(state_mutex_);
            if (total && *total > 0 && *total <= std::numeric_limits<int>::max()) { vdd_in_mw_.store(*total); last_total_at_ = std::chrono::steady_clock::now(); }
            else { vdd_in_mw_.store(-1); last_total_at_ = {}; }
            if (auto v = parse_token_mw(line, " VDD_CPU_GPU_CV ")) vdd_cpu_gpu_cv_mw_.store(*v);
            if (auto v = parse_token_mw(line, " VDD_SOC ")) vdd_soc_mw_.store(*v);
        }
    }
    ::close(fds[0]);
    // Terminate/reap only this reader's process group, including sudo's child.
    ::kill(-pid, SIGTERM);
    ::kill(pid, SIGTERM);
    int status;
    pid_t waited = 0;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(200);
    do {
        waited = ::waitpid(pid, &status, WNOHANG);
        if (waited == pid || (waited < 0 && errno != EINTR)) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    } while (std::chrono::steady_clock::now() < deadline);
    if (waited == 0 || (waited < 0 && errno == EINTR)) {
        ::kill(-pid, SIGKILL);
        ::kill(pid, SIGKILL);
        while (::waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
    }
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        vdd_in_mw_.store(-1);
        last_total_at_ = {};
    }
    running_.store(false);
}
} // namespace jetson

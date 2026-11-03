#include "shared_header.hpp"
#include <Eigen/Dense>
#include <memory>
#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <mutex>
#include <iomanip>
#include <fstream>
#include <chrono>
#include <cstring>
#include <cerrno>
#include <limits>
#include <cmath>
#include <stdexcept>

#include "../Common/jetson/jetson_power_monitor.hpp"

#ifdef Jetson
    std::atomic<float> current_freq{918.0f};
#else 
    std::atomic<float> current_freq{1200.0f};
#endif
float innerloopduration = 0.500*2*2;
float outerloopduration = innerloopduration;
std::atomic<bool> outerlooprunning{true};
std::atomic<bool> controllerlooping{true};
std::atomic<bool> monitorthread{true};
std::atomic<bool> stopsigma{false};
std::atomic<bool> powerinterrup{false};
float powersetpoint;

std::string g_power_backend = "tegrastats";
std::unique_ptr<jetson::JetsonPowerMonitor> g_power_monitor;

#ifdef Jetson
//static const char* GPU_DEVFREQ_PATH = "/sys/class/devfreq/17000000.gpu";
static const char* GPU_DEVFREQ_PATH = "/sys/class/devfreq/gpu-gpc-0";

int env_int_or_default(const char* name, int fallback)
{
    if (const char* env = std::getenv(name)) {
        char* end = nullptr;
        long value = std::strtol(env, &end, 10);
        if (end != env && value >= 0) return static_cast<int>(value);
    }
    return fallback;
}

float env_float_or_default(const char* name, float fallback)
{
    if (const char* env = std::getenv(name)) {
        char* end = nullptr;
        float value = std::strtof(env, &end);
        if (end != env && value >= 0.0f) return value;
    }
    return fallback;
}

float shell_equiv_power_mw()
{
    return env_float_or_default("GPU_SHELL_EQUIV_POWER_MW", 0.0f);
}

bool write_string_to_file(const std::string& path, const std::string& value)
{
    int fd = open(path.c_str(), O_WRONLY | O_CLOEXEC);
    if (fd < 0) {
        if (env_int_or_default("GPU_ACTUATION_LOG_ERRORS", 0) > 0) {
            std::cerr << "[GPU] failed to open " << path << ": "
                      << std::strerror(errno) << "\n";
        }
        return false;
    }

    const std::string line = value + "\n";
    const ssize_t written = write(fd, line.data(), line.size());
    const int write_errno = errno;
    const int close_result = close(fd);
    const int close_errno = errno;

    if (written != static_cast<ssize_t>(line.size()) || close_result != 0) {
        if (env_int_or_default("GPU_ACTUATION_LOG_ERRORS", 0) > 0) {
            const int err = (written != static_cast<ssize_t>(line.size())) ? write_errno : close_errno;
            std::cerr << "[GPU] failed to write " << path << ": "
                      << std::strerror(err) << "\n";
        }
        return false;
    }

    return true;
}

bool read_string_from_file(const std::string& path, std::string& value)
{
    std::ifstream f(path);
    if (!f.good()) return false;
    f >> value;
    return !f.fail();
}

bool read_ll_from_file(const std::string& path, long long& value)
{
    std::string s;
    if (!read_string_from_file(path, s)) return false;
    char* end = nullptr;
    long long v = std::strtoll(s.c_str(), &end, 10);
    if (end == s.c_str()) return false;
    value = v;
    return true;
}

int gpu_freq_step_index(long long freq_hz)
{
    //static const std::vector<long long> lut_hz = {
    //    1020000000LL, 918000000LL, 816000000LL, 714000000LL,
    //    612000000LL, 510000000LL, 408000000LL, 306000000LL
    //};
    static const std::vector<long long> lut_hz = {
	1575000000LL, 1566000000LL, 1557000000LL, 1548000000LL, 1539000000LL, 
	1530000000LL, 1521000000LL, 1512000000LL, 1503000000LL, 1494000000LL, 
	1485000000LL, 1476000000LL, 1467000000LL, 1458000000LL, 1449000000LL, 
	1440000000LL, 1431000000LL, 1422000000LL, 1413000000LL, 1404000000LL, 
	1395000000LL, 1386000000LL, 1377000000LL, 1368000000LL, 1359000000LL, 
	1350000000LL, 1341000000LL, 1332000000LL, 1323000000LL, 1314000000LL, 
	1305000000LL, 1296000000LL, 1287000000LL, 1278000000LL, 1269000000LL, 
	1260000000LL, 1251000000LL, 1242000000LL, 1233000000LL, 1224000000LL, 
	1215000000LL, 1206000000LL, 1197000000LL, 1188000000LL, 1179000000LL, 
	1170000000LL, 1161000000LL, 1152000000LL, 1143000000LL, 1134000000LL, 
	1125000000LL, 1116000000LL, 1107000000LL, 1098000000LL, 1089000000LL, 
	1080000000LL, 1071000000LL, 1062000000LL, 1053000000LL, 1044000000LL, 
	1035000000LL, 1026000000LL, 1017000000LL, 1008000000LL, 999000000LL, 
	990000000LL, 981000000LL, 972000000LL, 963000000LL, 954000000LL, 
	945000000LL, 936000000LL, 927000000LL, 918000000LL, 909000000LL, 
	900000000LL, 891000000LL, 882000000LL, 873000000LL, 864000000LL, 
	855000000LL, 846000000LL, 837000000LL, 828000000LL, 819000000LL, 
	810000000LL, 801000000LL, 792000000LL, 783000000LL, 774000000LL, 
	765000000LL, 756000000LL, 747000000LL, 738000000LL, 729000000LL, 
	720000000LL, 711000000LL, 702000000LL, 693000000LL, 684000000LL, 
	675000000LL, 666000000LL, 657000000LL, 648000000LL, 639000000LL, 
	630000000LL, 621000000LL, 612000000LL, 603000000LL, 594000000LL, 
	585000000LL, 576000000LL, 567000000LL, 558000000LL, 549000000LL, 
	540000000LL, 531000000LL, 522000000LL, 513000000LL, 504000000LL, 
	495000000LL, 486000000LL, 477000000LL, 468000000LL, 459000000LL, 
	450000000LL, 441000000LL, 432000000LL, 423000000LL, 414000000LL, 
	405000000LL, 396000000LL, 387000000LL, 378000000LL, 369000000LL, 
	360000000LL, 351000000LL, 342000000LL, 333000000LL, 324000000LL, 
	315000000LL, 306000000LL, 297000000LL, 288000000LL, 279000000LL, 
	270000000LL, 261000000LL, 252000000LL, 243000000LL, 234000000LL, 
	225000000LL, 216000000LL, 207000000LL, 198000000LL, 189000000LL, 
	180000000LL, 171000000LL, 162000000LL, 153000000LL, 144000000LL, 
	135000000LL, 126000000LL, 117000000LL, 108000000LL, 99000000LL, 
	90000000LL, 81000000LL, 72000000LL, 63000000LL, 54000000LL	    

    };

    for (size_t i = 0; i < lut_hz.size(); ++i) {
        if (lut_hz[i] == freq_hz) return static_cast<int>(i);
    }
    return -1;
}

void direct_set_gpu_freq_hz(long long freq_hz)
{
    static std::mutex actuation_mutex;
    static long long last_written_hz = -1;
    static long long pending_target_hz = -1;
    static int pending_count = 0;
    static std::chrono::steady_clock::time_point last_write_time;
    static bool has_last_write_time = false;

    std::lock_guard<std::mutex> lock(actuation_mutex);

    const std::string base = GPU_DEVFREQ_PATH;
    const std::string freq = std::to_string(freq_hz);

    if (freq_hz == last_written_hz) return;

    const int confirm_count = env_int_or_default("GPU_ACTUATION_CONFIRM_COUNT", 1);
    if (confirm_count > 1 && last_written_hz > 0) {
        const int cur_idx = gpu_freq_step_index(last_written_hz);
        const int target_idx = gpu_freq_step_index(freq_hz);

        if (cur_idx >= 0 && target_idx >= 0 && std::abs(target_idx - cur_idx) < 2) {
            if (pending_target_hz == freq_hz) {
                pending_count++;
            } else {
                pending_target_hz = freq_hz;
                pending_count = 1;
            }

            if (pending_count < confirm_count) return;
        }

        pending_target_hz = -1;
        pending_count = 0;
    }

    const int min_interval_ms = env_int_or_default("GPU_ACTUATION_MIN_INTERVAL_MS", 0);
    if (min_interval_ms > 0 && has_last_write_time) {
        const auto now = std::chrono::steady_clock::now();
        const auto elapsed_ms =
            std::chrono::duration_cast<std::chrono::milliseconds>(now - last_write_time).count();
        if (elapsed_ms < min_interval_ms) return;
    }

    if (!write_string_to_file(base + "/governor", "userspace")) return;

    long long cur_min = -1;
    long long cur_max = -1;
    read_ll_from_file(base + "/min_freq", cur_min);
    read_ll_from_file(base + "/max_freq", cur_max);

    if (cur_max >= 0 && freq_hz > cur_max) {
        if (!write_string_to_file(base + "/max_freq", freq)) return;
        if (!write_string_to_file(base + "/min_freq", freq)) return;
    } else if (cur_min >= 0 && freq_hz < cur_min) {
        if (!write_string_to_file(base + "/min_freq", freq)) return;
        if (!write_string_to_file(base + "/max_freq", freq)) return;
    } else {
        if (!write_string_to_file(base + "/min_freq", freq)) return;
        if (!write_string_to_file(base + "/max_freq", freq)) return;
    }

    if (!write_string_to_file(base + "/userspace/set_freq", freq)) return;

    std::string ignored;
    read_string_from_file(base + "/governor", ignored);
    read_string_from_file(base + "/min_freq", ignored);
    read_string_from_file(base + "/max_freq", ignored);
    read_string_from_file(base + "/userspace/set_freq", ignored);
    read_string_from_file(base + "/cur_freq", ignored);

    if (env_int_or_default("GPU_ACTUATION_WAIT_FOR_CUR_FREQ", 0) > 0) {
        const int max_steps = env_int_or_default("GPU_ACTUATION_WAIT_MAX_STEPS", 100);
        const int step_ms = env_int_or_default("GPU_ACTUATION_WAIT_STEP_MS", 20);
        for (int i = 0; i < max_steps; ++i) {
            std::string cur;
            if (read_string_from_file(base + "/cur_freq", cur) && cur == freq) {
                break;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(step_ms));
        }
    }

    const int emulate_ms = env_int_or_default("GPU_ACTUATION_EMULATE_SCRIPT_MS", 0);
    if (emulate_ms > 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(emulate_ms));
    }

    last_written_hz = freq_hz;
    last_write_time = std::chrono::steady_clock::now();
    has_last_write_time = true;
}
#endif

#ifdef CLAMP_PERIODS
    #ifndef BOUND
        #define BOUND 40  // Fallback default
    #endif
    static const float BOUND_VALUE = BOUND / 100.0f;
#endif



void activate_freq_nvidia_rtx(int coreClock) 
{  
    int memClock = 5001;  
    #ifdef Jetson
        direct_set_gpu_freq_hz(static_cast<long long>(coreClock) * 1000000LL);
    #else
        std::string command ="sudo nvidia-smi -i 0 -lgc "+ std::to_string(coreClock) + "," + std::to_string(coreClock)+ "> /dev/null 2>&1";
        int result = std::system(command.c_str());
    #endif
    
}

std::string normalize_power_backend(std::string s)
{
    std::transform(s.begin(), s.end(), s.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return s;
}


// int returnfreq()
// {
//     const char* cmd ="nvidia-smi -i 0 --query-gpu=clocks.sm --format=csv,noheader,nounits";
//     FILE* pipe = popen(cmd, "r");
//     if (!pipe) {
//         return -1; 
//     }

//     char buffer[64];
//     if (!fgets(buffer, sizeof(buffer), pipe)) {
//         pclose(pipe);
//         return -1;  
//     }
//     pclose(pipe);
//     return std::atoi(buffer); 
// }

int returnpowerrtx(){
#ifdef Jetson
    if (g_power_backend == "thor") {
        // Both monitoring threads share one command-line sample at up to 10 Hz.
        static std::mutex mutex;
        static std::chrono::steady_clock::time_point sampled_at{};
        static int cached_mw = -1;
        std::lock_guard<std::mutex> lock(mutex);
        if (cached_mw > 0 && std::chrono::steady_clock::now() - sampled_at < std::chrono::milliseconds(100))
            return cached_mw;

        FILE* pipe = popen("bash ../scripts/get_power.sh thor", "r");
        if (!pipe) throw std::runtime_error("Cannot start Thor power reader");
        char buffer[64]{};
        const bool read_ok = std::fgets(buffer, sizeof(buffer), pipe) != nullptr;
        const bool ended = std::fgetc(pipe) == EOF;
        const int status = pclose(pipe);
        std::istringstream input(buffer);
        long long mw = 0;
        char extra;
        if (!read_ok || !ended || status != 0 || !(input >> mw) || (input >> extra) ||
            mw <= 0 || mw > std::numeric_limits<int>::max())
            throw std::runtime_error("Thor INA238 VIN power read failed; no substitute value is used");
        cached_mw = static_cast<int>(mw);
        sampled_at = std::chrono::steady_clock::now();
        return cached_mw;
    }
    if (g_power_backend == "tegrastats") {
        // Startup validates the first sample before control/device actuation.
        // Both monitoring threads subsequently share this initialized reader.
        static std::mutex mutex;
        static bool have_sample = false;
        std::lock_guard<std::mutex> lock(mutex);
        if (!g_power_monitor) {
            jetson::JetsonPowerMonitor::Config cfg;
            cfg.enable_ina260 = false;
            cfg.enable_jtop = false;
            cfg.enable_tegrastats = true;
            cfg.tegrastats_interval_ms = 200;
            g_power_monitor = std::make_unique<jetson::JetsonPowerMonitor>(cfg);
            if (!g_power_monitor->init())
                throw std::runtime_error("Cannot start tegrastats VIN power reader");
        }
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
        do {
            const auto sample = g_power_monitor->sample();
            const double mw = sample.tegrastats_vdd_in_w * 1000.0;
            if (std::isfinite(mw) && mw >= 1.0 && mw <= std::numeric_limits<int>::max()) {
                have_sample = true;
                return static_cast<int>(std::llround(mw));
            }
            if (have_sample) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        } while (std::chrono::steady_clock::now() < deadline);
        throw std::runtime_error(
            "Missing, invalid or stale tegrastats VIN/VDD_IN power (mW); no substitute value is used");
    }
    try
    {
        if (!g_power_monitor)
        {
            jetson::JetsonPowerMonitor::Config cfg;
            cfg.enable_ina260     = (g_power_backend == "ina260");
            cfg.enable_jtop       = (g_power_backend == "jtop");
            cfg.enable_tegrastats = !cfg.enable_ina260 && !cfg.enable_jtop;

            if (const char* dev = std::getenv("INA260_I2C_DEV"))
                cfg.ina260_dev_path = dev;

            if (const char* addr = std::getenv("INA260_I2C_ADDR"))
                cfg.ina260_addr = std::strtol(addr, nullptr, 0);

            g_power_monitor = std::make_unique<jetson::JetsonPowerMonitor>(cfg);
            g_power_monitor->init();
        }

        auto sample = g_power_monitor->sample();

        double power_w =
            (g_power_backend == "ina260") ? sample.ina260_power_w :
            (g_power_backend == "jtop")   ? sample.jtop_total_w :
                                            sample.tegrastats_vdd_in_w;

        return (power_w < 0.0) ? 0 : static_cast<int>(power_w * 1000.0);
    }
    catch (...)
    {
        return 0;
    }
#else
    const char* cmd = "nvidia-smi -i 0 --query-gpu=power.draw --format=csv,noheader,nounits";
    FILE* pipe = popen(cmd, "r");
    if (!pipe) return -1;

    char buffer[64];
    if (!fgets(buffer, sizeof(buffer), pipe)) {
        pclose(pipe);
        return -1;
    }
    pclose(pipe);
    return std::atoi(buffer);
#endif
}

int returnfreqrtx(){
   // const char* cmd ="nvidia-smi -i 0 --query-gpu=power.draw --format=csv,noheader,nounits";
    #ifdef Jetson
        const char* cmd ="sudo ../scripts/get_gpu_freq_mhz.sh";
    #else
        const char* cmd = "nvidia-smi -i 0 --query-gpu=clocks.current.graphics --format=csv,noheader,nounits";
    #endif
    FILE* pipe = popen(cmd, "r");
    if (!pipe) {
        return -1;  // failed to run command
    }

    char buffer[64];
    if (!fgets(buffer, sizeof(buffer), pipe)) {
        pclose(pipe);
        return -1;  // failed to read output
    }
    pclose(pipe);
    return std::atoi(buffer); 
    
    
}


static int append_lock(const std::string&path, const std::string &line){
    
    int fd= open(path.c_str(), O_WRONLY | O_CREAT | O_APPEND,0644);
    if (fd<0) return - 1;
    flock(fd,LOCK_EX);
     
    if (write(fd, line.data(), line.size()) < 0) return -1;
    if (write(fd, "\n", 1) < 0) return -1;
    
    flock(fd, LOCK_UN);
    close(fd);
    return 0;
}

float calculate_deadline_miss(const std::vector<float>& local_resp,
                              const std::vector<float>& local_per,
                              float eps = 0.0f)  // e.g., 0.01f for 1% tolerance
{
    if (local_resp.empty() || local_per.empty())
        return 0.0f;

    size_t total = std::min(local_resp.size(), local_per.size());
    int miss_count = 0;

    for (size_t i = 0; i < total; ++i)
    {
        float period = local_per[i];
        if (period <= 0.0f)
            continue;

        float rtr = local_resp[i] / period;
        if (rtr > (1.0f + eps))
            miss_count++;
    }

    return (static_cast<float>(miss_count) / total) * 100.0f;
}

void monitorpower()
{
    std::cout << "[monitorpower] entered\n";
    average avg;
    interpowervalues.reserve(2048);
    using clock_t = std::chrono::steady_clock;

    const auto power_sample_period = std::chrono::milliseconds(100);  // 10 Hz

    while (monitorthread.load(std::memory_order_relaxed))
    {
        interpowervalues.clear();
        auto windowStart = clock_t::now();

        while (true)
        {
            auto now = clock_t::now();
            std::chrono::duration<double> elapsed = now - windowStart;
            if (elapsed.count() >= innerloopduration)
                break;

            static float last_valid_power = 11000.0f;

            float power = static_cast<float>(returnpowerrtx());

            // Use last valid value to suppress INA outliers without creating gaps.
            if (power > 0.0f && (g_power_backend == "thor" ||
                                 g_power_backend == "tegrastats" || power < 50000.0f))
            {
                if (g_power_backend != "thor" && g_power_backend != "tegrastats")
                    power += shell_equiv_power_mw();
                last_valid_power = power;
                interpowervalues.push_back(power);
            }
            else
            {
                interpowervalues.push_back(last_valid_power);
            }

            std::this_thread::sleep_for(power_sample_period);
        }

        float finpower = avg.calculateAverage(interpowervalues);
        finalpowervalues.push_back(finpower);
    }
}

void monitorfreq()
{
    average avg;
    interfreqvalues.reserve(2048);
    using clock_t = std::chrono::steady_clock;
    while (monitorthread.load(std::memory_order_relaxed))
    {
        //interfreqvalues.clear();
        auto windowStart = clock_t::now();
        while (true)
        {
            auto now = clock_t::now();
            std::chrono::duration<double> elapsed = now - windowStart;
            if (elapsed.count() >= innerloopduration)
                break;

            //float power = static_cast<float>(returnfreqrtx());
            //interfreqvalues.push_back(power);
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }

        //float finfreq = avg.calculateAverage(interfreqvalues);
        float finfreq =current_freq.load(std::memory_order_relaxed);
        finalfrequencyvalues.push_back(finfreq);
    }
}







void sigmadelta_freq_step(float newfreq) 
{ 
    const int sigma_period_ms = env_int_or_default("GPU_SIGMA_PERIOD_MS", 1);

    static const std::vector<int> lut = 
    #ifdef Jetson
        //{
        //    1020, 918, 816, 714, 612, 510, 408, 306    
        //};
  	[]() {
  	    std::vector<int> levels;
  	    for (int mhz = 1575; mhz >= 54; mhz -= 9)
  	        levels.push_back(mhz);
  	    return levels;
  	}();        
    
    //	{
    //    1575000000, 1566000000, 1557000000, 1548000000, 1539000000, 1530000000, 
    //    1521000000, 1512000000, 1503000000, 1494000000, 1485000000, 1476000000,
    //   1467000000, 1458000000, 1449000000, 1440000000, 1431000000, 1422000000, 
    //   1413000000, 1404000000, 1395000000, 1386000000, 1377000000, 1368000000, 
    //   1359000000, 1350000000, 1341000000, 1332000000, 1323000000, 1314000000, 
    //   1305000000, 1296000000, 1287000000, 1278000000, 1269000000, 1260000000, 
    //   1251000000, 1242000000, 1233000000, 1224000000, 1215000000, 1206000000, 
    //   1197000000, 1188000000, 1179000000, 1170000000, 1161000000, 1152000000, 
    //   1143000000, 1134000000, 1125000000, 1116000000, 1107000000, 1098000000, 
    //   1089000000, 1080000000, 1071000000, 1062000000, 1053000000, 1044000000, 
    //   1035000000, 1026000000, 1017000000, 1008000000, 999000000, 990000000, 
    //   981000000, 972000000, 963000000, 954000000, 945000000, 936000000, 
    //   927000000, 918000000, 909000000, 900000000, 891000000, 882000000, 
    //   873000000, 864000000, 855000000, 846000000, 837000000, 828000000, 
    //   819000000, 810000000, 801000000, 792000000, 783000000, 774000000, 
    //   765000000, 756000000, 747000000, 738000000, 729000000, 720000000, 
    //   711000000, 702000000, 693000000, 684000000, 675000000, 666000000, 
    //   657000000, 648000000, 639000000, 630000000, 621000000, 612000000, 
    //   603000000, 594000000, 585000000, 576000000, 567000000, 558000000, 
    //   549000000, 540000000, 531000000, 522000000, 513000000, 504000000, 
    //   495000000, 486000000, 477000000, 468000000, 459000000, 450000000, 
    //   441000000, 432000000, 423000000, 414000000, 405000000, 396000000, 
    //   387000000, 378000000, 369000000, 360000000, 351000000, 342000000, 
    //   333000000, 324000000, 315000000, 306000000, 297000000, 288000000, 
    //   279000000, 270000000, 261000000, 252000000, 243000000, 234000000, 
    //   225000000, 216000000, 207000000, 198000000, 189000000, 180000000, 
    //   171000000, 162000000, 153000000, 144000000, 135000000, 126000000, 
    //   117000000, 108000000, 99000000, 90000000, 81000000, 72000000,
    //   63000000, 54000000
    //    };
    #else
         {
            2100, 2085, 2070, 2055, 2040, 2025, 2010, 1995, 1980, 1965,
            1950, 1935, 1920, 1905, 1890, 1875, 1860, 1845, 1830, 1815,
            1800, 1785, 1770, 1755, 1740, 1725, 1710, 1695, 1680, 1665,
            1650, 1635, 1620, 1605, 1590, 1575, 1560, 1545, 1530, 1515,
            1500, 1485, 1470, 1455, 1440, 1425, 1410, 1395, 1380, 1365,
            1350, 1335, 1320, 1305, 1290, 1275, 1260, 1245, 1230, 1215,
            1200, 1185, 1170, 1155, 1140, 1125, 1110, 1095, 1080, 1065,
            1050, 1035, 1020, 1005, 990, 975, 960, 945, 930, 915,
            900, 885, 870, 855, 840, 825, 810, 795, 780, 765,
            750, 735, 720, 705, 690, 675, 660, 645, 630, 615,
            600, 585, 570, 555, 540, 525, 510, 495, 480, 465,
            450, 435, 420, 405, 390, 375, 360, 345, 330, 315,
            300, 285, 270, 255, 240, 225, 210
        };
    #endif

    static float acc = 0.0f;
    static int lastLower = 0;
    static int lastUpper = 0;
    acc = 0.0f;
    lastLower = 0;
    lastUpper = 0;

    while (!stopsigma.load(std::memory_order_relaxed))
    {
        if (newfreq >= lut.front()) {
            activate_freq_nvidia_rtx(lut.front());
            std::this_thread::sleep_for(std::chrono::milliseconds(sigma_period_ms));
            continue;
        }
        if (newfreq <= lut.back()) {
            activate_freq_nvidia_rtx(lut.back());
            std::this_thread::sleep_for(std::chrono::milliseconds(sigma_period_ms));
            continue;
        }
        auto it = std::lower_bound(
            lut.begin(), lut.end(), newfreq,
            [](int lutVal, float value) { return lutVal > value; }
        );

        int lower = *it;           
        int upper = *(it - 1);  
        if (lower != lastLower || upper != lastUpper) {
            acc = 0.0f;
            lastLower = lower;
            lastUpper = upper;
        }
        float delta = (newfreq - lower) / (float)(upper - lower);
        acc += delta;
        int selectedFreq;
        if (acc >= 1.0f) {
            selectedFreq = upper;
            acc -= 1.0f;
        } else {
            selectedFreq = lower;
        }
        activate_freq_nvidia_rtx(selectedFreq);
        std::this_thread::sleep_for(std::chrono::milliseconds(sigma_period_ms));
    }
}


static std::mutex g_console_mutex;

static void console_render_lqr_status(
    int controlperiod,
    double ts,
    int N,
    float measuredpower,
    float measuredpowererror,
    float measured_freq,
    float delta_freq,
    float next_freq,
    const float* executiontime,
    const float* responsetime,
    const float* desiredresponsetime,
    const float* rtr,
    const float* error,
    const float* taskperiod,
    const float* newtaskperiod,
    const float* deadlinemiss)
{
    std::lock_guard<std::mutex> lock(g_console_mutex);

    static bool initialized = false;

    if (!initialized) {
        std::cout << "\033[2J\033[H";

        std::cout << "==================== LQR Controller ====================\n";
        std::cout << "Control Period : \n";
        std::cout << "Time (s)       : \n";
        std::cout << "Measured Power :                      Power Error    : \n";
        std::cout << "Current Freq   :                      Delta Freq     : \n";
        std::cout << "Next Freq Cmd  : \n";
        std::cout << "\n";

        std::cout << "task            ex(ms)          RS(ms)          RSn(ms)         rtr\n";
        for (int i = 0; i < N; i++) std::cout << "\n";

        std::cout << "\n";
        std::cout << "task            err             P(ms)           Pn(ms)          Deadline miss (%)\n";
        for (int i = 0; i < N; i++) std::cout << "\n";

        std::cout << "\n";
        std::cout << "========================================================\n";

        initialized = true;
    }

    std::cout << std::fixed << std::setprecision(3);

    // Header information area
    std::cout << "\033[2;18H" << std::setw(6)  << controlperiod << "\033[K";
    std::cout << "\033[3;18H" << std::setw(10) << ts << "\033[K";

    std::cout << "\033[4;18H" << std::setw(10) << measuredpower /1000 << " W";
    std::cout << "\033[4;50H" << std::setw(10) << measuredpowererror /1000 << " W\033[K";

    std::cout << "\033[5;18H" << std::setw(10) << measured_freq << " MHz";
    std::cout << "\033[5;50H" << std::setw(10) << delta_freq << " MHz\033[K";

    std::cout << "\033[6;18H" << std::setw(10) << next_freq << " MHz\033[K";

    // First table: header on row 8, data from row 9.
    for (int i = 0; i < N; i++) {
        int row = 9 + i;
        std::cout << "\033[" << row << ";1H";
        std::cout << "T" << (i + 1)
                  << std::string(14, ' ')
                  << std::setw(10) << executiontime[i] << "        "
                  << std::setw(10) << responsetime[i] << "        "
                  << std::setw(10) << desiredresponsetime[i] << "        "
                  << std::setw(8)  << rtr[i]
                  << "\033[K";
    }

    // Second table: header on row 13 for N=3, data from the next row.
    int second_header_row = 10 + N;
    for (int i = 0; i < N; i++) {
        int row = second_header_row + 1 + i;
        std::cout << "\033[" << row << ";1H";
        std::cout << "T" << (i + 1)
                  << std::string(14, ' ')
                  << std::setw(10) << error[i] << "        "
                  << std::setw(10) << taskperiod[i] << "        "
                  << std::setw(10) << newtaskperiod[i] * 1000.0f << "        "
                  << std::setw(8)  << deadlinemiss[i]
                  << "\033[K";
    }

    // Move the cursor to the bottom.
    std::cout << "\033[" << (second_header_row + N + 3) << ";1H";
    std::cout.flush();
}


//void proposed(string path,logging& log, tasks& t, int numtasks,float** gain,std::atomic<bool>& controllerlooping, float powersetpoint, logging_sys& logsys)
//{
//    std::cout << "Proposed running\n";
//
//}



void proposed(std::string path,
              logging& log,
              tasks& t,
              int numtasks,
              float** gain,
              std::atomic<bool>& controllerlooping,
              float powersetpoint,
              logging_sys& logsys)
{
    auto start = std::chrono::steady_clock::now();
    int controlperiod = 0;
    int N = numtasks;

    float* delta = new float[N + 1];
    float* error = new float[N + 1];

    float* rtr = new float[N];
    float* upperbound = new float[N];
    float* lowerbound = new float[N];
    float* executiontime = new float[N];
    float* responsetime = new float[N];
    float* desiredresponsetime = new float[N];
    float* taskperiod = new float[N];
    float* newtaskperiod = new float[N];
    float* deadlinemiss = new float[N];

    std::thread freqthread;

    float measuredpower = 0.0f;
    float measuredpowererror = 0.0f;

    average average;
    std::ofstream ctrlLog("logs/controller.txt", std::ios::app);

    std::filesystem::path base_path(path);
    std::vector<std::string> exec_paths(N);
    std::vector<std::string> resp_paths(N);

    for (int i = 0; i < N; ++i) {
        exec_paths[i] = (base_path / ("taskexecutiontime" + std::to_string(i) + ".txt")).string();
        resp_paths[i] = (base_path / ("taskresponsetime" + std::to_string(i) + ".txt")).string();
    }

    while (controllerlooping.load(std::memory_order_relaxed))
    {
        std::this_thread::sleep_for(std::chrono::duration<float>(innerloopduration));

        stopsigma.store(true, std::memory_order_relaxed);
        if (freqthread.joinable()) {
            freqthread.join();
        }

        auto end = std::chrono::steady_clock::now();

        for (int i = 0; i < N; i++) {
            std::vector<float> local_rtr, local_resp, local_per, local_exec;
            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                local_rtr  = std::move(log[i].rtr);
                local_resp = std::move(log[i].response);
                local_per  = std::move(log[i].period);
                local_exec = std::move(log[i].exec);
            }

            rtr[i]           = average.calculateAverage(local_rtr);
            responsetime[i]  = average.calculateAverage(local_resp);
            taskperiod[i]    = average.calculateAverage(local_per);
            executiontime[i] = average.calculateAverage(local_exec);

            desiredresponsetime[i] = t[i].setpoint * taskperiod[i];
            deadlinemiss[i] = calculate_deadline_miss(local_resp, local_per, 0.00f);
	    if (rtr[i] > 2.0) error[i] = 0.0;
	    else error[i] = desiredresponsetime[i] - responsetime[i];

#ifdef DEBUG
            std::cout << "Size" << i
                      << " samples: rtr=" << local_rtr.size()
                      << " resp=" << local_resp.size()
                      << " period=" << local_per.size()
                      << " exec=" << local_exec.size()
                      << "\n";
#endif

            if (append_lock(exec_paths[i], "Control Period") < 0) {
                std::cout << "Error in proposed\n";
            }
            if (append_lock(resp_paths[i], "Control Period") < 0) {
                std::cout << "Error in proposed\n";
            }
        }

        std::vector<float> local_power;
        {
            local_power = std::move(logsys.power.measuredpower);
        }

        measuredpower = average.calculateAverage(local_power);
        measuredpowererror = powersetpoint - measuredpower;
        error[N] = measuredpowererror;

        for (int i = 0; i < N + 1; i++) {
            delta[i] = 0.0f;
            for (int j = 0; j < N + 1; j++) {
                delta[i] += error[j] * (-gain[i][j]);
            }
#ifdef DEBUG
            std::cout << "delta[" << i << "] = " << delta[i] << "\n";
#endif
        }

        for (int i = 0; i < N; i++)
        {
            newtaskperiod[i] = taskperiod[i] + delta[i];
            newtaskperiod[i] = newtaskperiod[i] / 1000.0f;
        }

#ifdef CLAMP_PERIODS
        for (int i = 0; i < N; i++) {
            float initial = t[i].initial_rate;
            float min_p = initial * (1 - BOUND_VALUE);
            float max_p = initial * (1 + BOUND_VALUE);
            float original = newtaskperiod[i];
            float clamped = std::clamp(original, min_p, max_p);

            sharedData->newperiods[i] = clamped;
            upperbound[i] = max_p;
            lowerbound[i] = min_p;

#ifdef DEBUG
            if (clamped != original) {
                printf("Task %d clamped: original=%f clamped=%f min=%f max=%f\n",
                       i, original, clamped, min_p, max_p);
            }
#endif
        }
#else
        for (int i = 0; i < N; i++) {
            sharedData->newperiods[i] = newtaskperiod[i];
        }
#endif

        float measured = current_freq.load(std::memory_order_relaxed);
        float delta_freq = delta[N];
        float next = measured + delta_freq;

        const float max_up_step_mhz =
            env_float_or_default("GPU_FREQ_CMD_MAX_UP_STEP_MHZ", 0.0f);
        const float max_down_step_mhz =
            env_float_or_default("GPU_FREQ_CMD_MAX_DOWN_STEP_MHZ", 0.0f);
        if (max_up_step_mhz > 0.0f && next > measured + max_up_step_mhz) {
            next = measured + max_up_step_mhz;
        }
        if (max_down_step_mhz > 0.0f && next < measured - max_down_step_mhz) {
            next = measured - max_down_step_mhz;
        }
        delta_freq = next - measured;

#ifdef Jetson
        next = std::clamp(next, 54.0f, 1575.0f);
#else
        next = std::clamp(next, 210.0f, 2100.0f);
#endif

        current_freq.store(next, std::memory_order_relaxed);

        stopsigma.store(false, std::memory_order_relaxed);
        freqthread = std::thread(sigmadelta_freq_step, next);

        double ts = std::chrono::duration<double>(end - start).count();

        console_render_lqr_status(
            controlperiod,
            ts,
            N,
            measuredpower,
            measuredpowererror,
            measured,
            delta_freq,
            next,
            executiontime,
            responsetime,
            desiredresponsetime,
            rtr,
            error,
            taskperiod,
            newtaskperiod,
            deadlinemiss
        );

        ctrlLog << "time=" << ts << "  control_period=" << controlperiod << "\n";
        ctrlLog << "task\texec(ms)\tresp(ms)\tdes_resp(ms)\trtr\terror\tPcur(ms)\tPnext(ms)\tDMR(%)\n";
        ctrlLog << std::fixed << std::setprecision(3);

        for (int i = 0; i < N; i++)
        {
            ctrlLog << "T" << (i + 1) << "\t"
                    << executiontime[i] << "\t"
                    << responsetime[i]  << "\t"
                    << desiredresponsetime[i] << "\t"
                    << rtr[i]           << "\t"
                    << error[i]         << "\t"
                    << taskperiod[i]    << "\t"
                    << newtaskperiod[i] * 1000.0f << "\t"
                    << deadlinemiss[i]  << "\n";

            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                log[i].filewritexec.push_back(executiontime[i]);
                log[i].filewriteresponse.push_back(responsetime[i]);
                log[i].filewriteperiod.push_back(taskperiod[i]);
                log[i].filewritertr.push_back(rtr[i]);
                log[i].filewritelowperiodbound.push_back(lowerbound[i] * 1000.0f);
                log[i].filewritehighperiodbound.push_back(upperbound[i] * 1000.0f);
                log[i].filewritedeadlinemiss.push_back(deadlinemiss[i]);
            }
        }

        logsys.power.powersetpoints.push_back(powersetpoint);
        logsys.power.powerseterror.push_back(measuredpowererror);
        logsys.power.powercontrolperiod.push_back(measuredpower);

        ctrlLog << "Power\t" << measuredpower
                << "\tPerror\t" << measuredpowererror
                << "\tDeltaFreq\t" << delta_freq << "\n";

        ctrlLog << "*****************************************************************\n\n";
        ctrlLog.flush();

        controlperiod++;
    }

    stopsigma.store(true, std::memory_order_relaxed);
    if (freqthread.joinable()) {
        freqthread.join();
    }

    delete[] delta;
    delete[] error;
    delete[] rtr;
    delete[] upperbound;
    delete[] lowerbound;
    delete[] executiontime;
    delete[] responsetime;
    delete[] desiredresponsetime;
    delete[] taskperiod;
    delete[] newtaskperiod;
    delete[] deadlinemiss;
}


// ===== Task-arrival LQR control logic BEGIN =====
// solution = 8
// 0-120s: control task0/task1/task2 + power
// >=120s: control task0/task1/task2/task3 + power
// This does NOT modify the original proposed() path.
void task_arrival_lqr(std::string path,
                      logging& log,
                      tasks& t,
                      int numtasks,
                      float** gain,
                      std::atomic<bool>& controllerlooping,
                      float powersetpoint,
                      logging_sys& logsys)
{
    std::cout << "[TASK_ARRIVAL_LQR] running with " << numtasks
              << " total tasks; task3 arrives at 120s\n";

    auto start = std::chrono::steady_clock::now();
    int controlperiod = 0;
    int N = numtasks;
    const double arrival_time_sec = 120.0;

    if (N < 4) {
        std::cerr << "[TASK_ARRIVAL_LQR] WARNING: expected 4 tasks, got "
                  << N << ". Will still run with available tasks.\n";
    }

    float* delta = new float[N + 1];
    float* error = new float[N + 1];

    float* rtr = new float[N];
    float* upperbound = new float[N];
    float* lowerbound = new float[N];
    float* executiontime = new float[N];
    float* responsetime = new float[N];
    float* desiredresponsetime = new float[N];
    float* taskperiod = new float[N];
    float* newtaskperiod = new float[N];
    float* deadlinemiss = new float[N];

    std::thread freqthread;

    float measuredpower = 0.0f;
    float measuredpowererror = 0.0f;

    average average;
    std::ofstream ctrlLog("logs/controller.txt", std::ios::app);

    std::filesystem::path base_path(path);
    std::vector<std::string> exec_paths(N);
    std::vector<std::string> resp_paths(N);

    for (int i = 0; i < N; ++i) {
        exec_paths[i] = (base_path / ("taskexecutiontime" + std::to_string(i) + ".txt")).string();
        resp_paths[i] = (base_path / ("taskresponsetime" + std::to_string(i) + ".txt")).string();
    }

    while (controllerlooping.load(std::memory_order_relaxed))
    {
        std::this_thread::sleep_for(std::chrono::duration<float>(innerloopduration));

        stopsigma.store(true, std::memory_order_relaxed);
        if (freqthread.joinable()) {
            freqthread.join();
        }

        auto end = std::chrono::steady_clock::now();
        double ts = std::chrono::duration<double>(end - start).count();

        int activeN = (ts < arrival_time_sec) ? std::min(3, N) : N;

        // Initialize all arrays every control period.
        // Inactive task keeps initial period and zero error.
        for (int i = 0; i < N; i++) {
            delta[i] = 0.0f;
            error[i] = 0.0f;

            rtr[i] = 0.0f;
            executiontime[i] = 0.0f;
            responsetime[i] = 0.0f;
            deadlinemiss[i] = 0.0f;

            taskperiod[i] = t[i].initial_rate * 1000.0f;   // ms
            desiredresponsetime[i] = t[i].setpoint * taskperiod[i];
            newtaskperiod[i] = t[i].initial_rate;          // seconds

#ifdef CLAMP_PERIODS
            lowerbound[i] = t[i].initial_rate * (1.0f - BOUND_VALUE);
            upperbound[i] = t[i].initial_rate * (1.0f + BOUND_VALUE);
#else
            lowerbound[i] = t[i].initial_rate;
            upperbound[i] = t[i].initial_rate;
#endif
        }

        // Only consume logs from active tasks.
        // Before 120s, task3 logs are not touched.
        for (int i = 0; i < activeN; i++) {
            std::vector<float> local_rtr, local_resp, local_per, local_exec;
            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                local_rtr  = std::move(log[i].rtr);
                local_resp = std::move(log[i].response);
                local_per  = std::move(log[i].period);
                local_exec = std::move(log[i].exec);
            }

            // TASK_ARRIVAL_EMPTY_SAMPLE_GUARD
            // If no samples arrived in this control window, keep this task unchanged.
            // This avoids P(ms)=0 and negative Pn(ms) artifacts.
            if (local_per.empty() || local_resp.empty()) {
                rtr[i] = 0.0f;
                responsetime[i] = 0.0f;
                executiontime[i] = 0.0f;
                taskperiod[i] = t[i].initial_rate * 1000.0f;   // ms
                desiredresponsetime[i] = 0.0f;
                deadlinemiss[i] = 0.0f;
                error[i] = 0.0f;
            } else {
                rtr[i]           = average.calculateAverage(local_rtr);
                responsetime[i]  = average.calculateAverage(local_resp);
                taskperiod[i]    = average.calculateAverage(local_per);
                executiontime[i] = average.calculateAverage(local_exec);

                desiredresponsetime[i] = t[i].setpoint * taskperiod[i];
                deadlinemiss[i] = calculate_deadline_miss(local_resp, local_per, 0.00f);
                error[i] = desiredresponsetime[i] - responsetime[i];
            }

            if (append_lock(exec_paths[i], "Control Period") < 0) {
                std::cout << "Error in task_arrival_lqr\n";
            }
            if (append_lock(resp_paths[i], "Control Period") < 0) {
                std::cout << "Error in task_arrival_lqr\n";
            }
        }

        std::vector<float> local_power;
        {
            local_power = std::move(logsys.power.measuredpower);
        }

        if (local_power.empty()) {
            measuredpower = 0.0f;
            measuredpowererror = 0.0f;
        } else {
            measuredpower = average.calculateAverage(local_power);
            measuredpowererror = powersetpoint - measuredpower;
        }
        error[N] = measuredpowererror;

        // Use full N+1 gain matrix.
        // Before arrival, task3 error is zero, so it does not contribute.
        for (int i = 0; i < N + 1; i++) {
            delta[i] = 0.0f;
            for (int j = 0; j < N + 1; j++) {
                delta[i] += error[j] * (-gain[i][j]);
            }
        }

        // Do not actuate inactive task before arrival.
        for (int i = activeN; i < N; i++) {
            delta[i] = 0.0f;
        }

        for (int i = 0; i < activeN; i++)
        {
            newtaskperiod[i] = taskperiod[i] + delta[i];   // ms
            newtaskperiod[i] = newtaskperiod[i] / 1000.0f; // seconds
        }

#ifdef CLAMP_PERIODS
        for (int i = 0; i < N; i++) {
            float initial = t[i].initial_rate;
            float min_p = initial * (1.0f - BOUND_VALUE);
            float max_p = initial * (1.0f + BOUND_VALUE);
            float original = newtaskperiod[i];

            if (i < activeN) {
                float clamped = std::clamp(original, min_p, max_p);
                sharedData->newperiods[i] = clamped;
                newtaskperiod[i] = clamped;
            } else {
                sharedData->newperiods[i] = initial;
                newtaskperiod[i] = initial;
            }

            lowerbound[i] = min_p;
            upperbound[i] = max_p;
        }
#else
        for (int i = 0; i < N; i++) {
            if (i < activeN) {
                sharedData->newperiods[i] = newtaskperiod[i];
            } else {
                sharedData->newperiods[i] = t[i].initial_rate;
                newtaskperiod[i] = t[i].initial_rate;
            }
        }
#endif

        float measured = current_freq.load(std::memory_order_relaxed);
        float delta_freq = delta[N];
        float next = measured + delta_freq;

#ifdef Jetson
        //next = std::clamp(next, 306.0f, 1020.0f);
        next = std::clamp(next, 54.0f, 1575.0f);
#else
        next = std::clamp(next, 210.0f, 2100.0f);
#endif

        current_freq.store(next, std::memory_order_relaxed);

        stopsigma.store(false, std::memory_order_relaxed);
        freqthread = std::thread(sigmadelta_freq_step, next);

        console_render_lqr_status(
            controlperiod,
            ts,
            N,
            measuredpower,
            measuredpowererror,
            measured,
            delta_freq,
            next,
            executiontime,
            responsetime,
            desiredresponsetime,
            rtr,
            error,
            taskperiod,
            newtaskperiod,
            deadlinemiss
        );

        ctrlLog << "time=" << ts
                << "  control_period=" << controlperiod
                << "  active_tasks=" << activeN
                << "  arrival_time_sec=" << arrival_time_sec
                << "\n";

        ctrlLog << "task\texec(ms)\tresp(ms)\tdes_resp(ms)\trtr\terror\tPcur(ms)\tPnext(ms)\tDMR(%)\tactive\n";
        ctrlLog << std::fixed << std::setprecision(3);

        for (int i = 0; i < N; i++)
        {
            ctrlLog << "T" << (i + 1) << "\t"
                    << executiontime[i] << "\t"
                    << responsetime[i]  << "\t"
                    << desiredresponsetime[i] << "\t"
                    << rtr[i]           << "\t"
                    << error[i]         << "\t"
                    << taskperiod[i]    << "\t"
                    << newtaskperiod[i] * 1000.0f << "\t"
                    << deadlinemiss[i]  << "\t"
                    << ((i < activeN) ? 1 : 0)
                    << "\n";

            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                log[i].filewritexec.push_back(executiontime[i]);
                log[i].filewriteresponse.push_back(responsetime[i]);
                log[i].filewriteperiod.push_back(taskperiod[i]);
                log[i].filewritertr.push_back(rtr[i]);
                log[i].filewritelowperiodbound.push_back(lowerbound[i] * 1000.0f);
                log[i].filewritehighperiodbound.push_back(upperbound[i] * 1000.0f);
                log[i].filewritedeadlinemiss.push_back(deadlinemiss[i]);
            }
        }

        logsys.power.powersetpoints.push_back(powersetpoint);
        logsys.power.powerseterror.push_back(measuredpowererror);
        logsys.power.powercontrolperiod.push_back(measuredpower);

        ctrlLog << "Power\t" << measuredpower
                << "\tPerror\t" << measuredpowererror
                << "\tDeltaFreq\t" << delta_freq
                << "\tActiveTasks\t" << activeN
                << "\n";

        ctrlLog << "*****************************************************************\n\n";
        ctrlLog.flush();

        controlperiod++;
    }

    stopsigma.store(true, std::memory_order_relaxed);
    if (freqthread.joinable()) {
        freqthread.join();
    }

    delete[] delta;
    delete[] error;
    delete[] rtr;
    delete[] upperbound;
    delete[] lowerbound;
    delete[] executiontime;
    delete[] responsetime;
    delete[] desiredresponsetime;
    delete[] taskperiod;
    delete[] newtaskperiod;
    delete[] deadlinemiss;
}
// ===== Task-arrival LQR control logic END =====


void openloop(std::string path,
              logging& log,
              tasks& t,
              int numtasks,
              std::atomic<bool>& controllerlooping,
              float powersetpoint,
              logging_sys& logsys)
{
    auto start = std::chrono::steady_clock::now();
    int controlperiod = 0;
    int N = numtasks;

    float* error = new float[N + 1];
    float* rtr = new float[N];
    float* executiontime = new float[N];
    float* responsetime = new float[N];
    float* desiredresponsetime = new float[N];
    float* taskperiod = new float[N];
    float* newtaskperiod = new float[N];
    float* deadlinemiss = new float[N];

    average average;
    std::ofstream ctrlLog("logs/controller.txt", std::ios::app);

    while (controllerlooping.load(std::memory_order_relaxed))
    {
        std::this_thread::sleep_for(std::chrono::duration<float>(innerloopduration));
        auto end = std::chrono::steady_clock::now();

        for (int i = 0; i < N; i++)
        {
            std::vector<float> local_rtr, local_resp, local_per, local_exec;
            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                local_rtr.swap(log[i].rtr);
                local_resp.swap(log[i].response);
                local_per.swap(log[i].period);
                local_exec.swap(log[i].exec);
            }

            rtr[i] = average.calculateAverage(local_rtr);
            responsetime[i] = average.calculateAverage(local_resp);
            taskperiod[i] = average.calculateAverage(local_per);
            executiontime[i] = average.calculateAverage(local_exec);
            desiredresponsetime[i] = t[i].setpoint * taskperiod[i];
            deadlinemiss[i] = calculate_deadline_miss(local_resp, local_per, 0.0f);

            error[i] = t[i].setpoint - rtr[i];

            // match LQR display convention exactly
            newtaskperiod[i] = taskperiod[i] / 1000.0f;
        }

        float measuredpower = average.calculateAverage(logsys.power.measuredpower);
        float measuredpowererror = powersetpoint - measuredpower;

        float measured = current_freq.load(std::memory_order_relaxed);
        float delta_freq = 0.0f;
        float next = measured;

        double ts = std::chrono::duration<double>(end - start).count();

        console_render_lqr_status(
            controlperiod,
            ts,
            N,
            measuredpower,
            measuredpowererror,
            measured,
            delta_freq,
            next,
            executiontime,
            responsetime,
            desiredresponsetime,
            rtr,
            error,
            taskperiod,
            newtaskperiod,
            deadlinemiss
        );

        ctrlLog << "time=" << ts << "  control_period=" << controlperiod << "\n";
        ctrlLog << "task\texec(ms)\tresp(ms)\tdes_resp(ms)\trtr\terror\tPcur(ms)\tPnext(ms)\tDMR(%)\n";
        ctrlLog << std::fixed << std::setprecision(3);

        for (int i = 0; i < N; i++)
        {
            ctrlLog << "T" << (i + 1) << "\t"
                    << executiontime[i] << "\t"
                    << responsetime[i]  << "\t"
                    << desiredresponsetime[i] << "\t"
                    << rtr[i]           << "\t"
                    << error[i]         << "\t"
                    << taskperiod[i]    << "\t"
                    << newtaskperiod[i] * 1000.0f << "\t"
                    << deadlinemiss[i]  << "\n";

            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                log[i].filewritexec.push_back(executiontime[i]);
                log[i].filewriteresponse.push_back(responsetime[i]);
                log[i].filewriteperiod.push_back(taskperiod[i]);
                log[i].filewritertr.push_back(rtr[i]);
                log[i].filewritedeadlinemiss.push_back(deadlinemiss[i]);
            }
        }

        logsys.power.powersetpoints.push_back(powersetpoint);
        logsys.power.powerseterror.push_back(measuredpowererror);
        logsys.power.powercontrolperiod.push_back(measuredpower);

        ctrlLog << "Power\t" << measuredpower
                << "\tPerror\t" << measuredpowererror
                << "\tDeltaFreq\t" << delta_freq << "\n";

        ctrlLog << "*****************************************************************\n\n";
        ctrlLog.flush();

        controlperiod++;
    }

    delete[] error;
    delete[] rtr;
    delete[] executiontime;
    delete[] responsetime;
    delete[] desiredresponsetime;
    delete[] taskperiod;
    delete[] newtaskperiod;
    delete[] deadlinemiss;
}


void FC_GPU_and_power( string path, logging& log, tasks& t,int numtasks,float** doublegain,std::atomic<bool>& controllerlooping,float powersetpoint,
    logging_sys& logsys)
{
    std::cout << "[FC_GPU+Power] running with " << numtasks << " tasks\n";

    auto start = std::chrono::steady_clock::now();
    int controlperiod = 0;
    int N = numtasks;

    float* delta = new float[N + 1];        
    float* error = new float[N + 1];          
    float* rtr = new float[N];
    float* upperbound = new float[N];
    float* lowerbound = new float[N];
    float* executiontime = new float[N];
    float* responsetime = new float[N];
    float* taskperiod = new float[N];
    float* newtaskperiod = new float[N];
    float* deadlinemiss = new float[N];
    std::thread freqthread;

    float measuredpower = 0.0f;
    float measuredpowererror = 0.0f;

    average average;
    std::ofstream ctrlLog("logs/controller.txt", std::ios::app);
    std::filesystem::path base_path(path);
    std::vector<std::string> exec_paths(N);
    std::vector<std::string> resp_paths(N);

    for (int i = 0; i < N; ++i) {
        exec_paths[i] = (base_path / ("taskexecutiontime" + std::to_string(i) + ".txt")).string();
        resp_paths[i] = (base_path / ("taskresponsetime" + std::to_string(i) + ".txt")).string();
    }

    while (controllerlooping.load(std::memory_order_relaxed))
    {
        std::this_thread::sleep_for(std::chrono::duration<float>(innerloopduration));

        stopsigma.store(true, std::memory_order_relaxed);
        if (freqthread.joinable()) {
            freqthread.join();
        }

        auto end = std::chrono::steady_clock::now();
        std::cout << "Control Period = " << controlperiod << "\n";

        for (int i = 0; i < N; i++) {
            std::vector<float> local_rtr, local_resp, local_per, local_exec;
            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                local_rtr  = std::move(log[i].rtr);
                local_resp = std::move(log[i].response);
                local_per  = std::move(log[i].period);
                local_exec = std::move(log[i].exec);
            }

            rtr[i]           = average.calculateAverage(local_rtr);
            responsetime[i]  = average.calculateAverage(local_resp);
            taskperiod[i]    = average.calculateAverage(local_per);
            executiontime[i] = average.calculateAverage(local_exec);

            std::cout << "Size" << i
                      << " samples: rtr=" << local_rtr.size()
                      << " resp=" << local_resp.size()
                      << " period=" << local_per.size()
                      << " exec=" << local_exec.size()
                      << "\n";

            deadlinemiss[i] = calculate_deadline_miss(local_resp, local_per, 0.00f);

            error[i] = t[i].setpoint - rtr[i];

            if (append_lock(exec_paths[i], "Control Period") < 0) cout << "Error in n+1";
            if (append_lock(resp_paths[i], "Control Period") < 0)  cout << "Error in n+1";

        }

        std::vector<float> local_power;
        {
            local_power = std::move(logsys.power.measuredpower);
        }

        measuredpower = average.calculateAverage(local_power);
        measuredpowererror = powersetpoint - measuredpower;
        error[N] = measuredpowererror;
        std::cout << "Measured Power = " << measuredpower
                  << " Error = " << measuredpowererror << "\n";

        for (int i = 0; i < N + 1; i++) {
            delta[i] = 0.0f;
            for (int j = 0; j < N + 1; j++) {
                delta[i] += error[j] * (-doublegain[i][j]);
            }
            std::cout << "delta[" << i << "] = " << delta[i] << "\n";
        }

        for (int i = 0; i < N; i++)
        {
            newtaskperiod[i] = taskperiod[i] + delta[i];
            newtaskperiod[i] = newtaskperiod[i] / 1000.0f;  // sharedData expects seconds
        }

#ifdef CLAMP_PERIODS
        for (int i = 0; i < N; i++) {
            float initial = t[i].initial_rate;
            float min_p = initial * (1 - BOUND_VALUE);
            float max_p = initial * (1 + BOUND_VALUE);
            float original = newtaskperiod[i];
            float clamped = std::clamp(original, min_p, max_p);

            sharedData->newperiods[i] = clamped;
            upperbound[i] = max_p;
            lowerbound[i] = min_p;

            if (clamped != original) {
                printf("Task %d clamped: original=%f clamped=%f min=%f max=%f\n",
                       i, original, clamped, min_p, max_p);
            }
        }
#else
        for (int i = 0; i < N; i++) {
            sharedData->newperiods[i] = newtaskperiod[i];
        }
#endif

        float measured = current_freq.load(std::memory_order_relaxed);
        float delta_freq = delta[N];
        float next = measured + delta_freq;
        #ifdef Jetson
            //next = std::clamp(next, 306.0f, 1020.0f); // change to jetson frew
            next = std::clamp(next, 54.0f, 1575.0f);
        #else
            next = std::clamp(next, 210.0f, 2100.0f);
        #endif
        current_freq.store(next, std::memory_order_relaxed);

        std::cout << "Current freq (SM) = " << measured << " MHz\n";
        std::cout << "Delta freq        = " << delta_freq << " MHz\n";
        std::cout << "New freq command  = " << next << " MHz\n";

        stopsigma.store(false, std::memory_order_relaxed);
        freqthread = std::thread(sigmadelta_freq_step, next);

        double ts = std::chrono::duration<double>(end - start).count();
        std::cout << "time=" << ts << "  control_period=" << controlperiod << "\n";
        ctrlLog  << "time=" << ts << "  control_period=" << controlperiod << "\n";

        std::cout << "task\texec(ms)\tresp(ms)\trtr\terror\tPcur(ms)\tPnext(ms)\tDeadline miss (%)\n";
        ctrlLog  << "task\texec(ms)\tresp(ms)\trtr\terror\tPcur(ms)\tPnext(ms)\tDeadline miss (%)\n";

        std::cout << std::fixed << std::setprecision(3);
        ctrlLog  << std::fixed << std::setprecision(3);

        for (int i = 0; i < N; i++)
        {
            std::cout << "T" << (i + 1) << "\t"
                      << executiontime[i] << "\t\t"
                      << responsetime[i]  << "\t\t"
                      << rtr[i]           << "\t"
                      << error[i]         << "\t"
                      << taskperiod[i]    << "\t"
                      << newtaskperiod[i] * 1000.0f << "\t"
                      << deadlinemiss[i]  << "\n";

            ctrlLog  << "T" << (i + 1) << "\t"
                     << executiontime[i] << "\t"
                     << responsetime[i]  << "\t"
                     << rtr[i]           << "\t"
                     << error[i]         << "\t"
                     << taskperiod[i]    << "\t"
                     << newtaskperiod[i] * 1000.0f << "\t"
                     << deadlinemiss[i]  << "\n";

            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                log[i].filewritexec.push_back(executiontime[i]);
                log[i].filewriteresponse.push_back(responsetime[i]);
                log[i].filewriteperiod.push_back(taskperiod[i]);
                log[i].filewritertr.push_back(rtr[i]);
                log[i].filewritelowperiodbound.push_back(lowerbound[i] * 1000.0f);
                log[i].filewritehighperiodbound.push_back(upperbound[i] * 1000.0f);
                log[i].filewritedeadlinemiss.push_back(deadlinemiss[i]);
            }
        }

        logsys.power.powersetpoints.push_back(powersetpoint);
        logsys.power.powerseterror.push_back(measuredpowererror);
        logsys.power.powercontrolperiod.push_back(measuredpower);

        ctrlLog << "Power\t" << measuredpower
                << "\tPerror\t" << measuredpowererror
                << "\tDeltaFreq\t" << delta_freq << "\n";

        std::cout << "*****************************************************************\n\n";
        ctrlLog  << "*****************************************************************\n\n";
        ctrlLog.flush();

        controlperiod++;
    }

    stopsigma.store(true, std::memory_order_relaxed);
    if (freqthread.joinable()) {
        freqthread.join();
    }

    delete[] delta;
    delete[] error;
    delete[] rtr;
    delete[] lowerbound;
    delete[] upperbound;
    delete[] executiontime;
    delete[] responsetime;
    delete[] taskperiod;
    delete[] newtaskperiod;
    delete[] deadlinemiss;
}


void FC_GPU(string path,logging& log, tasks& t, int numtasks,float** gain,std::atomic<bool>& controllerlooping, float powersetpoint,
           logging_sys& logsys)
{
    std::cout << "[FC_GPU] running with " << numtasks << " tasks\n";
    auto start = std::chrono::steady_clock::now();
    int controlperiod=0;
    float*delta;
    float*error;
    float*rtr;
    float*measuredpower;
    float*measuredpowererror;
    float*upperbound;
    float*lowerbound;
    float*executiontime;
    float*responsetime;
    float*taskperiod;
    float*newtaskperiod;
    float*deadlinemiss;
    measuredpower= new float[1];
    measuredpowererror= new float[1];
    delta= new float[numtasks];
    error=new float[numtasks];
    rtr= new float[numtasks];
    executiontime=new float[numtasks];
    responsetime=new float[numtasks];
    taskperiod=new float[numtasks];
    newtaskperiod=new float[numtasks];
    deadlinemiss=new float[numtasks];
    upperbound=new float[numtasks];
    lowerbound=new float[numtasks];
    int lastracker=0;
    average average;
    std::ofstream ctrlLog("logs/controller.txt", std::ios::app);
    std::filesystem::path base_path(path);
    std::vector<std::string> exec_paths(numtasks);
    std::vector<std::string> resp_paths(numtasks);

    for (int i = 0; i < numtasks; ++i) {
        exec_paths[i] = (base_path / ("taskexecutiontime" + std::to_string(i) + ".txt")).string();
        resp_paths[i] = (base_path / ("taskresponsetime" + std::to_string(i) + ".txt")).string();
    }

    #ifdef POWER_INTERRUPT
    bool is_interrupted = false;
    #else
    bool is_interrupted = true;
    #endif

    while (controllerlooping.load(std::memory_order_relaxed))
    {
        if (!is_interrupted && powerinterrup.load(std::memory_order_relaxed)) {
            is_interrupted = true;
            powersetpoint = powersetpoint - 1000;
            std::cout << "[POWER_INTERRUPT] new powersetpoint = " << powersetpoint << "\n";
        }
        std::this_thread::sleep_for(std::chrono::duration<float>(innerloopduration));
        auto end = std::chrono::steady_clock::now();
        std::cout<<"Control Period = "<<controlperiod<<"\n";
        for (int i = 0; i < numtasks; i++) {
            std::vector<float> local_rtr, local_resp, local_per, local_exec;
            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                local_rtr  = std::move(log[i].rtr);
                local_resp = std::move(log[i].response);
                local_per  = std::move(log[i].period);
                local_exec = std::move(log[i].exec);
                // log[i].* are now empty
            }// unlock here
        

            float avg_rtr  = average.calculateAverage(local_rtr);
            float avg_resp = average.calculateAverage(local_resp);
            float avg_per  = average.calculateAverage(local_per);
            float avg_exec = average.calculateAverage(local_exec);

            bool valid_sample =
                (!local_rtr.empty()) &&
                (!local_per.empty()) &&
                (avg_rtr > 0.0f) &&
                (avg_per > 0.0f);

            bool rtr_spike = valid_sample && (avg_rtr > 2.0f);

            if (valid_sample) {
                // Always log the measured values.
                rtr[i]          = avg_rtr;
                responsetime[i] = avg_resp;
                taskperiod[i]   = avg_per;
                executiontime[i]= avg_exec;
            } else {
                // Empty/invalid control window: keep last valid state.
                // This prevents 0 RTR / 0 period from entering FC control.
                std::cout << "[FC_GPU] task " << i
                          << " invalid sample, keep last state"
                          << " rtr_samples=" << local_rtr.size()
                          << " period_samples=" << local_per.size()
                          << "\n";
            }

            std::cout << "Size" << i
              << " samples: rtr=" << local_rtr.size()
              << " resp=" << local_resp.size()
              << " period=" << local_per.size()
              << " exec=" << local_exec.size()
              << "\n";

            float deadline=calculate_deadline_miss(local_resp,local_per,0.00);
            deadlinemiss[i]=deadline;

            local_rtr.clear();
            local_resp.clear();
            local_per.clear();
            local_exec.clear();

            if (rtr_spike) {
                // Do not let one extreme RTR spike dominate FC period update.
                // Keep current period command by setting zero control error.
                //error[i] = 0.0f;
                error[i] = t[i].setpoint - rtr[i];
                std::cout << "[FC_GPU] task " << i
                          << " RTR spike ignored for control: " << avg_rtr << "\n";
            } else {
                error[i] = t[i].setpoint - rtr[i];
            }
            if (append_lock(exec_paths[i], "Control Period") < 0)  cout << "Error \n\nin FC\n\n";            
            if (append_lock(resp_paths[i], "Control Period") < 0) cout << "Error \n\nin FC\n\n";
       
        }
        std::vector<float> loacl_power, local_perror;
        {
        loacl_power=std::move(logsys.power.measuredpower);

        }
        measuredpower[0]= average.calculateAverage(loacl_power);
        measuredpowererror[0]=powersetpoint-measuredpower[0];
        std::cout<<"Meaured Power = "<<measuredpower[0]<<"Error = "<<measuredpowererror[0]<<endl;
        
        
        
        //fc-controller
        for(int i=0; i<numtasks; i++)
            {
            delta[i] = 0.0;
            delta[i]= delta[i]+error[i]*-0.9;  
           // delta[i]= delta[i]+error[i]*-gain[i][i];  
	    //for(int j=0; j<numtasks; j++)
            //{   
            // delta[i]= delta[i]+error[j]*-gain[i][j];  
            //

            //}
            std::cout<<"delta ["<<i<<"]="<<delta[i]<<endl;
        }
        
        
             //fc-actuator

        float sumP = 0.0f;
        for (int i = 0; i < numtasks; i++)
            sumP += taskperiod[i];

        for (int i = 0; i < numtasks; i++) 
        {
            float sumOthers = sumP - taskperiod[i];
            float denom = 1.0f + taskperiod[i] * sumOthers * delta[i];
            std::cout<<"denom = \t"<<denom<<"\n";
            //std::cout<<taskperiod[i] / denom<<"\n";
            //newtaskperiod[i]=taskperiod[i]+ (taskperiod[i] / denom);
            //newtaskperiod[i]=newtaskperiod[i]/1000;
           newtaskperiod[i]=taskperiod[i]+delta[i];
           newtaskperiod[i]=newtaskperiod[i]/1000;
	   if (newtaskperiod[i] < 0.001) newtaskperiod[i] = 0.005;
           //newtaskperiod[i] = std::sqrt(newtaskperiod[i]);

        }
        
        #ifdef CLAMP_PERIODS
        for (int i = 0; i < numtasks; i++) {
            float initial = t[i].initial_rate;
            float min_p = initial * (1-BOUND_VALUE);
            float max_p = initial * (1+BOUND_VALUE);
            float original = newtaskperiod[i];
            float clamped = std::clamp(original, min_p, max_p);
            sharedData->newperiods[i] = clamped;
            //sharedData->newperiods[i] = std::clamp(newtaskperiod[i], min_p, max_p);  
            upperbound[i]=max_p;
            lowerbound[i]=min_p;
            if (clamped != original) 
            {
                printf("Task %d clamped: original=%f clamped=%f min=%f max=%f\n",i, original, clamped, min_p, max_p);}
                upperbound[i]=max_p;
                lowerbound[i]=min_p;
            }
        #else
        for (int i = 0; i < numtasks; i++) {
            sharedData->newperiods[i] = newtaskperiod[i];
        }
        #endif
   
        
        

        double ts = std::chrono::duration<double>(end - start).count();
        std::cout << "time=" << ts << "  control_period=" << controlperiod << "\n";
        ctrlLog  << "time=" << ts << "  control_period=" << controlperiod << "\n";

        std::cout << "task\texec(ms)\tresp(ms)\trtr\terror\tPcur(s)\tPnext(ms)\tDeadline miss (%)\n";
        ctrlLog  << "task\texec(ms)\tresp(ms)\trtr\terror\tPcur(s)\tPnext(ms)\tDeadline miss (%)\n";

        std::cout << std::fixed << std::setprecision(3);
        ctrlLog  << std::fixed << std::setprecision(3);

        for (int i = 0; i < numtasks; i++)
        {
            std::cout << "T" << (i + 1) << "\t"
                      << executiontime[i] << "\t\t"
                      << responsetime[i]  << "\t\t"
                      << rtr[i]           << "\t"
                      << error[i]         << "\t"
                      << taskperiod[i]    << "\t"
                      <<newtaskperiod[i]*1000 << "\t"
                      <<deadlinemiss[i]<<"\n";

            ctrlLog  << "T" << (i + 1) << "\t"
                     << executiontime[i] << "\t"
                     << responsetime[i]  << "\t"
                     << rtr[i]           << "\t"
                     << error[i]         << "\t"
                     << taskperiod[i]*1000    << "\t"
                     << newtaskperiod[i] << "\n";

            // Thread-safe append to filewrite buffers
            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                log[i].filewritexec.push_back(executiontime[i]);
                log[i].filewriteresponse.push_back(responsetime[i]);
                log[i].filewriteperiod.push_back(taskperiod[i]);
                log[i].filewritertr.push_back(rtr[i]);
                log[i].filewritelowperiodbound.push_back(lowerbound[i]*1000);
                log[i].filewritehighperiodbound.push_back(upperbound[i]*1000);
                log[i].filewritedeadlinemiss.push_back(deadlinemiss[i]);
            }
            
        }
        logsys.power.powersetpoints.push_back(powersetpoint);
        logsys.power.powerseterror.push_back(measuredpowererror[0]);
        logsys.power.powercontrolperiod.push_back(measuredpower[0]);
        std::cout << "*****************************************************************\n\n";
        ctrlLog  << "*****************************************************************\n\n";
        ctrlLog.flush();
        controlperiod=controlperiod+1;
      
    
    }
     // for (int i = 0; i < numtasks; ++i) {
       // exec_paths[i].close();
       // resp_paths[i].close();
    //}
 
    delete[]measuredpower;
    delete[]measuredpowererror;
    delete[] delta;
    delete[] error;
    delete[] rtr;
    delete[] lowerbound;
    delete[] upperbound;
    delete[] executiontime;
    delete[] responsetime;
    delete[] taskperiod;
    delete[] newtaskperiod;
    delete[] deadlinemiss;
}

void FC_GPU_power_only(std::string path,
                       logging& log,
                       tasks& t,
                       int numtasks,
                       std::atomic<bool>& controllerlooping,
                       float powersetpoint,
                       logging_sys& logsys)
{
    std::cout << "[FC_GPU power-only] running with " << numtasks << " tasks\n";

    auto start = std::chrono::steady_clock::now();
    int controlperiod = 0;

    std::thread freqthread;
    average average;
    std::ofstream ctrlLog("logs/controller.txt", std::ios::app);

    float* rtr = new float[numtasks];
    float* executiontime = new float[numtasks];
    float* responsetime = new float[numtasks];
    float* desiredresponsetime = new float[numtasks];
    float* error = new float[numtasks];
    float* taskperiod = new float[numtasks];
    float* newtaskperiod = new float[numtasks];
    float* deadlinemiss = new float[numtasks];
    float* lowerbound = new float[numtasks];
    float* upperbound = new float[numtasks];

    std::filesystem::path base_path(path);
    std::vector<std::string> exec_paths(numtasks);
    std::vector<std::string> resp_paths(numtasks);

    for (int i = 0; i < numtasks; ++i) {
        exec_paths[i] = (base_path / ("taskexecutiontime" + std::to_string(i) + ".txt")).string();
        resp_paths[i] = (base_path / ("taskresponsetime" + std::to_string(i) + ".txt")).string();
    }

    while (controllerlooping.load(std::memory_order_relaxed))
    {
        std::this_thread::sleep_for(std::chrono::duration<float>(innerloopduration));

        stopsigma.store(true, std::memory_order_relaxed);
        if (freqthread.joinable()) {
            freqthread.join();
        }

        auto end = std::chrono::steady_clock::now();

        // ---- observe task timing, but DO NOT use it for control ----
        for (int i = 0; i < numtasks; i++) {
            std::vector<float> local_rtr, local_resp, local_per, local_exec;
            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                local_rtr  = std::move(log[i].rtr);
                local_resp = std::move(log[i].response);
                local_per  = std::move(log[i].period);
                local_exec = std::move(log[i].exec);
            }

            rtr[i]           = average.calculateAverage(local_rtr);
            responsetime[i]  = average.calculateAverage(local_resp);
            taskperiod[i]    = average.calculateAverage(local_per);
            executiontime[i] = average.calculateAverage(local_exec);
            deadlinemiss[i]  = calculate_deadline_miss(local_resp, local_per, 0.00f);

            // Only for display / analysis, not for control
            desiredresponsetime[i] = t[i].setpoint * taskperiod[i];
            error[i] = desiredresponsetime[i] - responsetime[i];

            // power-only baseline: period is fixed at initial rate
            newtaskperiod[i] = t[i].initial_rate;          // seconds
            lowerbound[i] = t[i].initial_rate * 1000.0f;  // ms
            upperbound[i] = t[i].initial_rate * 1000.0f;  // ms

            if (append_lock(exec_paths[i], "Control Period") < 0) {
                std::cout << "Error in FC_GPU_power_only\n";
            }
            if (append_lock(resp_paths[i], "Control Period") < 0) {
                std::cout << "Error in FC_GPU_power_only\n";
            }
        }

        // ---- keep task periods fixed: do NOT control RTR / do NOT change periods ----
        for (int i = 0; i < numtasks; i++) {
            sharedData->newperiods[i] = t[i].initial_rate;
        }

        // ---- power measurement ----
        std::vector<float> local_power;
        {
            local_power = std::move(logsys.power.measuredpower);
        }

        float measuredpower = average.calculateAverage(local_power);
        float measuredpowererror = powersetpoint - measuredpower;

        // ---- frequency control only ----
        float measured = current_freq.load(std::memory_order_relaxed);

        // measuredpower is in mW in current Jetson path
        constexpr float kp_mhz_per_mw = 0.01f;
        float delta_freq = kp_mhz_per_mw * measuredpowererror;
        float next = measured + delta_freq;

    #ifdef Jetson
        //next = std::clamp(next, 306.0f, 1020.0f);
        next = std::clamp(next, 54.0f, 1575.0f);
    #else
        next = std::clamp(next, 210.0f, 2100.0f);
    #endif

        current_freq.store(next, std::memory_order_relaxed);

        stopsigma.store(false, std::memory_order_relaxed);
        freqthread = std::thread(sigmadelta_freq_step, next);

        // ---- unified display ----
        double ts = std::chrono::duration<double>(end - start).count();

        console_render_lqr_status(
            controlperiod,
            ts,
            numtasks,
            measuredpower,
            measuredpowererror,
            measured,
            delta_freq,
            next,
            executiontime,
            responsetime,
            desiredresponsetime,
            rtr,
            error,
            taskperiod,
            newtaskperiod,
            deadlinemiss
        );

        // ---- logging ----
        ctrlLog << "time=" << ts << "  control_period=" << controlperiod << "\n";
        ctrlLog << "task\texec(ms)\tresp(ms)\tdes_resp(ms)\trtr\terror\tPcur(ms)\tPfixed(ms)\tDMR(%)\n";
        ctrlLog << std::fixed << std::setprecision(3);

        for (int i = 0; i < numtasks; i++)
        {
            ctrlLog << "T" << (i + 1) << "\t"
                    << executiontime[i] << "\t"
                    << responsetime[i]  << "\t"
                    << desiredresponsetime[i] << "\t"
                    << rtr[i]           << "\t"
                    << error[i]         << "\t"
                    << taskperiod[i]    << "\t"
                    << newtaskperiod[i] * 1000.0f << "\t"
                    << deadlinemiss[i]  << "\n";

            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                log[i].filewritexec.push_back(executiontime[i]);
                log[i].filewriteresponse.push_back(responsetime[i]);
                log[i].filewriteperiod.push_back(taskperiod[i]);
                log[i].filewritertr.push_back(rtr[i]);
                log[i].filewritedeadlinemiss.push_back(deadlinemiss[i]);
                log[i].filewritelowperiodbound.push_back(lowerbound[i]);
                log[i].filewritehighperiodbound.push_back(upperbound[i]);
            }
        }

        logsys.power.powersetpoints.push_back(powersetpoint);
        logsys.power.powerseterror.push_back(measuredpowererror);
        logsys.power.powercontrolperiod.push_back(measuredpower);

        ctrlLog << "Power\t" << measuredpower
                << "\tPerror\t" << measuredpowererror
                << "\tCurrentFreq\t" << measured
                << "\tDeltaFreq\t" << delta_freq
                << "\tNextFreq\t" << next << "\n";
        ctrlLog << "*****************************************************************\n\n";
        ctrlLog.flush();

        controlperiod++;
    }

    stopsigma.store(true, std::memory_order_relaxed);
    if (freqthread.joinable()) {
        freqthread.join();
    }

    delete[] rtr;
    delete[] executiontime;
    delete[] responsetime;
    delete[] desiredresponsetime;
    delete[] error;
    delete[] taskperiod;
    delete[] newtaskperiod;
    delete[] deadlinemiss;
    delete[] lowerbound;
    delete[] upperbound;
}

    
void adhoc(logging& log, tasks& t, int numtasks, std::atomic<bool>& controllerlooping, float powersetpoint, logging_sys& logsys)
{
    std::cout << "[adhoc] running\n";
}

void siso(logging& log, tasks& t, int numtasks, std::atomic<bool>& controllerlooping, float powersetpoint, logging_sys& logsys)
{
    std::cout << "[siso] running\n";
}


void monitor(logging* log, logging_sys*plog, int numtasks)
{
    if (!log || !sharedData) return;
    std::cout<<"Begin monitor \n";
    std::vector<float> prevResp(numtasks, std::numeric_limits<float>::quiet_NaN());
    std::vector<float> prevExec(numtasks, std::numeric_limits<float>::quiet_NaN());
    float prevpower;

    using clock = std::chrono::high_resolution_clock;
    while (monitorthread.load())   
    {
        auto start = clock::now();
        std::chrono::duration<double> elapsed(0);
        while (elapsed.count() < innerloopduration && outerlooprunning.load())
        {
            elapsed = clock::now() - start;

            for (int i = 0; i < numtasks; ++i)
            {
                float resp = sharedData->responsetime[i];
                float gpu_exec = sharedData->executiontime[i];
                if (resp != prevResp[i])
                {
                    (*log)[i].add_rt(resp);   
                    (*log)[i].outeradd_rt(resp);         
                    float period_ms = sharedData->newperiods[i];
                    (*log)[i].add_period(period_ms*1000.0f); 
                    (*log)[i].outeradd_period(period_ms); 
                    if (period_ms > 0.0f){
                        (*log)[i].add_rtr(resp / (period_ms * 1000.0f));
                        (*log)[i].outeradd_rtr(resp / (period_ms * 1000.0f));
                    }
                    else{
                        (*log)[i].add_rtr(0.0f);
                        (*log)[i].outeradd_rtr(0.0f);
                    }
                    prevResp[i] = resp;
                }
                float exec = sharedData->executiontime[i];
                if (exec != prevExec[i])
                {
                    (*log)[i].add_exec(exec);
                    (*log)[i].outeradd_exec(exec);
                    prevExec[i] = exec;
                }
            }
            float power = static_cast<float>(returnpowerrtx());
            if (g_power_backend != "thor" && g_power_backend != "tegrastats" &&
                power > 0.0f && power < 20000.0f) {
                power += shell_equiv_power_mw();
            }
            //if (power != prevpower)
                //{
                (*plog).power.add_measuredpower(power);
                // }
            //prevpower=power;
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
}






volatile sig_atomic_t readyCount = 0;
void signalHandler(int) {
    readyCount++;
}



using Matrix = Eigen::MatrixXf;
// Discrete Algebraic Riccati Equation (iterative solve)
static Matrix solveDARE(const Matrix& A,
                        const Matrix& B,
                        const Matrix& Q,
                        const Matrix& R,
                        int max_iters = 10000,
                        float tol = 1e-6f)
{
    Matrix P = Q;
    Matrix Pnext = Q;

    for (int k = 0; k < max_iters; ++k) {
        Matrix S = R + B.transpose() * P * B;
        Matrix Ktmp = S.inverse() * (B.transpose() * P * A);

        Pnext = A.transpose() * P * A
              - A.transpose() * P * B * Ktmp
              + Q;

        float err = (Pnext - P).cwiseAbs().maxCoeff();
        P = Pnext;

        if (err < tol) {
            return P;
        }
    }

    throw std::runtime_error("solveDARE: Riccati iteration did not converge");
}

// Discrete-time LQR solve
static Matrix dlqr(const Matrix& A,
                   const Matrix& B,
                   const Matrix& Q,
                   const Matrix& R)
{
    Matrix P = solveDARE(A, B, Q, R);
    Matrix K = (R + B.transpose() * P * B).inverse() * (B.transpose() * P * A);
    return K;
}

void compute_LQR_gain(float** gain, int numtasks)
{

    const float base_last_col_full[6] = {
        0.06238100f,
        0.06804800f,
        0.07260400f,
        0.10549000f,
        0.02831200f,
        0.08079800f
    };

    const float base_last_row_full[6] = {
        0.02220753300f,
        0.01107223000f,
        0.02852230300f,
        0.0738135200f,
        0.01356965500f,
        0.01528722400f
    };

    const float base_bottom_right = 0.00116413f;

    const int N = numtasks;
    const int n = N + 1;

    //matrix A
    Matrix A = Matrix::Identity(n, n);
    for (int i = 0; i < n; ++i) {
        A(i, i) = 0.95f;
    }

    //B matrix
    Matrix B = Matrix::Zero(n, n);

    //top-left nxn block (period -> RT error)
    //non-trained diagonal values.
    for (int i = 0; i < N; ++i) {
        B(i, i) = 1.0f;
    }

    //last column (freq -> RT error)
    for (int i = 0; i < N; ++i) {
        B(i, N) = base_last_col_full[i];
    }

    //bottom row  (period -> power error)
    for (int j = 0; j < N; ++j) {
        B(N, j) = base_last_row_full[j];
    }

    //Bottom right value (freq vs power)
    B(N, N) = -base_bottom_right;

    //Q matrix = state penalty
    Matrix Q = Matrix::Zero(n, n);
    for (int i = 0; i < N; ++i) {
        Q(i, i) = 20.0f;   // RT error weight
    }
    Q(N, N) = 10.0f;       // power error weight

    //R matrix = input penalty
    Matrix R = Matrix::Zero(n, n);
    for (int i = 0; i < N; ++i) {
        R(i, i) = 1.0f;    // period adjustment penalty
    }
    R(N, N) = 10.0f;       // frequency adjustment penalty

    //Solve LQR
    Matrix K = dlqr(A, B, Q, R);

    //move to float** gain
    for (int i = 0; i < n; ++i) {
        for (int j = 0; j < n; ++j) {
            gain[i][j] = K(i, j);
        }
    }

    #ifdef DEBUG
        std::cout << "numtasks = " << numtasks << "\n\n";
        std::cout << "A =\n" << A << "\n\n";
        std::cout << "B =\n" << B << "\n\n";
        std::cout << "Q =\n" << Q << "\n\n";
        std::cout << "R =\n" << R << "\n\n";
        std::cout << "LQR gain K =\n" << K << "\n\n";
    #endif
}



void dfs(std::string path,
                    logging& log,
                    tasks& t,
                    int numtasks,
                    std::atomic<bool>& controllerlooping,
                    float powersetpoint,
                    logging_sys& logsys)
{
    std::cout << "DFS running with " << numtasks << " tasks\n";

    // gain
    //float kp = 0.05;
    float kp = 0.01;

    std::thread freqthread;
    int controlperiod = 0;

    float* error = new float[numtasks];
    float* rtr = new float[numtasks];
    float* executiontime = new float[numtasks];
    float* responsetime = new float[numtasks];
    float* taskperiod = new float[numtasks];
    float* newtaskperiod = new float[numtasks];
    float* deadlinemiss = new float[numtasks];
    float* upperbound = new float[numtasks];
    float* lowerbound = new float[numtasks];

    float measuredpower = 0.0f;
    float powererror = 0.0f;

    average average;
    auto start = std::chrono::steady_clock::now();
    std::ofstream ctrlLog("logs/controller.txt", std::ios::app);

    std::filesystem::path base_path(path);
    std::vector<std::string> exec_paths(numtasks);
    std::vector<std::string> resp_paths(numtasks);

    for (int i = 0; i < numtasks; ++i) {
        exec_paths[i] = (base_path / ("taskexecutiontime" + std::to_string(i) + ".txt")).string();
        resp_paths[i] = (base_path / ("taskresponsetime" + std::to_string(i) + ".txt")).string();
    }
    #ifdef POWER_INTERRUPT
    bool is_interrupted = false;
    #else
    bool is_interrupted = true;
    #endif    
        
    while (controllerlooping.load(std::memory_order_relaxed))
    {
        if (!is_interrupted && powerinterrup.load()) {
            is_interrupted = true;
            powersetpoint = powersetpoint - 1000;  
        }
        std::this_thread::sleep_for(std::chrono::duration<float>(outerloopduration));

        stopsigma.store(true, std::memory_order_relaxed);
        if (freqthread.joinable()) {
            freqthread.join();
        }

        auto end = std::chrono::steady_clock::now();
        std::cout << "Current time =\t"
                  << std::chrono::duration_cast<std::chrono::seconds>(end - start).count()
                  << "\n";
        std::cout << "Control Period = " << controlperiod << "\n";

        // Gather per-task measurements for logging only
        for (int i = 0; i < numtasks; i++)
        {
            std::vector<float> local_rtr, local_resp, local_per, local_exec;
            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                local_rtr  = std::move(log[i].rtr);
                local_resp = std::move(log[i].response);
                local_per  = std::move(log[i].period);
                local_exec = std::move(log[i].exec);
            }

            rtr[i]           = average.calculateAverage(local_rtr);
            responsetime[i]  = average.calculateAverage(local_resp);
            taskperiod[i]    = average.calculateAverage(local_per);
            executiontime[i] = average.calculateAverage(local_exec);
            deadlinemiss[i]  = calculate_deadline_miss(local_resp, local_per, 0.05f);

            error[i] = t[i].setpoint - rtr[i];

            append_lock(exec_paths[i], "Control Period");
            append_lock(resp_paths[i], "Control Period");
        }

        std::vector<float> local_power;
        {
            local_power = std::move(logsys.power.measuredpower);
        }

        measuredpower = average.calculateAverage(local_power);
        powererror = powersetpoint - measuredpower;

        std::cout << "Measured Power = " << measuredpower << " W\n";
        std::cout << "Power Setpoint = " << powersetpoint << " W\n";
        std::cout << "Power Error    = " << powererror << " W\n";

        float delta_freq = kp * powererror;

        float measured = current_freq.load(std::memory_order_relaxed);
        float next = measured + delta_freq;

        #ifdef Jetson
            //next = std::clamp(next, 306.0f, 1020.0f);
            next = std::clamp(next, 54.0f, 1575.0f);
        #else
            next = std::clamp(next, 210.0f, 2100.0f);
        #endif

        current_freq.store(next, std::memory_order_relaxed);

        std::cout << "Current freq       = " << measured << " MHz\n";
        std::cout << "Delta freq         = " << delta_freq << " MHz\n";
        std::cout << "New freq (command) = " << next << " MHz\n";

        stopsigma.store(false, std::memory_order_relaxed);
        freqthread = std::thread(sigmadelta_freq_step, next);

        double ts = std::chrono::duration<double>(end - start).count();
        std::cout << "time=" << ts << "  control_period=" << controlperiod << "\n";
        ctrlLog  << "time=" << ts << "  control_period=" << controlperiod << "\n";

        std::cout << "task\texec(ms)\tresp(ms)\trtr\tRTR_err\tPcur(ms)\tPnext(ms)\tDeadline miss (%)\n";
        ctrlLog  << "task\texec(ms)\tresp(ms)\trtr\tRTR_err\tPcur(ms)\tPnext(ms)\tDeadline miss (%)\n";

        std::cout << std::fixed << std::setprecision(3);
        ctrlLog  << std::fixed << std::setprecision(3);

        for (int i = 0; i < numtasks; i++)
        {
            float initial = t[i].initial_rate;
            float min_p = initial * 0.90f;
            float max_p = initial * 1.10f;
            upperbound[i] = max_p;
            lowerbound[i] = min_p;

            newtaskperiod[i] = taskperiod[i];

            std::cout << "T" << (i + 1) << "\t"
                      << executiontime[i] << "\t\t"
                      << responsetime[i]  << "\t\t"
                      << rtr[i]           << "\t"
                      << error[i]         << "\t"
                      << taskperiod[i]    << "\t"
                      << newtaskperiod[i] << "\t"
                      << deadlinemiss[i]  << "\n";

            ctrlLog  << "T" << (i + 1) << "\t"
                     << executiontime[i] << "\t"
                     << responsetime[i]  << "\t"
                     << rtr[i]           << "\t"
                     << error[i]         << "\t"
                     << taskperiod[i]    << "\t"
                     << newtaskperiod[i] << "\t"
                     << deadlinemiss[i]  << "\n";

            {
                std::lock_guard<std::mutex> lk(log[i].mtx);
                log[i].filewritexec.push_back(executiontime[i]);
                log[i].filewriteresponse.push_back(responsetime[i]);
                log[i].filewriteperiod.push_back(taskperiod[i]);
                log[i].filewritertr.push_back(rtr[i]);
                log[i].filewritelowperiodbound.push_back(lowerbound[i] * 1000.0f);
                log[i].filewritehighperiodbound.push_back(upperbound[i] * 1000.0f);
                log[i].filewritedeadlinemiss.push_back(deadlinemiss[i]);
            }
        }

        logsys.power.powersetpoints.push_back(powersetpoint);
        logsys.power.powerseterror.push_back(powererror);
        logsys.power.powercontrolperiod.push_back(measuredpower);

        ctrlLog << "Power\t" << measuredpower
                << "\tPerror\t" << powererror
                << "\tDeltaFreq\t" << delta_freq << "\n";

        std::cout << "*****************************************************************\n\n";
        ctrlLog  << "*****************************************************************\n\n";
        ctrlLog.flush();

        controlperiod++;
    }

    stopsigma.store(true, std::memory_order_relaxed);
    if (freqthread.joinable()) {
        freqthread.join();
    }

    delete[] error;
    delete[] rtr;
    delete[] executiontime;
    delete[] responsetime;
    delete[] taskperiod;
    delete[] newtaskperiod;
    delete[] deadlinemiss;
    delete[] upperbound;
    delete[] lowerbound;
}

void compute_LQR_gain_2(float** gain, int numtasks) //this one works for less than 6 tasks
{
    if (numtasks < 1 || numtasks > 6) {
        throw std::runtime_error("compute_lqr_gain_from_identified_B: numtasks must be between 1 and 6.");
    }

    const float base_last_col_full[6] = {
        0.06238100f,
        0.06804800f,
        0.07260400f,
        0.10549000f,
        0.02831200f,
        0.08079800f
    };

    const float base_last_row_full[6] = {
        0.02220753300f,
        0.01107223000f,
        0.02852230300f,
        0.0738135200f,
        0.01356965500f,
        0.01528722400f
    };

    const float base_bottom_right = 0.00116413f;

    const int N = numtasks;
    const int n = N + 1;

    // -------------------------------------------------------------------------
    // A matrix
    // -------------------------------------------------------------------------
    Matrix A = Matrix::Identity(n, n);
    for (int i = 0; i < n; ++i) {
        A(i, i) = 0.95f;
    }

    // -------------------------------------------------------------------------
    // B matrix
    //
    // Top-left block is still placeholder unless you have measured
    // period-vs-response-time slopes.
    // -------------------------------------------------------------------------
    Matrix B = Matrix::Zero(n, n);

    for (int i = 0; i < N; ++i) {
        B(i, i) = 1.0f;   // replace later with measured -dRT/dT
    }

    for (int i = 0; i < N; ++i) {
        B(i, N) = base_last_col_full[i];
    }

    for (int j = 0; j < N; ++j) {
        B(N, j) = 0.25 * base_last_row_full[j];
        //B(N, j) = base_last_row_full[j];
    }

    // error_power = Pset - Pmeasured, so this term should be negative
    B(N, N) = -base_bottom_right;

    //B(0, N) =  0.0193101314007f;
    //B(1, N) =  0.00206031185497f;
    //B(2, N) =  0.00424506534189f;
    B(0, N) =  0.00206031185497f;
    B(1, N) =  0.00424506534189f;
    B(2, N) =  0.0193101314007f;
    B(N, N) = -0.00205847843323f;


    // -------------------------------------------------------------------------
    // Q and R
    // -------------------------------------------------------------------------
    Matrix Q = Matrix::Zero(n, n);
    for (int i = 0; i < N; ++i) {
	//Q(i, i) = 20.0f;
	Q(i, i) = 10.0f;
    }
    //Q(N, N) = 10.0f;
    Q(N, N) = 1.0f;

    Matrix R = Matrix::Zero(n, n);
    for (int i = 0; i < N; ++i) {
        R(i, i) = 1.0f;
    }

    R(N, N) = 10.0f;

    // -------------------------------------------------------------------------
    // Optional scaling to improve conditioning
    //
    // We normalize state and input channels so the Riccati recursion is less
    // sensitive to wildly different magnitudes in B.
    // -------------------------------------------------------------------------
    Matrix Sx = Matrix::Identity(n, n);
    Matrix Su = Matrix::Identity(n, n);

    // State scaling: RT errors ~ ms, power error ~ W
    for (int i = 0; i < N; ++i) {
        Sx(i, i) = 10.0f;   // assume ~10 ms characteristic RT error
    }
    Sx(N, N) = 1.0f;        // assume power error already ~1 W scale

    // Input scaling: period changes ~ ms, freq changes ~ 100 MHz scale
    for (int i = 0; i < N; ++i) {
        Su(i, i) = 1.0f;    // 1 ms period step scale
    }
    Su(N, N) = 100.0f;      // 100 MHz frequency step scale

    Matrix Sx_inv = Sx.inverse();
    Matrix Su_inv = Su.inverse();

    // Scaled system: x = Sx * xs, u = Su * us
    Matrix As = Sx_inv * A * Sx;
    Matrix Bs = Sx_inv * B * Su;

    Matrix Qs = Sx.transpose() * Q * Sx;
    Matrix Rs = Su.transpose() * R * Su;

    // -------------------------------------------------------------------------
    // Finite-horizon backward Riccati recursion
    // -------------------------------------------------------------------------
    const int horizon = 500;
    Matrix P = Qs;
    Matrix K = Matrix::Zero(n, n);

    for (int k = 0; k < horizon; ++k) {
        Matrix M = Rs + Bs.transpose() * P * Bs;

        Eigen::FullPivLU<Matrix> lu(M);
        if (!lu.isInvertible()) {
            throw std::runtime_error("LQR failed: (R + B^T P B) became singular.");
        }

        K = lu.solve(Bs.transpose() * P * As);

        Matrix Pnext = As.transpose() * P * As
                     - As.transpose() * P * Bs * K
                     + Qs;

        // Force symmetry to suppress numerical drift
        P = 0.5f * (Pnext + Pnext.transpose());

        if (!P.allFinite()) {
            throw std::runtime_error("LQR failed: Riccati recursion produced NaN/Inf.");
        }
    }

    // Convert scaled gain back to original coordinates:
    // us = -Ks xs
    // u  = Su us = -Su Ks Sx^{-1} x
    Matrix K_unscaled = Su * K * Sx_inv;

    for (int i = 0; i < n; ++i) {
        for (int j = 0; j < n; ++j) {
            gain[i][j] = K_unscaled(i, j);
        }
    }

    std::cout << "numtasks = " << numtasks << "\n\n";
    std::cout << "A =\n" << A << "\n\n";
    std::cout << "B =\n" << B << "\n\n";
    std::cout << "Scaled LQR gain K =\n" << K_unscaled << "\n\n";
}

int main(int argc,char*argv[])
{
    #ifdef Jetson
    const char* backend_env = std::getenv("JPAP_POWER_BACKEND");
    if (backend_env)
    {
        g_power_backend = normalize_power_backend(std::string(backend_env));
    }
    if (g_power_backend == "thor" || g_power_backend == "tegrastats") {
        try {
            const int initial_power_mw = returnpowerrtx();
            std::cout << "Power backend: " << g_power_backend
                      << " VIN (module + carrier), mW; initial="
                      << initial_power_mw << "\n";
        } catch (const std::exception& e) {
            std::cerr << e.what() << "\n";
            return 1;
        }
    }
    #endif
    signal(SIGHUP, signalHandler);
    std::cout << "Controller PID: " << getpid() << "\n";
    int numtasks= atoi(argv[1]);
    int solution = std::atoi(argv[2]);
    int duration = std::atoi(argv[3]);
    powersetpoint= std::atof(argv[4]);
    string path= argv[5];
    std::cout<<"Set point power = "<<powersetpoint<<endl;
    int expected_argc = 6 + numtasks * 2;
    if (argc < expected_argc) {
        std::cerr << "ERROR: not enough arguments.\n"
                      << "Expected argc >= " << expected_argc << " but got " << argc << "\n";
        return 1;
    }
    key_t key = ftok("shmfile", 65);
    int shmid = shmget(key, 1024, 0666 | IPC_CREAT);
    bool createdshm;
    if(shmid>0){
        sharedData = (SharedData*)shmat(shmid, nullptr, 0);
        createdshm=true;
    }
    else
    {
        shmid = shmget(key, sizeof(SharedData), 0666);
        sharedData = (SharedData*)shmat(shmid, nullptr, 0);
    }
    std::cout<<path<<endl;
   
    
    
    
    
    
    
    //key_t key = ftok("shmfile", 65);
    //int shmid = shmget(key, sizeof(SharedData), 0666);
    //SharedData* sharedData = (SharedData*)shmat(shmid, nullptr, 0);   
    std::cout<<"tasks = "<<numtasks<<endl;
    float** gain = new float*[numtasks];
    float** doublegain = new float*[numtasks+1];
    float** LQRGain = new float*[numtasks+1];

    for (int i = 0; i < numtasks + 1; ++i) {
        LQRGain[i] = new float[numtasks + 1];
    }
    if (solution == 3 || solution == 8) compute_LQR_gain_2(LQRGain, numtasks);
    //compute_LQR_gain(LQRGain, numtasks);
    /*
    
.00000000   0.00000000   0.00000000   0.00000000   0.00000000   0.00000000  -0.06238100
  0.00000000   1.00000000   0.00000000   0.00000000   0.00000000   0.00000000  -0.06804800
  0.00000000   0.00000000   1.00000000   0.00000000   0.00000000   0.00000000  -0.07260400
  0.00000000   0.00000000   0.00000000   1.00000000   0.00000000   0.00000000  -0.10549000
  0.00000000   0.00000000   0.00000000   0.00000000   1.00000000   0.00000000  -0.02831200
  0.00000000   0.00000000   0.00000000   0.00000000   0.00000000   1.00000000  -0.08079800
-22.20753300 -11.07223000 -28.52230300  -7.38135200 -13.56965500 -15.28722400   0.00116413

    */
    
    for (int i = 0; i < numtasks + 1; ++i) {
        doublegain[i] = new float[numtasks + 1];
    }

    // values from your 7x7 example
    // these are used for the LAST COLUMN and LAST ROW
    const float base_last_col[6] = {
        0.06238100f,
        0.06804800f,
        0.07260400f,
        0.10549000f,
        0.02831200f,
        0.08079800f
    };

    const float base_last_row[6] = {
        22.20753300f,
        11.07223000f,
        28.52230300f,
        7.38135200f,
        13.56965500f,
        15.28722400f
    };

    
    const float base_bottom_right = 0.00116413f;

//     for(int i = 0; i < numtasks; ++i) {
//         doublegain[i] = new float[numtasks];
//     }    
    
    
    for (int i = 0; i < numtasks + 1; ++i) {
    for (int j = 0; j < numtasks + 1; ++j) {
        doublegain[i][j] = 0.0f;
    }
    }

    // top-left NxN block = your regular rule
    for (int i = 0; i < numtasks; ++i) {
        for (int j = 0; j < numtasks; ++j) {
            if (i == j) {
                doublegain[i][j] = (1.25f * 1.0f) * 1.0f * 3.0f;
            } else {
                doublegain[i][j] = 0.1f * 2.0f * 1.5f / 1.0f;
            }
        }
    }

    for (int i = 0; i < numtasks; ++i) {
        doublegain[i][numtasks] = base_last_col[i];
    }

    // last row: use posted values
    for (int j = 0; j < numtasks; ++j) {
        doublegain[numtasks][j] = base_last_row[j];
    }

    // bottom-right element
    doublegain[numtasks][numtasks] = base_bottom_right;
    for (int i = 0; i < numtasks + 1; ++i) {
        for (int j = 0; j < numtasks + 1; ++j) {
            doublegain[i][j] = doublegain[i][j] / 10;
        }
    }





    //fc-gpu gain
    for(int i = 0; i < numtasks; ++i) {
        gain[i] = new float[numtasks];
    }    
    //for(int i = 0; i < numtasks; ++i) {
    //    for(int j = 0; j < numtasks; ++j){
    //        if( i==j){
    //        //gain[i][j]=(1.25*1)*1*4;
    //        gain[i][j]=(1.25*1)*1*4*2;
    //        }
    //        else{
    //        //gain[i][j]=1*2*1.5/(1);
    //        gain[i][j]=2*2*1.5/(1);
    //         }
    //    }
    //}
    for(int i = 0; i < numtasks; ++i) {
        for(int j = 0; j < numtasks; ++j){
            if( i==j){
            //gain[i][j]=(1.25*1)*1*4*2;
            gain[i][j]=(1.25*1)*1*4;
            }
            else{
            //gain[i][j]=2*2*1.5/(1);
            gain[i][j]=2*1.5/(1);
             }
        }
    }    
    for(int i = 0; i < numtasks; ++i) {
        for(int j = 0; j < numtasks; ++j){
           std::cout<<gain[i][j]<<"\t";
        }
         std::cout<<endl;
    }
    
    
    //std::atomic<float> current_freq{1200.0f};
    #ifdef Jetson
        std::atomic<float> current_freq{918.0f};
    #else
        std::atomic<float> current_freq{1800.0f};
    #endif
    activate_freq_nvidia_rtx(current_freq);
    logging log(numtasks,solution);
    logging_sys logsys(solution);
    tasks task(numtasks);  
    int arg_index = 6;  
    for (int i = 0; i < numtasks; i++) {
        //task[i].pid          = std::atoi(argv[arg_index++]);
        task[i].initial_rate = std::atof(argv[arg_index++]);
        task[i].setpoint     = std::atof(argv[arg_index++]);
    }
    std::cout<<"Power Set point = \t"<<powersetpoint<<endl;
    for (int i = 0; i < numtasks; i++) {
         std::cout << "Task " << i
          //<< " PID=" << task[i].pid
          << " Rate=" << task[i].initial_rate*1000
          << " Setpoint=" << task[i].setpoint
          << "\n";
    }
    
    std::unordered_map<int, std::string> mappings = {
            {1, "FC_GPU"},
            {2, "FC_GPU+1"},
            {3, "Proposed"},
            {4, "OpenLoop"},
            {5, "Adhoc"},
            {6, "SISO"},
            {8, "TASK_ARRIVAL_LQR"},
        };
    
    std::cout << "Solution = " << (mappings.count(solution) ? mappings[solution] : "UNKNOWN") << "\n";
    
    while (readyCount < numtasks) 
    {
        usleep(10000);
    }
    std::ifstream in("pid.txt");
    if (!in) {
        std::cerr << "Error: cannot open pid.txt\n";
        return 1;
    }
    std::vector<pid_t> pids;
    for (int i = 0; i < numtasks; ++i) {
        pid_t p;
        if (!(in >> p)) {
            std::cerr << "pid.txt has fewer than " << numtasks << " PIDs\n";
            return 1;
        }
        pids.push_back(p);
    }
    for (pid_t p : pids) {
        if (kill(p, SIGHUP) != 0) {
            perror("kill");
        } else {
            std::cout << "Sent SIGHUP to " << p << "\n";
        }
    }

    std::cout << "Begining\n";

    std::cout << "[main] before monitorThread\n";
    std::thread monitorThread(monitor, &log, &logsys, numtasks);
    std::cout << "[main] monitorThread started\n";

    std::cout << "[main] before monitorpowerthread\n";
    std::thread monitorpowerthread(monitorpower);
    std::cout << "[main] monitorpowerthread started\n";

    std::cout << "[main] before monitorfreqthread\n";
    std::thread monitorfreqthread(monitorfreq);
    std::cout << "[main] monitorfreqthread started\n";

    std::thread controllerThread;
    std::thread controllerThread2;

    std::cout << "[main] before 5s sleep\n";
    std::this_thread::sleep_for(std::chrono::seconds(5));
    std::cout << "[main] after 5s sleep\n";

    switch (solution) {
        case 1:
            std::cout << "[main] launching FC_GPU\\n";
            controllerThread = std::thread(
                FC_GPU, path, std::ref(log), std::ref(task), numtasks,
                gain, std::ref(controllerlooping), powersetpoint, std::ref(logsys));
            std::cout << "[main] FC_GPU launched\\n";
            break;

        

        case 2:
            std::cout << "[main] launching proposed(doublegain)\n";
            controllerThread = std::thread(
                proposed, path, std::ref(log), std::ref(task), numtasks,
                doublegain, std::ref(controllerlooping), powersetpoint, std::ref(logsys));
            std::cout << "[main] proposed(doublegain) launched\n";
            break;

        case 3:
            std::cout << "[main] launching proposed(LQRGain)\n";
            controllerThread = std::thread(
                proposed, path, std::ref(log), std::ref(task), numtasks,
                LQRGain, std::ref(controllerlooping), powersetpoint, std::ref(logsys));
            std::cout << "[main] proposed(LQRGain) launched\n";
            break;

        case 7:
            std::cout << "[main] launching DFS\\n";
            controllerThread = std::thread(
                dfs, path, std::ref(log), std::ref(task), numtasks,
                std::ref(controllerlooping), powersetpoint, std::ref(logsys));
            std::cout << "[main] DFS launched\\n";
            break;

        case 8:
            std::cout << "[main] launching TASK_ARRIVAL_LQR using original proposed(LQRGain) path\n";
            controllerThread = std::thread(
                proposed, path, std::ref(log), std::ref(task), numtasks,
                LQRGain, std::ref(controllerlooping), powersetpoint, std::ref(logsys));
            std::cout << "[main] TASK_ARRIVAL_LQR original proposed(LQRGain) launched\n";
            break;

        case 4:
            std::cout << "[main] launching openloop\n";
            controllerThread = std::thread(
                openloop, path, std::ref(log), std::ref(task), numtasks,
                std::ref(controllerlooping), powersetpoint, std::ref(logsys));
            std::cout << "[main] openloop launched\n";
            break;
        }

    // std::cout<<"Begining \n";
    // std::thread monitorThread(monitor, &log, &logsys, numtasks);
    // std::thread monitorpowerthread(monitorpower);
    // std::thread monitorfreqthread(monitorfreq);
    // std::thread controllerThread;
    // std::thread controllerThread2;
    // std::this_thread::sleep_for(std::chrono::seconds(5));
    // switch (solution) {
    //     case 1:
    //         controllerThread = std::thread(FC_GPU, path, std::ref(log), std::ref(task), numtasks, gain,std::ref(controllerlooping),powersetpoint,std::ref(logsys));
    //         break;
    //     case 2:
    //         controllerThread = std::thread(proposed, path, std::ref(log), std::ref(task), numtasks, doublegain,std::ref(controllerlooping),powersetpoint,std::ref(logsys));
    //         break;
    //     case 3:
    //         controllerThread = std::thread(proposed, path, std::ref(log), std::ref(task), numtasks, LQRGain,std::ref(controllerlooping),powersetpoint,std::ref(logsys));
    //         break;
    //     case 4:
    //         controllerThread = std::thread(openloop, std::ref(log), std::ref(task), numtasks, std::ref(controllerlooping),powersetpoint,std::ref(logsys));
    //         break;
    //     case 5:
    //         controllerThread = std::thread(adhoc, std::ref(log), std::ref(task), numtasks, std::ref(controllerlooping),powersetpoint,std::ref(logsys));
    //         break;
    //     case 6:
    //         controllerThread = std::thread(siso, std::ref(log), std::ref(task), numtasks, std::ref(controllerlooping),powersetpoint,std::ref(logsys));
    //         break;
    //     default:
    //         std::cerr << "ERROR: unknown solution id " << solution << "\n";
    //         outerlooprunning.store(false);
    //         controllerlooping.store(false);
    //         if (monitorThread.joinable()) monitorThread.join();
    //         return 1;
    // }
   
    auto start = std::chrono::steady_clock::now();
    while (true) {
        auto now = std::chrono::steady_clock::now();
        std::chrono::duration<double> elapsed = now - start;
        if (10+elapsed.count() >= duration)
            break;

        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    // 1) Stop all controller/monitor loops so joins won't hang
    outerlooprunning.store(false);
    controllerlooping.store(false);
    monitorthread.store(false);
    stopsigma.store(true);
    if (controllerThread.joinable()) controllerThread.join();
    if (controllerThread2.joinable()) controllerThread2.join();
    if (monitorThread.joinable()) monitorThread.join();
    if (monitorpowerthread.joinable()) monitorpowerthread.join();
    if (monitorfreqthread.joinable()) monitorfreqthread.join();


    for (int i = 0; i < numtasks; ++i) {
        delete[] gain[i];
    }
    delete[] gain;
     for (int i = 0; i < numtasks+1; ++i) {
        delete [] doublegain[i];
     }
    delete[] doublegain;
    log.dump_files(path);
    logsys.dump_files(path);
    log.dump_power(path, finalpowervalues);
    log.dump_freq(path, finalfrequencyvalues);
    if (createdshm == true) {
        shmdt(sharedData);
        shmctl(shmid, IPC_RMID, NULL);
    }

    return 0;
}

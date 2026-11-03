#pragma once

#include <cstdint>
#include <optional>
#include <string>

#include "ina260_reader.hpp"
#include "tegrastats_monitor.hpp"
#include "jtop_reader.hpp"

namespace jetson {

struct PowerSample {
    uint64_t host_ts_ns = 0;

    bool has_ina260 = false;
    bool has_tegrastats = false;
    bool has_jtop = false;
    bool valid = false;

    double ina260_power_w = 0.0;
    double ina260_voltage_v = 0.0;
    double ina260_current_a = 0.0;

    double tegrastats_vdd_in_w = 0.0;
    double tegrastats_vdd_cpu_gpu_cv_w = 0.0;
    double tegrastats_vdd_soc_w = 0.0;

    double jtop_total_w = 0.0;
    double jtop_vdd_cpu_gpu_cv_w = 0.0;
    double jtop_vdd_soc_w = 0.0;

    double total_power_w = 0.0;
    std::string selected_source;
};

class JetsonPowerMonitor {
public:
    struct Config {
        bool enable_ina260;
        bool enable_tegrastats;
        bool enable_jtop;

        std::string ina260_dev_path = "/dev/i2c-7";
        int ina260_addr = 0x40;

        int tegrastats_interval_ms;

        std::string jtop_cmd;

        Config()
            : enable_ina260(true),
              enable_tegrastats(true),
              enable_jtop(false),
              ina260_dev_path("/dev/i2c-7"),
              ina260_addr(0x40),
              tegrastats_interval_ms(200),
              jtop_cmd("python3 scripts/jtop_probe.py") {}
    };

    explicit JetsonPowerMonitor(const Config& cfg = Config());
    ~JetsonPowerMonitor();

    bool init();
    void stop();

    PowerSample sample();

private:
    static std::optional<double> parse_mw_string_to_w(const std::string& s);

private:
    Config cfg_;

    bool initialized_ = false;
    bool tegrastats_started_ = false;
    bool jtop_started_ = false;

    Ina260Reader ina260_reader_;
    TegrastatsMonitor tegrastats_monitor_;
    JtopReader jtop_reader_;
};

} // namespace jetson
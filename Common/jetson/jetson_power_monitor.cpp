#include "jetson_power_monitor.hpp"

#include "time_utils.hpp"

#include <string>

namespace jetson {

JetsonPowerMonitor::JetsonPowerMonitor(const Config& cfg)
    : cfg_(cfg),
      ina260_reader_(cfg.ina260_dev_path, cfg.ina260_addr) {}

JetsonPowerMonitor::~JetsonPowerMonitor() {
    stop();
}

bool JetsonPowerMonitor::init() {
    if (initialized_) return true;

    bool any_enabled = false;

    if (cfg_.enable_tegrastats) {
        tegrastats_started_ = tegrastats_monitor_.start(cfg_.tegrastats_interval_ms);
        any_enabled = any_enabled || tegrastats_started_;
    }

    if (cfg_.enable_jtop) {
        jtop_started_ = jtop_reader_.start(cfg_.jtop_cmd);
        any_enabled = any_enabled || jtop_started_;
    }

    if (cfg_.enable_ina260) {
        any_enabled = true;
    }

    initialized_ = true;
    return any_enabled;
}

void JetsonPowerMonitor::stop() {
    if (!initialized_) return;

    if (tegrastats_started_) {
        tegrastats_monitor_.stop();
        tegrastats_started_ = false;
    }

    if (jtop_started_) {
        jtop_reader_.stop();
        jtop_started_ = false;
    }

    initialized_ = false;
}

std::optional<double> JetsonPowerMonitor::parse_mw_string_to_w(const std::string& s) {
    if (s.empty()) return std::nullopt;

    try {
        double mw = std::stod(s);
        return mw / 1000.0;
    } catch (...) {
        return std::nullopt;
    }
}

PowerSample JetsonPowerMonitor::sample() {
    PowerSample out;
    out.host_ts_ns = static_cast<uint64_t>(common::now_ns());

    if (cfg_.enable_ina260) {
        Ina260Sample s = ina260_reader_.read_sample();
        if (s.ok) {
            out.has_ina260 = true;
            out.ina260_current_a = s.current_a;
            out.ina260_voltage_v = s.voltage_v;
            out.ina260_power_w = s.power_w;
        }
    }

    if (cfg_.enable_tegrastats && tegrastats_started_) {
        TegrastatsPower p = tegrastats_monitor_.latest();

        if (p.vdd_in_mw > 0 || p.vdd_cpu_gpu_cv_mw > 0 || p.vdd_soc_mw > 0) {
            out.has_tegrastats = true;
            out.tegrastats_vdd_in_w = static_cast<double>(p.vdd_in_mw) / 1000.0;
            out.tegrastats_vdd_cpu_gpu_cv_w = static_cast<double>(p.vdd_cpu_gpu_cv_mw) / 1000.0;
            out.tegrastats_vdd_soc_w = static_cast<double>(p.vdd_soc_mw) / 1000.0;
        }
    }

    if (cfg_.enable_jtop && jtop_started_) {
        JtopSample s = jtop_reader_.latest();
        if (s.valid) {
            bool got_any = false;

            if (auto v = parse_mw_string_to_w(s.power_tot_mw)) {
                out.jtop_total_w = *v;
                got_any = true;
            }
            if (auto v = parse_mw_string_to_w(s.power_vdd_cpu_gpu_cv_mw)) {
                out.jtop_vdd_cpu_gpu_cv_w = *v;
                got_any = true;
            }
            if (auto v = parse_mw_string_to_w(s.power_vdd_soc_mw)) {
                out.jtop_vdd_soc_w = *v;
                got_any = true;
            }

            out.has_jtop = got_any;
        }
    }

    if (out.has_ina260) {
        out.total_power_w = out.ina260_power_w;
        out.selected_source = "ina260";
        out.valid = true;
    } else if (out.has_tegrastats && out.tegrastats_vdd_in_w > 0.0) {
        out.total_power_w = out.tegrastats_vdd_in_w;
        out.selected_source = "tegrastats_vdd_in";
        out.valid = true;
    } else if (out.has_jtop && out.jtop_total_w > 0.0) {
        out.total_power_w = out.jtop_total_w;
        out.selected_source = "jtop_total";
        out.valid = true;
    }

    return out;
}

} // namespace jetson
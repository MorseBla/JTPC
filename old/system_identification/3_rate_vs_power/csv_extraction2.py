import os
import json
import csv

BASE_DIR = "logs"
OUTPUT_FILE = "power_vs_rt.csv"


def main():
    rows = []

    for workload in os.listdir(BASE_DIR):

        workload_path = os.path.join(BASE_DIR, workload)

        if not os.path.isdir(workload_path):
            continue

        for fname in os.listdir(workload_path):

            if not fname.endswith(".json"):
                continue

            full_path = os.path.join(workload_path, fname)

            try:
                with open(full_path, "r") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"Skipping {full_path}: {e}")
                continue

            rt = data.get("avg_response_ms")
            power = data.get("avg_power_w")
            period = data.get("period_s")
            freq = data.get("avg_measured_freq_mhz")

            if rt is None or power is None:
                continue

            rows.append({
                "workload": workload,
                "period_s": float(period) if period is not None else -1,
                "freq_mhz": float(freq) if freq is not None else -1,
                "response_ms": float(rt),
                "power_w": float(power),
            })

    rows.sort(
        key=lambda x: (
            x["workload"],
            x["response_ms"]
        )
    )

    with open(OUTPUT_FILE, "w", newline="") as csvfile:

        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                "workload",
                "period_s",
                "freq_mhz",
                "response_ms",
                "power_w",
            ]
        )

        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

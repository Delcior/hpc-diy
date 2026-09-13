#!/usr/bin/env python3
"""Convert continuous tegrastats output into Prometheus textfile metrics.

The output path is configured through PROM_OUTPUT.
"""

from __future__ import print_function

import os
import re
import signal
import subprocess
import sys
import tempfile
import time


RAM_RE = re.compile(r"\bRAM\s+(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)MB\b")
SWAP_RE = re.compile(r"\bSWAP\s+(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)MB\b")
CPU_RE = re.compile(r"\bCPU\s+\[([^]]+)\]")
CPU_VALUE_RE = re.compile(r"(\d+(?:\.\d+)?)%@([0-9]+)")
GPU_RE = re.compile(r"\b(GR3D(?:\d*)_FREQ)\s+(\d+(?:\.\d+)?)%@([0-9]+)")
EMC_RE = re.compile(r"\bEMC_FREQ\s+(\d+(?:\.\d+)?)%@([0-9]+)")
TEMP_RE = re.compile(
    r"\b(CPU|GPU|AO|Tboard|PMIC|PLL)(?:-therm)?@"
    r"(\d+(?:\.\d+)?)C\b"
)
POWER_RE = re.compile(
    r"\b(VDD_IN|VDD_CPU|VDD_GPU|POM_5V_IN|POM_5V_GPU|POM_5V_CPU)\s+"
    r"(\d+(?:\.\d+)?)(?:/(?:\d+(?:\.\d+)?))?"
)


def metric(name, help_text, metric_type, value, labels=None):
    """Render one Prometheus metric and its metadata."""
    lines = ["# HELP {0} {1}".format(name, help_text),
             "# TYPE {0} {1}".format(name, metric_type)]
    label_text = ""
    if labels:
        label_text = "{" + ",".join(
            '{0}="{1}"'.format(key, str(value).replace('\\', '\\\\').replace('"', '\\"'))
            for key, value in labels.items()
        ) + "}"
    lines.append("{0}{1} {2}".format(name, label_text, value))
    return lines


def deduplicate_metadata(lines):
    """Keep one HELP and TYPE line for each metric family."""
    seen = set()
    result = []
    for line in lines:
        if line.startswith("# HELP ") or line.startswith("# TYPE "):
            key = line.split(" ", 3)[0:3]
            key = " ".join(key)
            if key in seen:
                continue
            seen.add(key)
        result.append(line)
    return result


def parse(line):
    """Return Prometheus metric lines parsed from one tegrastats line."""
    output = []

    match = RAM_RE.search(line)
    if match:
        output.extend(metric(
            "jetson_ram_used_bytes", "Used RAM", "gauge",
            float(match.group(1)) * 1024 * 1024))
        output.extend(metric(
            "jetson_ram_total_bytes", "Total RAM", "gauge",
            float(match.group(2)) * 1024 * 1024))

    match = SWAP_RE.search(line)
    if match:
        output.extend(metric(
            "jetson_swap_used_bytes", "Used swap", "gauge",
            float(match.group(1)) * 1024 * 1024))
        output.extend(metric(
            "jetson_swap_total_bytes", "Total swap", "gauge",
            float(match.group(2)) * 1024 * 1024))

    match = CPU_RE.search(line)
    if match:
        for index, cpu_match in enumerate(CPU_VALUE_RE.finditer(match.group(1))):
            output.extend(metric(
                "jetson_cpu_utilization_percent", "CPU utilization", "gauge",
                cpu_match.group(1), {"cpu": index}))
            output.extend(metric(
                "jetson_cpu_clock_hertz", "CPU clock frequency", "gauge",
                float(cpu_match.group(2)) * 1000000, {"cpu": index}))

    for match in GPU_RE.finditer(line):
        engine = match.group(1).replace("_FREQ", "").lower()
        output.extend(metric(
            "jetson_gpu_utilization_percent", "GPU engine utilization", "gauge",
            match.group(2), {"engine": engine}))
        output.extend(metric(
            "jetson_gpu_clock_hertz", "GPU engine clock frequency", "gauge",
            float(match.group(3)) * 1000000, {"engine": engine}))

    match = EMC_RE.search(line)
    if match:
        output.extend(metric(
            "jetson_emc_utilization_percent", "EMC utilization", "gauge",
            match.group(1)))
        output.extend(metric(
            "jetson_emc_clock_hertz", "EMC clock frequency", "gauge",
            float(match.group(2)) * 1000000))

    for match in TEMP_RE.finditer(line):
        output.extend(metric(
            "jetson_temperature_celsius", "Jetson thermal zone temperature", "gauge",
            match.group(2), {"sensor": match.group(1).lower()}))

    for match in POWER_RE.finditer(line):
        output.extend(metric(
            "jetson_power_watts", "Jetson power draw", "gauge",
            float(match.group(2)) / 1000, {"rail": match.group(1)}))

    return deduplicate_metadata(output)


def fail(message):
    print("tegrastats_to_prom: {0}".format(message), file=sys.stderr)
    return 1


def write_payload(output_path, lines):
    """Atomically replace the Prometheus textfile collector output."""
    payload = "\n".join(lines) + "\n"
    output_dir = os.path.dirname(os.path.abspath(output_path))
    temporary_path = None
    try:
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".tegrastats.", suffix=".prom", dir=output_dir, text=True)
        with os.fdopen(descriptor, "w") as output_file:
            output_file.write(payload)
            output_file.flush()
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, output_path)
    except (IOError, OSError) as error:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise IOError("cannot write {0}: {1}".format(output_path, error))


def main():
    output_path = os.environ.get("PROM_OUTPUT")
    if not output_path:
        return fail("PROM_OUTPUT is not set")

    output_dir = os.path.dirname(os.path.abspath(output_path))
    if not os.path.isdir(output_dir):
        return fail("output directory does not exist: {0}".format(output_dir))

    process = None
    stopping = [False]

    def handle_signal(signum, frame):
        del signum, frame
        stopping[0] = True
        if process and process.poll() is None:
            process.terminate()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        process = subprocess.Popen(
            ["tegrastats", "--interval", "500"],
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            universal_newlines=True,
            bufsize=1,
        )

        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            lines = parse(line)
            lines.extend(metric(
                "jetson_tegrastats_sample_timestamp_seconds",
                "Unix timestamp of the tegrastats sample", "gauge", time.time()))
            write_payload(output_path, lines)

        return_code = process.wait()
        if return_code != 0:
            if stopping[0]:
                return 0
            return fail("tegrastats exited with status {0}".format(return_code))
    except (IOError, OSError) as error:
        return fail(str(error))
    except KeyboardInterrupt:
        if process and process.poll() is None:
            process.terminate()
        if process:
            process.wait()
    finally:
        if process and process.poll() is None:
            process.terminate()
            process.wait()

    return 0


if __name__ == "__main__":
    sys.exit(main())

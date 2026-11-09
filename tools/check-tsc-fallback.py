#!/usr/bin/env python3
"""Validate the generated TSC selector against a deterministic CPUID fixture."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cache = Path((root / '.local/headless-cache').read_text().strip())
source = (cache / 'source/src/common/cpu_features.cpp').read_text()
derived = (cache / 'native-local/headless/cpu_features.cpp').read_text()

# Reproduce the build's deliberate TSC fallback transformation and require the
# generated translation unit to match it exactly. This prevents a weakened
# source-pattern test from silently accepting different production logic.
amd_fallback = (
    "    // AMD CPUs have no leaf 0x15 (Zen 4 stops at 0x10): measure their invariant TSC too, or every\n"
    "    // guest clock read (CNTPCT, which games read thousands of times a frame) goes through the\n"
    "    // host's much slower QueryPerformanceCounter.\n"
    "    if (caps.invariant_tsc && caps.tsc_frequency == 0) {\n"
    "        caps.tsc_frequency = X64::EstimateRDTSCFrequency();\n    }\n\n"
)
expected = source.replace(amd_fallback, '').replace(
    "        } else {\n            caps.tsc_frequency = X64::EstimateRDTSCFrequency();\n        }",
    "        }"
).replace(
    "    if (max_std_fn >= 0x16) {",
    "    if (caps.invariant_tsc && caps.tsc_frequency < 1'000'000'000ULL) {\n"
    "        caps.tsc_frequency = X64::EstimateRDTSCFrequency();\n    }\n\n"
    "    if (max_std_fn >= 0x16) {"
)
assert derived == expected, "Generated CPU feature source differs from the expected TSC fallback transformation"

selection_start = derived.index("    if (max_std_fn >= 0x15) {")
selection_end = derived.index("    if (caps.invariant_tsc && caps.tsc_frequency < 1'000'000'000ULL)", selection_start)
selection = derived[selection_start:selection_end]
fallback_start = selection_end
fallback_end = derived.index("\n    if (max_std_fn >= 0x16)", fallback_start)
fallback = derived[fallback_start:fallback_end]

code = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
using u64 = uint64_t;
static unsigned estimates;
static u64 estimated;
static int leaf15[4];
static void mock_cpuid(int* info, unsigned leaf) {
    std::memset(info, 0, sizeof(int) * 4);
    if (leaf == 0x15) std::memcpy(info, leaf15, sizeof(leaf15));
}
#define __cpuid(info, leaf) mock_cpuid((info), (leaf))
namespace X64 { u64 EstimateRDTSCFrequency() { ++estimates; return estimated; } }

u64 select(unsigned max_std_fn, bool invariant, int denominator, int numerator, int crystal) {
    int cpu_id[4]{};
    leaf15[0] = denominator; leaf15[1] = numerator; leaf15[2] = crystal; leaf15[3] = 0;
    struct { bool invariant_tsc; u64 tsc_frequency = 0, tsc_crystal_ratio_denominator = 0,
        tsc_crystal_ratio_numerator = 0, crystal_frequency = 0; } caps{invariant};
''' + selection + r'''
''' + fallback + r'''
    return caps.tsc_frequency;
}
int main() {
    estimated = 2'200'000'000ULL;
    assert(select(0x10, true, 0, 0, 0) == estimated && estimates == 1);
    assert(select(0x15, true, 2, 4, 0) == estimated && estimates == 2);
    assert(select(0x15, true, 0, 0, 0) == estimated && estimates == 3);
    assert(select(0x15, true, 1, 100, 24'000'000) == 2'400'000'000ULL && estimates == 3);
    assert(select(0x15, false, 1, 100, 24'000'000) == 2'400'000'000ULL && estimates == 3);
    estimated = 500'000'000ULL;
    assert(select(0x15, true, 1, 100, 0) == estimated && estimates == 4);
}
'''
with tempfile.TemporaryDirectory(prefix="eden-tsc-") as directory:
    path = Path(directory)
    (path / "check.cpp").write_text(code)
    subprocess.run(["clang++-18", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True, timeout=5)
print("TSC generated-source equivalence and CPUID-driven selection: missing leaf, invalid ratio, valid ratio, invariant gating and low-frequency fallback PASS")

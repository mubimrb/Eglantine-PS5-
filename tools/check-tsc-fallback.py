#!/usr/bin/env python3
"""Validate the generated TSC CPUID selection and low-frequency fallback."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cache = Path((root / '.local/headless-cache').read_text().strip())
derived = (cache / 'native-local/headless/cpu_features.cpp').read_text()

fallback_start = derived.index('    if (caps.invariant_tsc && caps.tsc_frequency < 1\'000\'000\'000ULL)')
fallback_end = derived.index('\n    if (max_std_fn >= 0x16)', fallback_start)
fallback = derived[fallback_start:fallback_end]
assert 'X64::EstimateRDTSCFrequency()' in fallback
assert 'if (max_std_fn >= 0x15)' in derived
assert 'caps.tsc_crystal_ratio_denominator' in derived
assert 'caps.tsc_crystal_ratio_numerator' in derived
assert 'caps.crystal_frequency' in derived
selection_start = derived.index('    if (max_std_fn >= 0x15) {')
selection_end = derived.index('    if (max_std_fn >= 0x16) {')
selection = derived[selection_start:selection_end]

code = '''
#include <cassert>
#include <cstdint>
using u64 = uint64_t;
// The extracted source uses the platform CPUID helper. The fixture preloads
// cpu_id with the requested leaf values, so model the helper as a no-op.
#define __cpuid(info, leaf) ((void)(info), (void)(leaf))
static unsigned estimates;
static u64 estimated;
namespace X64 { u64 EstimateRDTSCFrequency() { ++estimates; return estimated; } }
u64 select(unsigned max_std_fn, int denominator, int numerator, int crystal) {
    int cpu_id[]{denominator, numerator, crystal, 0};
    struct { bool invariant_tsc = false; u64 tsc_frequency = 0, tsc_crystal_ratio_denominator = 0,
        tsc_crystal_ratio_numerator = 0, crystal_frequency = 0; } caps;
''' + selection + '''
    return caps.tsc_frequency;
}
u64 low_frequency_fallback(bool invariant, u64 frequency) {
    struct { bool invariant_tsc; u64 tsc_frequency; } caps{invariant, frequency};
''' + fallback + '''
    return caps.tsc_frequency;
}
int main() {
    estimated = 2'200'000'000;
    assert(select(0x10, 0, 0, 0) == 0 && estimates == 0);
    assert(select(0x15, 2, 4, 0) == estimated && estimates == 1);
    assert(select(0x15, 0, 0, 0) == estimated && estimates == 2);
    assert(select(0x15, 1, 100, 24'000'000) == 2'400'000'000 && estimates == 2);
    assert(low_frequency_fallback(false, 0) == 0 && estimates == 2);
    assert(low_frequency_fallback(true, 1'200'000'000) == 1'200'000'000 && estimates == 2);
    assert(low_frequency_fallback(true, 0) == estimated && estimates == 3);
    estimated = 500'000'000;
    assert(low_frequency_fallback(true, 500'000'000) == estimated && estimates == 4);
}
'''
with tempfile.TemporaryDirectory(prefix='eden-tsc-') as directory:
    path = Path(directory)
    (path / 'check.cpp').write_text(code)
    subprocess.run(['clang++-18', '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
                    str(path / 'check.cpp'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True, timeout=5)
print('TSC CPUID selection and low-frequency fallback: missing leaf, valid/invalid ratios, invariant gating and estimator results PASS')

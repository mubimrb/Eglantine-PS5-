// SPDX-License-Identifier: GPL-3.0-or-later
// The standalone mapping tests exercise rejected requests without starting the
// application's asynchronous logger. Keep those diagnostics visible on stderr.
#define FMT_HEADER_ONLY
#include <cstdio>
#include "common/logging.h"
#include "common/settings.h"

namespace Common::Log {
void FmtLogMessageImpl(Class, Level, const char*, unsigned int, const char*,
                       fmt::string_view format, const fmt::format_args& args) {
    fmt::vprint(stderr, format, args);
    std::fputc('\n', stderr);
}
} // namespace Common::Log

// Shader-lowering tests reference the current program ID through logging and
// diagnostics. The host-only target has no application/session lifecycle, so
// provide the neutral default used by an unloaded program.
namespace Settings {
u64 GetCurrentProgramID() {
    return 0;
}
} // namespace Settings

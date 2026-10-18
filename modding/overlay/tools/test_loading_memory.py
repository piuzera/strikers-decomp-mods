"""Host regression harness for the production virtual-read loops and RAM profile.

Compiles the actual synchronous read implementations with a bounded allocator
and file-I/O stubs. Does not start Dolphin or send controller inputs.
"""

import configparser
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import palmeiras_team as team


def production_function(source, signature):
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for offset in range(brace, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start:offset + 1]
    raise AssertionError(f"Unterminated production function: {signature}")


class LoadingMemoryTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"), "Requires a host C++ compiler")
    def test_production_read_loops_preserve_bytes_with_recorded_memory_limit(self):
        source = (team.ROOT / "src/NL/nlFileGC.cpp").read_text()
        functions = "\n".join(production_function(source, signature) for signature in (
            "void* nlReadToVirtualMemory(", "static inline void* nlReadToVirtualMemoryInline("))
        harness = r'''
#include "NL/StreamingBuffer.h"
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>
typedef unsigned char u8;
struct nlFile { std::vector<u8> bytes; unsigned int position; };
static unsigned int allocations = 0, releases = 0, largestRequest = 0;
static const unsigned int recordedLargestFreeBlock = 452732;
void check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
void* nlMalloc(unsigned int size, unsigned int alignment, bool atEnd) {
    check(size <= recordedLargestFreeBlock, "reproduced the logged allocation failure");
    check(size <= 0x10000 && size % 32 == 0 && alignment == 32, "unbounded or unaligned transfer buffer");
    check(!atEnd, "unexpected allocation direction");
    ++allocations; largestRequest = std::max(largestRequest, size);
    void* p = std::malloc(size); check(p != NULL, "host allocation failed"); return p;
}
void nlFree(void* p) { ++releases; std::free(p); }
void nlRead(nlFile* f, void* dst, unsigned int count) {
    check(f->position + count <= f->bytes.size(), "read beyond file boundary");
    std::memcpy(dst, f->bytes.data() + f->position, count); f->position += count;
}
'''
        harness += "\n" + functions + r'''
typedef void* (*Reader)(nlFile*, void*, unsigned int, unsigned int);
void exercise(Reader read, const std::vector<u8>& input, unsigned int hint) {
    nlFile f = {input, 0};
    std::vector<u8> dest(input.size() + 64, 0xA5);
    unsigned int before = allocations;
    check(read(&f, dest.data() + 32, input.size(), hint) == dest.data() + 32, "wrong target pointer");
    check(f.position == input.size(), "file was truncated");
    check(std::equal(input.begin(), input.end(), dest.begin() + 32), "file bytes changed");
    for (unsigned int i = 0; i < 32; ++i) {
        check(dest[i] == 0xA5 && dest[dest.size() - 1 - i] == 0xA5, "target buffer overrun");
    }
    check(allocations - before == (input.empty() ? 0u : 1u), "unexpected scratch allocations");
    check(allocations == releases, "scratch buffer leaked");
}
int main(int argc, char** argv) {
    try {
        check(nlVirtualReadChunkSize(0x80000, 0) == 0, "empty file policy");
        check(nlVirtualReadChunkSize(0x80000, 472241) == 0x10000, "large model policy");
        check(nlVirtualReadChunkSize(0x80000, 33) == 64, "small file alignment");
        check(nlVirtualReadChunkSize(0, 100000) == 0x10000, "zero hint must make progress");
        unsigned int sizes[] = {0, 1, 31, 32, 33, 16383, 16384, 65535, 65536, 65537, 472241, 524288, 1048577};
        unsigned int hints[] = {0, 1, 32, 0x4000, 0x80000};
        Reader readers[] = {nlReadToVirtualMemory, nlReadToVirtualMemoryInline};
        for (Reader reader : readers) {
            for (unsigned int size : sizes) {
                std::vector<u8> bytes(size);
                for (unsigned int i = 0; i < size; ++i) bytes[i] = (i * 71 + i / 256) & 255;
                for (unsigned int hint : hints) exercise(reader, bytes, hint);
            }
            if (argc > 1) {
                std::ifstream file(argv[1], std::ios::binary);
                check(file.good(), "retail Hammer Bros model missing");
                std::vector<u8> bytes((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
                exercise(reader, bytes, 0x80000);
            }
        }
        check(largestRequest == 65536, "unexpected peak scratch allocation");
        std::cout << "Production read loops preserve all bytes; peak scratch=65536, recorded available=452732\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
'''
        with tempfile.TemporaryDirectory(prefix="strikers-memory-") as directory:
            cpp = Path(directory) / "memory_test.cpp"
            binary = Path(directory) / "memory_test"
            cpp.write_text(harness)
            compile_result = subprocess.run(["c++", "-std=c++17", "-O2", "-I", str(team.ROOT / "include"),
                                             str(cpp), "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            command = [str(binary)]
            model = team.FILES / "art/characters/HammerBro/HammerBro.glg"
            if model.exists():
                command.append(str(model))
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("peak scratch=65536", result.stdout)

    def test_profile_enables_required_memory_without_touching_controllers(self):
        with tempfile.TemporaryDirectory(prefix="strikers-profile-") as directory:
            profile = Path(directory)
            config = profile / "Config"
            config.mkdir()
            (config / "Dolphin.ini").write_text("[Core]\nCPUThread = True\n[Interface]\nThemeName = UserTheme\n")
            controller = config / "GCPadNew.ini"
            binding = b"[GCPad1]\nDevice = User controller\nButtons/A = User A\n"
            controller.write_bytes(binding)
            team.configure_runtime_profile(profile)
            parser = configparser.ConfigParser()
            parser.read(config / "Dolphin.ini")
            self.assertTrue(parser.getboolean("Core", "RAMOverrideEnable"))
            self.assertEqual(parser.getint("Core", "MEM1Size"), 48 * 1024 * 1024)
            self.assertTrue(parser.getboolean("Core", "CPUThread"))
            self.assertEqual(parser.get("Interface", "ThemeName"), "UserTheme")
            self.assertEqual(controller.read_bytes(), binding)

    def test_launch_arguments_cannot_silently_use_retail_24_mib(self):
        from unittest import mock
        with mock.patch.object(team, "dolphin", return_value="dolphin-emu"):
            args = team.launch_arguments(team.DISC / "sys/main.dol")
        self.assertIn("Dolphin.Core.RAMOverrideEnable=True", args)
        self.assertIn("Dolphin.Core.MEM1Size=50331648", args)
        self.assertIn(str(team.USER_PROFILE), args)
        self.assertNotIn(str(team.MOD_BUILD / "dolphin-qa"), args)


if __name__ == "__main__":
    unittest.main()

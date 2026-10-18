"""Exercise production GLX pool initialization/allocation with host boundaries.

No GPU, Dolphin or game launch. Native addresses are modeled as 32-bit numbers;
the harness never dereferences them.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from palmeiras_team import ROOT
from test_loading_memory import production_function


class GraphicsMemoryTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++"), "Requires host C++ compiler")
    def test_production_resource_budget_bounds_and_replay_headroom(self):
        source = (ROOT / "src/NL/glx/glxMemory.cpp").read_text()
        functions = "\n".join(production_function(source, name) for name in (
            "bool glxInitMemory()", "void* glplatResourceAlloc(", "u32 glx_GetFreeMemory()"))
        replay_source = (ROOT / "src/Game/ReplayManager.cpp").read_text()
        replay = production_function(replay_source, "static unsigned int ChooseReplayMemorySize()")
        harness = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
typedef uint32_t u32;
#define KB(x) ((x) * 1024u)
#define MB(x) KB(KB(x))
#define NULL 0
enum eGLMemory { GLM_Header, GLM_Matrix, GLM_IndexData, GLM_VertexData, GLM_TextureData, GLM_Target, GLM_Num };
struct GLXMemoryInfo { u32 m_uBytes[GLM_Num]; };
static GLXMemoryInfo g_uResourceAlloc[16];
static int g_uResourceMarker, i_frame;
static u32 ResourceMemSize, FrameMemSizeReal, FrameMemSizeVirt, p_phys, n_phys;
static u32 p_frame[2][2], n_frame[2][2], g_frameHighWater[2], FrameMemSizes[2];
static const char* szMemoryNames[] = {"header", "matrix", "index", "vert", "tex", "target"};
static u32 physicalMemory, nextAddress;
static bool developer, throwOnBreak;
static int breaks;
static std::vector<u32> mainAllocations, virtualAllocations;
static std::map<std::string, u32> configuration;
struct Config { static Config& Global() { static Config c; return c; } };
bool GetConfigBool(Config&, const char*, bool) { return developer; }
u32 GetFromConfig(const char* key, u32 fallback) {
    return configuration.count(key) ? configuration[key] : fallback;
}
u32 OSGetPhysicalMemSize() { return physicalMemory; }
u32 nlMalloc(u32 bytes, u32 alignment, bool) {
    assert(alignment == 32 && bytes % 32 == 0);
    mainAllocations.push_back(bytes);
    u32 result = nextAddress; nextAddress += bytes; return result;
}
u32 nlVirtualAlloc(u32 bytes, bool) { virtualAllocations.push_back(bytes); return 0x40000000; }
void OSReport(const char*, ...) {}
void nlBreak() { ++breaks; if (throwOnBreak) throw std::runtime_error("pool exhausted"); }
struct Allocator { u32 largest; u32 LargestFreeBlock() { return largest; } } StandardAllocator;
static const u32 ExpandedReplayMemorySize = MB(8);
void reset(u32 ram) {
    physicalMemory = ram; ResourceMemSize = MB(12) - KB(12);
    FrameMemSizeReal = KB(896); FrameMemSizeVirt = KB(640);
    nextAddress = 0x80000000; developer = false; breaks = 0; throwOnBreak = true;
    configuration.clear(); mainAllocations.clear(); virtualAllocations.clear();
    for (int i = 0; i < 16; ++i) g_uResourceAlloc[i] = GLXMemoryInfo();
    g_uResourceMarker = 0;
}
''' + functions + replay + r'''
int main() {
    const u32 retailPool = MB(12) - KB(12);
    reset(MB(24));
    configuration["resource total memory"] = retailPool;
    assert(glxInitMemory());
    assert(ResourceMemSize == retailPool && FrameMemSizeReal == KB(896) && FrameMemSizeVirt == KB(640));
    assert(mainAllocations.size() == 2 && virtualAllocations.size() == 1);

    // Reproduce the limit: a nearly full retail pool cannot fit another model.
    glplatResourceAlloc(retailPool - 32, GLM_TextureData);
    u32 used = n_phys, tracked = g_uResourceAlloc[0].m_uBytes[GLM_TextureData];
    try { glplatResourceAlloc(MB(1), GLM_TextureData); assert(false); }
    catch (const std::runtime_error&) {}
    assert(breaks == 1 && n_phys == used && glx_GetFreeMemory() == 32);
    assert(g_uResourceAlloc[0].m_uBytes[GLM_TextureData] == tracked);
    // Even if a user dismisses nlBreak, no out-of-pool pointer may escape.
    throwOnBreak = false;
    assert(glplatResourceAlloc(MB(1), GLM_Header) == NULL);
    assert(n_phys == used && g_uResourceAlloc[0].m_uBytes[GLM_Header] == 0);

    reset(MB(48));
    configuration["resource total memory"] = retailPool;
    configuration["frame vertex memory"] = KB(896);
    configuration["frame header memory"] = KB(640);
    assert(glxInitMemory());
    assert(ResourceMemSize == MB(16) && FrameMemSizeReal == MB(4) && FrameMemSizeVirt == MB(2));
    assert(mainAllocations.size() == 3 && virtualAllocations.empty());
    assert(mainAllocations[0] == MB(16) && mainAllocations[1] == MB(8) && mainAllocations[2] == MB(4));
    // Previously resident assets plus independent Human and late textures.
    glplatResourceAlloc(retailPool - 32, GLM_TextureData);
    u32 marker = n_phys;
    glplatResourceAlloc(MB(1), GLM_VertexData);
    glplatResourceAlloc(MB(1), GLM_TextureData);
    assert(breaks == 0 && glx_GetFreeMemory() > MB(2));
    assert(g_uResourceAlloc[0].m_uBytes[GLM_TextureData] == retailPool - 32 + MB(1));
    // Same bump-pointer marker/release contract used between matches.
    n_phys = marker;
    assert(glx_GetFreeMemory() == MB(16) - marker);
    n_phys = 0;
    void* start = glplatResourceAlloc(1, GLM_Header);
    void* next = glplatResourceAlloc(31, GLM_Header);
    assert((uintptr_t)next == (uintptr_t)start + 32 && n_phys == 63);
    glplatResourceAlloc(ResourceMemSize - 64, GLM_VertexData);
    assert(n_phys == ResourceMemSize && glx_GetFreeMemory() == 0);
    throwOnBreak = false;
    assert(glplatResourceAlloc(0xffffffffUL, GLM_TextureData) == NULL);
    assert(n_phys == ResourceMemSize);

    // Configurations already larger than the minimum are preserved, also E3.
    reset(MB(48)); configuration["resource total memory"] = MB(20);
    assert(glxInitMemory() && ResourceMemSize == MB(20));
    reset(MB(48)); developer = true; configuration["e3 resource total memory"] = MB(18);
    assert(glxInitMemory() && ResourceMemSize == MB(18));

    // Recorded failed-run general heap figures, adjusted for the pool growth.
    u32 growth = MB(16) - retailPool;
    StandardAllocator.largest = 16833712 - growth;
    assert(ChooseReplayMemorySize() == MB(8));
    assert(6232824 - growth > MB(1));
}
'''
        with tempfile.TemporaryDirectory(prefix="strikers-glx-") as directory:
            cpp, binary = Path(directory) / "glx.cpp", Path(directory) / "glx"
            cpp.write_text(harness)
            result = subprocess.run(["c++", "-std=c++11", str(cpp), "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

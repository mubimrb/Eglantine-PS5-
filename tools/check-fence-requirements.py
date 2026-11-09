#!/usr/bin/env python3
"""Exercise the pinned Eglantine fence commit/signal code with mock caches."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'Eglantine/src/video_core/fence_manager.h').read_text()


def body(text, signature):
    start = text.index(signature)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


code = r'''
#include <cassert>
#include <condition_variable>
#include <functional>
#include <memory>
#include <mutex>
#include <queue>
#include <utility>
#include <vector>
using u8=unsigned char;
namespace Settings {
inline bool delayed{};
bool IsGPUFenceBehaviorDefault(){return false;}
bool IsGPULevelHigh(){return false;}
bool IsGPUFenceBehaviorBalanced(){return delayed;}
bool IsGPUFenceBehaviorAccurate(){return false;}
}
namespace VideoCommon {
namespace Nx2Profile {enum class Zone{Fence,FenceSkipped};struct Scope{Scope(Zone){}};}
struct Cache {
 std::mutex mutex;bool pending{},side_work{};unsigned checks{},commits{};
 bool HasUncommittedFlushes(){++checks;return pending;}
 bool HasAsyncFlushWork(){return pending||side_work;}
 void CommitAsyncFlushes(){++commits;pending=false;}
};
struct Raster {unsigned invalidates{},flushes{};void InvalidateGPUCache(){++invalidates;}void FlushCommands(){++flushes;}};
struct TestFence {bool stubbed;};
struct Manager {
 using TFence=std::shared_ptr<TestFence>;
 static constexpr bool can_async_check=false;
 static constexpr u8 TextureFlushes=1,BufferFlushes=2;
 Cache texture_cache,buffer_cache,query_cache;Raster rasterizer;
 std::mutex guard,uncommitted_guard;std::condition_variable cv;
 unsigned skipped_fences{},queued{};bool skip{};
 std::vector<std::function<void()>> uncommitted_operations;
 std::vector<std::vector<std::function<void()>>> pending_operations;
 std::vector<u8> pending_flushes;std::queue<TFence> fences;
 template<bool>void TryReleasePendingFences(){}
 bool SkipEmptyFence(){return skip;}
 TFence CreateFence(bool stubbed){return std::make_shared<TestFence>(TestFence{stubbed});}
 void QueueFence(TFence&){++queued;}
 struct CacheFlushes{bool should_flush;u8 committed;};
'''
code += body(source, 'CacheFlushes CommitCacheFlushes()') + '\n'
code += body(source, 'void SignalFence(std::function<void()>&& func)') + '\n};\n}\n'
code += r'''
int main(){
 using namespace VideoCommon;
 for(bool delayed:{false,true})for(unsigned mask=0;mask<8;++mask){
  Settings::delayed=delayed;Manager m;
  m.texture_cache.pending=mask&1;m.buffer_cache.pending=mask&2;m.query_cache.pending=mask&4;
  unsigned callbacks{};m.SignalFence([&]{++callbacks;});
  assert(m.queued==1&&m.fences.size()==1&&m.fences.front()->stubbed==(mask==0));
  assert(m.texture_cache.checks==1&&m.buffer_cache.checks==1&&m.query_cache.checks==1);
  assert(m.texture_cache.commits==bool(mask&1)&&m.buffer_cache.commits==bool(mask&2)&&m.query_cache.commits==1);
  assert(m.pending_flushes.back()==(mask&3)&&m.rasterizer.flushes==bool(mask));
  assert(callbacks==!delayed&&m.rasterizer.invalidates==1);
  if(delayed){assert(m.pending_operations.back().size()==1);m.pending_operations.back()[0]();assert(callbacks==1);}
 }
 Settings::delayed=false;
 {Manager m;m.skip=true;unsigned calls{};m.SignalFence([&]{++calls;});
  assert(calls==1&&!m.queued&&!m.query_cache.checks&&!m.query_cache.commits);}
 {Manager m;m.texture_cache.side_work=true;m.SignalFence([]{});
  assert(m.queued==1&&m.fences.front()->stubbed&&m.texture_cache.commits==1);
  assert(m.pending_flushes.back()==1&&!m.rasterizer.flushes);}
 {Manager m;m.buffer_cache.pending=true;m.SignalFence([]{});
  assert(m.queued==1&&!m.fences.front()->stubbed&&m.rasterizer.flushes==1);}
}
'''
with tempfile.TemporaryDirectory(prefix='fence-requirements-') as temp:
    path = Path(temp)
    (path / 'check.cpp').write_text(code)
    subprocess.run(['clang++-18', '-std=c++20', '-O1', '-g', '-pthread',
                    '-fsanitize=address,undefined', str(path / 'check.cpp'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True, timeout=10)
print('Fence requirements PASS: all cache masks in immediate/delayed modes, empty-fence skip, side-work stub and callback ordering')

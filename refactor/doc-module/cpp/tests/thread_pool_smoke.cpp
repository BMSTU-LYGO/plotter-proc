#include "plotter/doc/thread_pool.hpp"

#include <cassert>
#include <chrono>
#include <stdexcept>
#include <thread>

int main() {
    assert(plotter::doc::ThreadPool::resolve_thread_count(3) == 3U);
    assert(plotter::doc::ThreadPool::resolve_thread_count(0) >= 1U);
    assert(plotter::doc::ThreadPool::thread_count_from_string("auto") == 0U);
    assert(plotter::doc::ThreadPool::thread_count_from_string("3") == 3U);
    plotter::doc::ThreadPool pool({2, 2});
    const auto values = pool.map_indexed(24, [](std::size_t index) {
        std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>((24U - index) % 3U)));
        return index * index;
    });
    assert(values.size() == 24U);
    for (std::size_t index = 0; index < values.size(); ++index) assert(values[index] == index * index);
    auto future = pool.submit([] { return 42; });
    assert(future.get() == 42);
    pool.shutdown();
    bool rejected = false;
    try { (void)pool.submit([] { return 0; }); } catch (const std::runtime_error&) { rejected = true; }
    assert(rejected);
}

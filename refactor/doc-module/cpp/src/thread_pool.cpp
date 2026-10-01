#include "plotter/doc/thread_pool.hpp"

#include <algorithm>
#include <charconv>

namespace plotter::doc {

std::size_t ThreadPool::resolve_thread_count(std::size_t requested) noexcept {
    if (requested != 0U) return requested;
    return std::max<std::size_t>(1U, std::thread::hardware_concurrency());
}

std::size_t ThreadPool::thread_count_from_string(std::string_view value) {
    if (value == "auto") return 0U;
    std::size_t result{};
    const auto parsed = std::from_chars(value.data(), value.data() + value.size(), result);
    if (value.empty() || parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() || result == 0U)
        throw std::invalid_argument("thread count must be 'auto' or a positive integer");
    return result;
}

ThreadPool::ThreadPool(ThreadPoolOptions options)
    : maximum_queued_tasks_(options.maximum_queued_tasks) {
    if (maximum_queued_tasks_ == 0U) throw std::invalid_argument("thread pool queue bound must be positive");
    const std::size_t count = resolve_thread_count(options.thread_count);
    workers_.reserve(count);
    try {
        for (std::size_t index = 0; index < count; ++index) workers_.emplace_back(&ThreadPool::worker, this);
    } catch (...) {
        shutdown();
        throw;
    }
}

ThreadPool::~ThreadPool() { shutdown(); }

void ThreadPool::shutdown() {
    {
        std::lock_guard lock(mutex_);
        stopping_ = true;
    }
    task_available_.notify_all();
    queue_space_.notify_all();
    for (std::thread& worker_thread : workers_)
        if (worker_thread.joinable()) worker_thread.join();
}

void ThreadPool::worker() {
    for (;;) {
        std::function<void()> task;
        {
            std::unique_lock lock(mutex_);
            task_available_.wait(lock, [this] { return stopping_ || !tasks_.empty(); });
            if (stopping_ && tasks_.empty()) return;
            task = std::move(tasks_.front());
            tasks_.pop_front();
        }
        queue_space_.notify_one();
        task();
    }
}

}  // namespace plotter::doc

#pragma once

#include <condition_variable>
#include <cstddef>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string_view>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>
#include <deque>

namespace plotter::doc {

struct ThreadPoolOptions final {
    // Zero selects max(1, hardware_concurrency()).
    std::size_t thread_count{};
    std::size_t maximum_queued_tasks{1024};
};

class ThreadPool final {
public:
    explicit ThreadPool(ThreadPoolOptions options = {});
    ~ThreadPool();

    ThreadPool(const ThreadPool&) = delete;
    ThreadPool& operator=(const ThreadPool&) = delete;

    template <typename Function>
    [[nodiscard]] auto submit(Function&& function)
        -> std::future<std::invoke_result_t<std::decay_t<Function>&>>;

    // Calls function(index) once for every index and returns values ordered by
    // index, regardless of the order in which workers finish.
    template <typename Function>
    [[nodiscard]] auto map_indexed(std::size_t count, Function&& function)
        -> std::vector<std::invoke_result_t<std::decay_t<Function>&, std::size_t>>;

    void shutdown();
    [[nodiscard]] std::size_t thread_count() const noexcept { return workers_.size(); }
    [[nodiscard]] static std::size_t resolve_thread_count(std::size_t requested) noexcept;
    // Accepts "auto" or a positive decimal worker count; "auto" returns zero.
    [[nodiscard]] static std::size_t thread_count_from_string(std::string_view value);

private:
    void worker();

    std::size_t maximum_queued_tasks_{};
    std::vector<std::thread> workers_;
    std::deque<std::function<void()>> tasks_;
    mutable std::mutex mutex_;
    std::condition_variable task_available_, queue_space_;
    bool stopping_{};
};

template <typename Function>
auto ThreadPool::submit(Function&& function)
    -> std::future<std::invoke_result_t<std::decay_t<Function>&>> {
    using Result = std::invoke_result_t<std::decay_t<Function>&>;
    auto task = std::make_shared<std::packaged_task<Result()>>(std::forward<Function>(function));
    std::future<Result> result = task->get_future();
    {
        std::unique_lock lock(mutex_);
        queue_space_.wait(lock, [this] { return stopping_ || tasks_.size() < maximum_queued_tasks_; });
        if (stopping_) throw std::runtime_error("cannot submit work after thread pool shutdown");
        tasks_.emplace_back([task] { (*task)(); });
    }
    task_available_.notify_one();
    return result;
}

template <typename Function>
auto ThreadPool::map_indexed(std::size_t count, Function&& function)
    -> std::vector<std::invoke_result_t<std::decay_t<Function>&, std::size_t>> {
    using Result = std::invoke_result_t<std::decay_t<Function>&, std::size_t>;
    static_assert(!std::is_void_v<Result>, "map_indexed requires a non-void result");
    std::vector<std::future<Result>> futures;
    futures.reserve(count);
    for (std::size_t index = 0; index < count; ++index)
        futures.push_back(submit([function, index]() mutable { return std::invoke(function, index); }));
    std::vector<Result> result;
    result.reserve(count);
    for (auto& future : futures) result.push_back(future.get());
    return result;
}

}  // namespace plotter::doc

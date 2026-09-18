#include <array>
#include <atomic>
#include <span>

#include <psp2/kernel/processmgr.h>

namespace {

constexpr int Sum(std::span<const int> values) {
    int total = 0;
    for (const int value : values) {
        total += value;
    }
    return total;
}

static_assert(Sum(std::array{1, 2, 3, 4}) == 10);

} // namespace

int main() {
    const std::array values{1, 2, 3, 4};
    std::atomic<int> result{Sum(values)};
    sceKernelExitProcess(result.load() == 10 ? 0 : 1);
    return 0;
}

#include <array>
#include <atomic>
#include <span>

#include <psp2/kernel/processmgr.h>

#include "../../../src/idlib/CryptoHash.h"

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

    std::uint8_t digest[idCrypto::SHA256_DIGEST_BYTES] = {};
    idCrypto::SHA256(nullptr, 0, digest);
    const bool sha256Ok =
        digest[0] == 0xe3 && digest[1] == 0xb0 &&
        digest[2] == 0xc4 && digest[3] == 0x42;

    sceKernelExitProcess(result.load() == 10 && sha256Ok ? 0 : 1);
    return 0;
}

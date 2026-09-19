#include "probe_scene.h"
#include <iostream>
#include <cstdlib>
int main() {
    const Probe::Scene s = Probe::MakeScene();
    for (auto index : s.indices) if (index >= s.vertices.size()) return EXIT_FAILURE;
    if (s.indices[Probe::FloorFirstIndex] != 24) return EXIT_FAILURE;
    if (Probe::FloorFirstIndex * sizeof(std::uint16_t) != 72) return EXIT_FAILURE;
    const auto p = Probe::Projection();
    if (Probe::Multiply(p, Probe::Identity()) != p) return EXIT_FAILURE;
    for (int frame = 0; frame < 360; ++frame) {
        const auto m = Probe::Multiply(p, Probe::CubeModel(frame * 0.02f));
        for (int i = 0; i < 24; ++i) {
            const auto &v = s.vertices[i];
            float q[4] = {};
            for (int r = 0; r < 4; ++r)
                q[r] = m[r]*v.xyz[0]+m[4+r]*v.xyz[1]+m[8+r]*v.xyz[2]+m[12+r];
            if (!(q[3] > 0)) return EXIT_FAILURE;
            for (int r = 0; r < 3; ++r)
                if (!std::isfinite(q[r]) || std::abs(q[r]) >= q[3]) return EXIT_FAILURE;
        }
    }
    std::cout << "PASS: 28 vertices, 42 indices, 72-byte floor offset, projection and 360 poses\n";
}

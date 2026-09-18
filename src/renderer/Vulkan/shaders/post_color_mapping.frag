#version 450

// r_brightness and r_gamma over the finished frame, HUD and menus included.
// Same arithmetic as the OpenGL builtin/final_color_mapping program that
// RB_ApplyColorMappingsToBackBuffer draws (draw_common.cpp).

layout(set = 0, binding = 0) uniform sampler2D sceneCopy;	// bottom-up capture of the swapchain

layout(std140, set = 6, binding = 0) uniform ColorMappingBlock {
    vec4 params;	// x: brightness, y: gamma
} block;

layout(location = 0) in vec2 fragUV;
layout(location = 0) out vec4 outColor;

void main() {
    vec4 sampleColor = texture(sceneCopy, vec2(fragUV.x, 1.0 - fragUV.y));
    vec3 color = clamp(sampleColor.rgb * block.params.x, 0.0, 1.0);
    float safeGamma = max(block.params.y, 0.001);
    color = pow(color, vec3(1.0 / safeGamma));
    outColor = vec4(color, sampleColor.a);
}

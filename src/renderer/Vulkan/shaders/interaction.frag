#version 450

// openQ4 Vulkan interaction pipeline — fragment stage (Phase F1).
//
// interaction.vfp parity math: DXT5/RXGB bump decode (alpha=x, green=y,
// blue=z, no renormalization), projected light-falloff and light-projection
// samples, diffuse map × diffuseColor, and specular through the REAL
// _specularTable ramp — the table carries clamp((N·H)·4−3)² and the CPU-side
// ARB2 path doubles the specular env constant, so the ×2 lives here.
// Direction vectors normalize in-shader (no normalization cube map, locked
// Phase F decision). Ambient lights substitute the constant tangent-space
// direction the ambient normal-map cube decodes to (pushed as pc.b, with
// the cube's 8-bit quantization applied CPU-side). The shipped
// Parallaxbump custom-lighting guide enables a scale/bias height offset
// through pc.c; the otherwise-unused red channel of RXGB normal maps holds
// the height while alpha/green/blue retain the tangent-space normal.
// Additive ONE:ONE blend; alpha writes 0 like the GL reference.

layout(set = 0, binding = 0) uniform sampler2D specularTableMap;
layout(set = 1, binding = 0) uniform sampler2D bumpMap;
layout(set = 2, binding = 0) uniform sampler2D lightFalloffMap;
layout(set = 3, binding = 0) uniform sampler2D lightProjectionMap;
layout(set = 4, binding = 0) uniform sampler2D diffuseMap;
layout(set = 5, binding = 0) uniform sampler2D specularMap;

layout(push_constant) uniform InteractionPushConstants {
    mat4 mvp;
    vec4 a;
    vec4 b;
    vec4 c;
    vec4 d;
} pc;

layout(set = 6, binding = 0, std140) uniform InteractionBlock {
    vec4 localLightOrigin;
    vec4 localViewOrigin;
    vec4 lightProjectionS;
    vec4 lightProjectionT;
    vec4 lightProjectionQ;
    vec4 lightFalloffS;
    vec4 bumpMatrixS;
    vec4 bumpMatrixT;
    vec4 diffuseMatrixS;
    vec4 diffuseMatrixT;
    vec4 specularMatrixS;
    vec4 specularMatrixT;
    vec4 diffuseColor;
    vec4 specularColor;
    vec4 flatDiffuseParams;
    // cel banding (RB_SetCelInteractionUniform): x enabled, y band count,
    // z hard specular, w softness; zero when the surface is not banded
    vec4 celParams;
} inter;

layout(location = 0) in vec2 vBumpTexCoord;
layout(location = 1) in vec2 vDiffuseTexCoord;
layout(location = 2) in vec2 vSpecularTexCoord;
layout(location = 3) in vec4 vLightFalloffTexCoord;
layout(location = 4) in vec4 vLightProjectionTexCoord;
layout(location = 5) in vec3 vLightVector;
layout(location = 6) in vec3 vHalfAngleVector;
layout(location = 7) in vec3 vVertexColor;
layout(location = 8) in vec3 vViewVector;

layout(location = 0) out vec4 outColor;

vec3 SafeNormalize(vec3 value) {
    return value * inversesqrt(max(dot(value, value), 1.0e-8));
}

vec3 ApplyFlatDiffuseSweep(vec3 diffuse, float localZ) {
    if (inter.flatDiffuseParams.x <= 0.0) {
        return diffuse;
    }
    float height = clamp((localZ - inter.flatDiffuseParams.y)
        * inter.flatDiffuseParams.z, 0.0, 1.0);
    float distanceToBand = abs(height - fract(inter.flatDiffuseParams.w));
    distanceToBand = min(distanceToBand, 1.0 - distanceToBand);
    float band = 1.0 - smoothstep(0.045, 0.16, distanceToBand);
    return mix(diffuse, vec3(1.0), inter.flatDiffuseParams.x * band);
}

vec3 EvaluatePackedPBR(vec3 localNormal, vec2 albedoTexCoord,
        vec2 ormTexCoord, float shadowFactor) {
    vec3 albedo = pow(max(texture(diffuseMap, albedoTexCoord).rgb, vec3(0.0)), vec3(2.2));
    vec3 orm = texture(specularMap, ormTexCoord).rgb;
    float metallic = clamp(orm.b * pc.d.y, 0.0, 1.0);
    float roughness = clamp(orm.g * pc.d.z, 0.045, 1.0);
    vec3 lightDir = (pc.a.z > 0.5) ? pc.b.xyz : SafeNormalize(vLightVector);
    vec3 viewDir = SafeNormalize(vViewVector);
    vec3 halfDir = SafeNormalize(lightDir + viewDir);
    float ndotl = max(dot(localNormal, lightDir), 0.0);
    float ndotv = max(dot(localNormal, viewDir), 0.0);
    float ndoth = max(dot(localNormal, halfDir), 0.0);
    float vdoth = max(dot(viewDir, halfDir), 0.0);
    float alpha = roughness * roughness;
    float alphaSquared = alpha * alpha;
    float denom = max(ndoth * ndoth * (alphaSquared - 1.0) + 1.0, 1.0e-4);
    float distribution = alphaSquared / (3.14159265 * denom * denom);
    float k = (roughness + 1.0) * (roughness + 1.0) * 0.125;
    float geometry = (ndotl / max(ndotl * (1.0 - k) + k, 1.0e-4))
        * (ndotv / max(ndotv * (1.0 - k) + k, 1.0e-4));
    vec3 f0 = mix(vec3(0.04), albedo, metallic);
    vec3 fresnel = f0 + (vec3(1.0) - f0) * pow(1.0 - vdoth, 5.0);
    vec3 specular = distribution * geometry * fresnel
        / max(4.0 * ndotl * ndotv, 1.0e-4);
    vec3 diffuse = (vec3(1.0) - fresnel) * (1.0 - metallic)
        * albedo * (1.0 / 3.14159265);
    vec3 radiance = textureProj(lightFalloffMap, vLightFalloffTexCoord).rgb
        * textureProj(lightProjectionMap, vLightProjectionTexCoord).rgb
        * inter.diffuseColor.rgb * shadowFactor;
    return (diffuse + specular) * radiance * ndotl * vVertexColor;
}

// ---------------------------------------------------------------------------
// Cel banding, from glprogs/material_interaction.fs and the shadow interaction
// programs. inter.celParams is ( bandsEnabled, bandCount, hardSpecular,
// softness ); R_CelQuantizeUnitValue is the CPU copy of the ladder.
// ---------------------------------------------------------------------------

float CelSteps() {
    return max(inter.celParams.y - 1.0, 1.0);
}

// Places a 0..1 value on the band ladder; softness widens every boundary into
// a smoothstep centred where the hard step would land.
float CelLadder(float value) {
    float steps = CelSteps();
    float scaled = value * steps;

    float softness = clamp(inter.celParams.w, 0.0, 1.0);
    if (softness <= 0.0) {
        return floor(scaled + 0.5) / steps;
    }

    float lower = floor(scaled);
    float halfWidth = softness * 0.5;
    float blend = smoothstep(0.5 - halfWidth, 0.5 + halfWidth, scaled - lower);

    return (lower + blend) / steps;
}

// Quantizes a light contribution without shifting its hue: the brightest
// channel picks the band. Black and overbright pass through untouched.
vec3 CelQuantizeLight(vec3 light) {
    if (inter.celParams.x <= 0.5) {
        return light;
    }

    float peak = max(max(light.r, light.g), light.b);
    if (peak <= 0.0 || peak >= 1.0) {
        return light;
    }

    return light * (CelLadder(peak) / peak);
}

// Collapses the specular falloff into flat plateaus on the same ladder.
float CelSpecularTerm(float term) {
    if (inter.celParams.x <= 0.5 || inter.celParams.z <= 0.5) {
        return term;
    }

    return CelLadder(clamp(term, 0.0, 1.0));
}

void main() {
    vec2 bumpTexCoord = vBumpTexCoord;
    vec2 diffuseTexCoord = vDiffuseTexCoord;
    vec2 specularTexCoord = vSpecularTexCoord;
    if (pc.d.x > 1.5) {
        outColor = vec4(0.0, 1.0, 0.0, 0.0);
        return;
    }
    if (pc.c.z > 0.5) {
        float height = texture(bumpMap, bumpTexCoord).r;
        vec2 offset = SafeNormalize(vViewVector).xy * (height * pc.c.x + pc.c.y);
        bumpTexCoord += offset;
        diffuseTexCoord += offset;
        specularTexCoord += offset;
    }

    vec4 bumpSample = texture(bumpMap, bumpTexCoord);
    if (pc.d.x > 0.5) {
        vec3 localNormal = bumpSample.rgb * 2.0 - 1.0;
        localNormal.xy *= pc.d.w;
        outColor = vec4(EvaluatePackedPBR(SafeNormalize(localNormal),
            diffuseTexCoord, specularTexCoord, 1.0), 0.0);
        return;
    }
    vec3 localNormal = vec3(bumpSample.a, bumpSample.g, bumpSample.b) * 2.0 - 1.0;

    vec3 lightDir = (pc.a.z > 0.5) ? pc.b.xyz : SafeNormalize(vLightVector);
    float ndotl = max(dot(lightDir, localNormal), 0.0);

    vec3 light = vec3(ndotl);
    light *= textureProj(lightFalloffMap, vLightFalloffTexCoord).rgb;
    light *= textureProj(lightProjectionMap, vLightProjectionTexCoord).rgb;

    vec3 diffuse = texture(diffuseMap, diffuseTexCoord).rgb * inter.diffuseColor.rgb;
    diffuse = ApplyFlatDiffuseSweep(diffuse, vLightFalloffTexCoord.z);

    vec3 halfAngle = SafeNormalize(vHalfAngleVector);
    float specularDot = clamp(dot(halfAngle, localNormal), 0.0, 1.0);
    float specularTerm = texture(specularTableMap, vec2(specularDot, 0.5)).r * 2.0;
    specularTerm = CelSpecularTerm(specularTerm);
    vec3 specular = texture(specularMap, specularTexCoord).rgb * inter.specularColor.rgb * specularTerm;

    light = CelQuantizeLight(light);
    outColor = vec4((diffuse + specular) * light * vVertexColor, 0.0);
}

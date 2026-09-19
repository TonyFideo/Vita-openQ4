// Copyright (C) 2004 Id Software, Inc.
//
// Keep the existing implementation byte-for-byte for desktop/Android builds.
// Vita selects GLES_D3 and must not compile or advertise the compute/SSBO
// clustered path. No classic light, stencil or material pass is removed here.
#if !defined(VITA) && !defined(__vita__)
#include "ModernClusteredLighting.desktop.inc"
#else
#include "tr_local.h"
#include "ModernClusteredLighting.h"

static rendererClusteredLightingStats_t vitaClusterStats = {};
static rendererClusteredDecalStats_t vitaDecalStats = {};

void R_ModernClusteredLighting_ResetDecalsForFrame(void) {
    memset(&vitaDecalStats, 0, sizeof(vitaDecalStats));
    vitaDecalStats.lastReject = RENDERER_CLUSTER_DECAL_REJECT_RESOURCE_UNAVAILABLE;
    vitaDecalStats.lastRejectSource = vitaDecalStats.lastRejectView = -1;
    idStr::Copynz(vitaDecalStats.status, "unavailable on Vita GLES_D3", sizeof(vitaDecalStats.status));
}
void R_ModernClusteredLighting_Shutdown(void) {
    memset(&vitaClusterStats, 0, sizeof(vitaClusterStats));
    idStr::Copynz(vitaClusterStats.status, "unavailable on Vita GLES_D3", sizeof(vitaClusterStats.status));
    R_ModernClusteredLighting_ResetDecalsForFrame();
}
void R_ModernClusteredLighting_Init(const renderBackendCaps_t &, const renderFeatureSet_t &) {
    R_ModernClusteredLighting_Shutdown();
    vitaClusterStats.initialized = true;
}
void R_ModernClusteredLighting_PrepareFrame(const idScenePacketFrame &, bool requested) {
    vitaClusterStats.requested = requested;
    R_ModernClusteredLighting_ResetDecalsForFrame();
}
void R_ModernClusteredLighting_DrawDebugOverlay(void) {}
void R_ModernClusteredLighting_PrintGfxInfo(void) {
    common->Printf("Clustered lighting: unavailable on Vita; GLES_D3 owns lighting\n");
}
const rendererClusteredLightingStats_t &R_ModernClusteredLighting_Stats(void) { return vitaClusterStats; }
bool R_ModernClusteredLighting_FrameLossless(void) { return false; }
bool R_ModernClusteredLighting_BindGridForView(const viewDef_t *) { return false; }
int R_ModernClusteredLighting_NumLightDescriptors(void) { return 0; }
const rendererModernLightDescriptor_t *R_ModernClusteredLighting_LightDescriptor(int) { return NULL; }
int R_ModernClusteredLighting_NumShadowDescriptors(void) { return 0; }
const rendererModernShadowDescriptor_t *R_ModernClusteredLighting_ShadowDescriptor(int) { return NULL; }
int R_ModernClusteredLighting_ShadowDescriptorUboBlockBytes(void) { return 0; }
int R_ModernClusteredLighting_ProbeUboBlockBytes(void) { return 0; }
bool R_ModernClusteredLighting_PrepareDecals(const rendererClusteredDecalSource_t *, int, unsigned int) { return false; }
bool R_ModernClusteredLighting_SealDecals(const rendererClusteredDecalSource_t *, int, unsigned int) { return false; }
bool R_ModernClusteredLighting_RejectDecalsForFrame(rendererClusteredDecalReject_t reason, int sourceIndex, int submittedRecords, unsigned int generation) {
    R_ModernClusteredLighting_ResetDecalsForFrame();
    vitaDecalStats.lastReject = reason;
    vitaDecalStats.lastRejectSource = sourceIndex;
    vitaDecalStats.submittedRecords = submittedRecords;
    vitaDecalStats.generation = generation;
    return false;
}
const rendererClusteredDecalStats_t &R_ModernClusteredLighting_DecalStats(void) { return vitaDecalStats; }
bool R_ModernClusteredLighting_DecalViewStats(const viewDef_t *viewDef, rendererClusteredDecalViewStats_t &stats) {
    memset(&stats, 0, sizeof(stats));
    stats.viewDef = viewDef;
    stats.firstCommandOrder = stats.lastCommandOrder = -1;
    return false;
}
bool R_ModernClusteredLighting_DecalOwnsSurface(const viewDef_t *, const void *) { return false; }
bool R_ModernClusteredLighting_DecalOwnsCommand(const viewDef_t *, int) { return false; }
int R_ModernClusteredLighting_DecalSealedCommandForSurface(const viewDef_t *, const void *, bool &duplicate) {
    duplicate = false;
    return -1;
}
const char *R_ModernClusteredLighting_DecalRejectName(rendererClusteredDecalReject_t) { return "unavailable-vita-glesd3"; }
bool RendererClusterGrid_RunSelfTest(void) {
    common->Printf("Cluster grid self-test unavailable on Vita GLES_D3\n");
    return false;
}
#endif

// Vita's GLES_D3 path has no compute shaders or SSBOs. Keep the desktop
// implementation byte-for-byte for other platforms and request the existing
// CPU skinning fallback on Vita.
#if defined(VITA) || defined(__vita__)
#include "../tr_local.h"
#include "../GpuSkinning.h"

void R_BackendGpuSkinning_Init( const renderBackendCaps_t & ) {
}

void R_BackendGpuSkinning_Shutdown( void ) {
}

bool R_BackendGpuSkinning_PrepareAmbientCache( srfTriangles_t *tri, bool needsLighting ) {
	(void)needsLighting;
	if ( tri == NULL ) {
		R_GpuSkinning_RecordFallback( GPU_SKINNING_FALLBACK_VERTEX_COUNT );
		return false;
	}
	if ( tri->ambientCache != NULL ) {
		return true;
	}
	R_GpuSkinning_RecordFallback( GPU_SKINNING_FALLBACK_BACKEND_UNAVAILABLE );
	return false;
}

void R_BackendGpuSkinning_PrintGfxInfo( void ) {
	common->Printf( "GPU skinning compute (OpenGL): unavailable on Vita; CPU fallback active\n" );
}
#else
#include "GpuSkinningGL.desktop.inc"
#endif

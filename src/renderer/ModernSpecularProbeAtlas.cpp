// Vita keeps the classic GLES_D3 interaction path. The modern specular probe
// atlas requires desktop cubemap readback through glGetTexImage, unavailable
// in vitaGL. Preserve the desktop implementation verbatim and fail closed.
#if defined(VITA) || defined(__vita__)
#include "tr_local.h"
#include "ModernSpecularProbeAtlas.h"
#include <cstring>

static modernSpecularProbeAtlasStats_t g_vitaSpecularAtlasStats;

static void VitaSpecularAtlasStatus( const char *status ) {
	std::memset( g_vitaSpecularAtlasStats.status, 0, sizeof( g_vitaSpecularAtlasStats.status ) );
	if ( status != NULL ) {
		std::strncpy( g_vitaSpecularAtlasStats.status, status, sizeof( g_vitaSpecularAtlasStats.status ) - 1 );
	}
}

const char *ModernSpecularProbeAtlasReject_Name( modernSpecularProbeAtlasReject_t reject ) {
	switch ( reject ) {
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_NONE: return "none";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_NULL_OUTPUT: return "null-output";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_NULL_IMAGE: return "null-image";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_UNAVAILABLE: return "unavailable";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_NOT_LOADED: return "not-loaded";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_DEFAULTED: return "defaulted";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_MUTABLE: return "mutable";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_NOT_CUBE: return "not-cube";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_NON_SQUARE: return "non-square";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_OVERSIZED: return "oversized";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_INVALID_STORAGE: return "invalid-storage";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_ATLAS_FULL: return "atlas-full";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_SOURCE_CHANGED: return "source-changed";
	case MODERN_SPECULAR_PROBE_ATLAS_REJECT_UPLOAD_UNAVAILABLE: return "upload-unavailable";
	default: return "unknown";
	}
}

void R_ModernSpecularProbeAtlas_Init( const renderBackendCaps_t &, const renderFeatureSet_t & ) {
	std::memset( &g_vitaSpecularAtlasStats, 0, sizeof( g_vitaSpecularAtlasStats ) );
	VitaSpecularAtlasStatus( "unavailable-vita-gles-d3" );
}

void R_ModernSpecularProbeAtlas_Shutdown( void ) {
	std::memset( &g_vitaSpecularAtlasStats, 0, sizeof( g_vitaSpecularAtlasStats ) );
	VitaSpecularAtlasStatus( "off" );
}

void R_ModernSpecularProbeAtlas_BeginFrame( void ) {
	g_vitaSpecularAtlasStats.acquires = 0;
	g_vitaSpecularAtlasStats.cacheHits = 0;
	g_vitaSpecularAtlasStats.uploadedEntries = 0;
	g_vitaSpecularAtlasStats.uploadedFaces = 0;
}

modernSpecularProbeAtlasReject_t R_ModernSpecularProbeAtlas_Acquire(
	const idImage *image, modernSpecularProbeAtlasPlacement_t *placement ) {
	g_vitaSpecularAtlasStats.acquires++;
	if ( placement == NULL ) {
		g_vitaSpecularAtlasStats.rejectedNullOutput++;
		return MODERN_SPECULAR_PROBE_ATLAS_REJECT_NULL_OUTPUT;
	}
	ModernSpecularProbeAtlas_ClearPlacement( *placement );
	if ( image == NULL ) {
		g_vitaSpecularAtlasStats.rejectedNullImage++;
		return MODERN_SPECULAR_PROBE_ATLAS_REJECT_NULL_IMAGE;
	}
	g_vitaSpecularAtlasStats.rejectedUnavailable++;
	return MODERN_SPECULAR_PROBE_ATLAS_REJECT_UNAVAILABLE;
}

void R_ModernSpecularProbeAtlas_FlushUploads( void ) {}
unsigned int R_ModernSpecularProbeAtlas_Texture( void ) { return 0; }
bool R_ModernSpecularProbeAtlas_Ready( void ) { return false; }
bool R_ModernSpecularProbeAtlas_FrameReady( void ) { return false; }
const modernSpecularProbeAtlasStats_t &R_ModernSpecularProbeAtlas_Stats( void ) { return g_vitaSpecularAtlasStats; }

void R_ModernSpecularProbeAtlas_PrintGfxInfo( void ) {
	common->Printf( "Modern specular probe atlas: unavailable on Vita GLES_D3\n" );
}

bool RendererSpecularProbeAtlas_RunSelfTest( void ) {
	return true;
}

#else
#include "ModernSpecularProbeAtlas.desktop.inc"
#endif

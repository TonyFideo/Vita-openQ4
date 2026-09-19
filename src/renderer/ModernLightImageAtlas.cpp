// Vita keeps the classic GLES_D3 lighting path. Modern clustered light atlases
// depend on desktop texture readback (glGetTexImage), which vitaGL does not
// expose. Preserve the desktop implementation verbatim and fail closed here.
#if defined(VITA) || defined(__vita__)
#include "tr_local.h"
#include "ModernLightImageAtlas.h"
#include <cstring>

static modernLightImageAtlasStats_t g_vitaLightAtlasStats;

static void VitaLightAtlasStatus( const char *status ) {
	std::memset( g_vitaLightAtlasStats.status, 0, sizeof( g_vitaLightAtlasStats.status ) );
	if ( status != NULL ) {
		std::strncpy( g_vitaLightAtlasStats.status, status, sizeof( g_vitaLightAtlasStats.status ) - 1 );
	}
}

const char *ModernLightAtlasReject_Name( modernLightAtlasReject_t reject ) {
	switch ( reject ) {
	case MODERN_LIGHT_ATLAS_REJECT_NONE: return "none";
	case MODERN_LIGHT_ATLAS_REJECT_NULL_IMAGE: return "null-image";
	case MODERN_LIGHT_ATLAS_REJECT_NOT_LOADED: return "image-not-loaded";
	case MODERN_LIGHT_ATLAS_REJECT_CUBE_MAP: return "cube-map-light-image";
	case MODERN_LIGHT_ATLAS_REJECT_OVERSIZED: return "light-image-oversized";
	case MODERN_LIGHT_ATLAS_REJECT_ATLAS_FULL: return "light-atlas-full";
	case MODERN_LIGHT_ATLAS_REJECT_UNAVAILABLE: return "light-atlas-unavailable";
	default: return "unknown";
	}
}

void R_ModernLightImageAtlas_Init( const renderBackendCaps_t &, const renderFeatureSet_t & ) {
	std::memset( &g_vitaLightAtlasStats, 0, sizeof( g_vitaLightAtlasStats ) );
	VitaLightAtlasStatus( "unavailable-vita-gles-d3" );
}

void R_ModernLightImageAtlas_Shutdown( void ) {
	std::memset( &g_vitaLightAtlasStats, 0, sizeof( g_vitaLightAtlasStats ) );
	VitaLightAtlasStatus( "off" );
}

void R_ModernLightImageAtlas_BeginFrame( void ) {
	g_vitaLightAtlasStats.acquires = 0;
	g_vitaLightAtlasStats.cacheHits = 0;
	g_vitaLightAtlasStats.uploads = 0;
	g_vitaLightAtlasStats.evictions = 0;
	g_vitaLightAtlasStats.rejectedNullImage = 0;
	g_vitaLightAtlasStats.rejectedNotLoaded = 0;
	g_vitaLightAtlasStats.rejectedCubeMap = 0;
	g_vitaLightAtlasStats.rejectedOversized = 0;
	g_vitaLightAtlasStats.rejectedAtlasFull = 0;
}

modernLightAtlasReject_t R_ModernLightImageAtlas_Acquire( const idImage *image, float rect[4] ) {
	if ( rect != NULL ) {
		rect[0] = rect[1] = rect[2] = rect[3] = 0.0f;
	}
	g_vitaLightAtlasStats.acquires++;
	if ( image == NULL ) {
		g_vitaLightAtlasStats.rejectedNullImage++;
		return MODERN_LIGHT_ATLAS_REJECT_NULL_IMAGE;
	}
	return MODERN_LIGHT_ATLAS_REJECT_UNAVAILABLE;
}

void R_ModernLightImageAtlas_FlushUploads( void ) {}
unsigned int R_ModernLightImageAtlas_Texture( void ) { return 0; }
bool R_ModernLightImageAtlas_Ready( void ) { return false; }
const modernLightImageAtlasStats_t &R_ModernLightImageAtlas_Stats( void ) { return g_vitaLightAtlasStats; }

void R_ModernLightImageAtlas_PrintGfxInfo( void ) {
	common->Printf( "Modern light image atlas: unavailable on Vita GLES_D3\n" );
}

bool RendererLightImageAtlas_RunSelfTest( void ) {
	// Unavailability is intentional on Vita; the classic interaction path does
	// not consume this atlas.
	return true;
}

#else
#include "ModernLightImageAtlas.desktop.inc"
#endif

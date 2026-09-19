#include "vita_debug_screen.h"

#include <psp2/display.h>
#include <psp2/gxm.h>
#include <psp2/kernel/sysmem.h>

#include <stdint.h>
#include <string.h>

namespace {

static const int VITA_SCREEN_WIDTH = 960;
static const int VITA_SCREEN_HEIGHT = 544;
static const int VITA_SCREEN_PITCH = 960;
static const int VITA_SCREEN_BYTES = 2 * 1024 * 1024;
static const int VITA_FONT_SCALE = 2;
static const int VITA_FONT_WIDTH = 5;
static const int VITA_FONT_HEIGHT = 7;
static const int VITA_CHAR_ADVANCE = 12;
static const int VITA_LINE_ADVANCE = 18;
static const int VITA_MARGIN_X = 24;
static const int VITA_MARGIN_Y = 20;

static const uint32_t VITA_COLOR_BLACK = 0xFF000000U;
static const uint32_t VITA_COLOR_WHITE = 0xFFFFFFFFU;
static const uint32_t VITA_COLOR_GREEN = 0xFF80FF80U;
static const uint32_t VITA_COLOR_YELLOW = 0xFF00FFFFU;
static const uint32_t VITA_COLOR_RED = 0xFF0000FFU;

struct VitaGlyph {
	char character;
	uint8_t rows[VITA_FONT_HEIGHT];
};

static const VitaGlyph kGlyphs[] = {
	{ 'A', { 0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11 } },
	{ 'B', { 0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E } },
	{ 'C', { 0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E } },
	{ 'D', { 0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E } },
	{ 'E', { 0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F } },
	{ 'F', { 0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10 } },
	{ 'G', { 0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F } },
	{ 'H', { 0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11 } },
	{ 'I', { 0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E } },
	{ 'J', { 0x01, 0x01, 0x01, 0x01, 0x11, 0x11, 0x0E } },
	{ 'K', { 0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11 } },
	{ 'L', { 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F } },
	{ 'M', { 0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11 } },
	{ 'N', { 0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11 } },
	{ 'O', { 0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E } },
	{ 'P', { 0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10 } },
	{ 'Q', { 0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D } },
	{ 'R', { 0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11 } },
	{ 'S', { 0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E } },
	{ 'T', { 0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04 } },
	{ 'U', { 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E } },
	{ 'V', { 0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04 } },
	{ 'W', { 0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A } },
	{ 'X', { 0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11 } },
	{ 'Y', { 0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04 } },
	{ 'Z', { 0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F } },
	{ '0', { 0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E } },
	{ '1', { 0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E } },
	{ '2', { 0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F } },
	{ '3', { 0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E } },
	{ '4', { 0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02 } },
	{ '5', { 0x1F, 0x10, 0x10, 0x1E, 0x01, 0x01, 0x1E } },
	{ '6', { 0x0E, 0x10, 0x10, 0x1E, 0x11, 0x11, 0x0E } },
	{ '7', { 0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08 } },
	{ '8', { 0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E } },
	{ '9', { 0x0E, 0x11, 0x11, 0x0F, 0x01, 0x01, 0x0E } },
	{ '-', { 0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00 } },
	{ ':', { 0x00, 0x04, 0x04, 0x00, 0x04, 0x04, 0x00 } },
	{ '.', { 0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x04 } },
	{ '/', { 0x01, 0x02, 0x02, 0x04, 0x08, 0x08, 0x10 } },
	{ '=', { 0x00, 0x00, 0x1F, 0x00, 0x1F, 0x00, 0x00 } },
	{ '_', { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F } },
	{ '[', { 0x0E, 0x08, 0x08, 0x08, 0x08, 0x08, 0x0E } },
	{ ']', { 0x0E, 0x02, 0x02, 0x02, 0x02, 0x02, 0x0E } },
	{ '%', { 0x19, 0x19, 0x02, 0x04, 0x08, 0x13, 0x13 } },
	{ '?', { 0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04 } }
};

static SceUID vitaDisplayBlock = -1;
static uint32_t *vitaFrameBuffer = NULL;
static SceDisplayFrameBuf vitaDisplayFrame;
static bool vitaDisplayFrameValid = false;
static int vitaCursorY = VITA_MARGIN_Y;

static const uint8_t *Vita_FindGlyph( char character ) {
	for ( unsigned int i = 0; i < sizeof( kGlyphs ) / sizeof( kGlyphs[0] ); ++i ) {
		if ( kGlyphs[i].character == character ) {
			return kGlyphs[i].rows;
		}
	}
	for ( unsigned int i = 0; i < sizeof( kGlyphs ) / sizeof( kGlyphs[0] ); ++i ) {
		if ( kGlyphs[i].character == '?' ) {
			return kGlyphs[i].rows;
		}
	}
	return NULL;
}

static char Vita_NormalizeChar( char character ) {
	if ( character >= 'a' && character <= 'z' ) {
		return static_cast<char>( character - 'a' + 'A' );
	}
	return character;
}

static uint32_t Vita_ColorForLine( vitaDiagColor_t color ) {
	switch ( color ) {
		case VITA_DIAG_OK:
			return VITA_COLOR_GREEN;
		case VITA_DIAG_WARN:
			return VITA_COLOR_YELLOW;
		case VITA_DIAG_ERROR:
			return VITA_COLOR_RED;
		case VITA_DIAG_INFO:
		default:
			return VITA_COLOR_WHITE;
	}
}

static void Vita_DrawPixelBlock( int x, int y, uint32_t color ) {
	if ( vitaFrameBuffer == NULL ) {
		return;
	}
	for ( int sy = 0; sy < VITA_FONT_SCALE; ++sy ) {
		const int py = y + sy;
		if ( py < 0 || py >= VITA_SCREEN_HEIGHT ) {
			continue;
		}
		for ( int sx = 0; sx < VITA_FONT_SCALE; ++sx ) {
			const int px = x + sx;
			if ( px >= 0 && px < VITA_SCREEN_WIDTH ) {
				vitaFrameBuffer[py * VITA_SCREEN_PITCH + px] = color;
			}
		}
	}
}

static void Vita_DrawChar( int x, int y, char input, uint32_t color ) {
	const char character = Vita_NormalizeChar( input );
	if ( character == ' ' ) {
		return;
	}
	const uint8_t *rows = Vita_FindGlyph( character );
	if ( rows == NULL ) {
		return;
	}
	for ( int row = 0; row < VITA_FONT_HEIGHT; ++row ) {
		for ( int col = 0; col < VITA_FONT_WIDTH; ++col ) {
			const uint8_t mask = static_cast<uint8_t>( 1U << ( VITA_FONT_WIDTH - 1 - col ) );
			if ( ( rows[row] & mask ) != 0 ) {
				Vita_DrawPixelBlock(
					x + col * VITA_FONT_SCALE,
					y + row * VITA_FONT_SCALE,
					color );
			}
		}
	}
}

}

bool VitaDiagScreen_Init( void ) {
	if ( vitaFrameBuffer != NULL ) {
		return true;
	}

	vitaDisplayBlock = sceKernelAllocMemBlock(
		"openq4-prerender-screen",
		SCE_KERNEL_MEMBLOCK_TYPE_USER_CDRAM_RW,
		VITA_SCREEN_BYTES,
		NULL );
	if ( vitaDisplayBlock < 0 ) {
		return false;
	}

	void *base = NULL;
	if ( sceKernelGetMemBlockBase( vitaDisplayBlock, &base ) < 0 || base == NULL ) {
		sceKernelFreeMemBlock( vitaDisplayBlock );
		vitaDisplayBlock = -1;
		return false;
	}
	vitaFrameBuffer = static_cast<uint32_t *>( base );

	VitaDiagScreen_Clear();

	memset( &vitaDisplayFrame, 0, sizeof( vitaDisplayFrame ) );
	vitaDisplayFrame.size = sizeof( vitaDisplayFrame );
	vitaDisplayFrame.base = vitaFrameBuffer;
	vitaDisplayFrame.pitch = VITA_SCREEN_PITCH;
	vitaDisplayFrame.pixelformat = SCE_DISPLAY_PIXELFORMAT_A8B8G8R8;
	vitaDisplayFrame.width = VITA_SCREEN_WIDTH;
	vitaDisplayFrame.height = VITA_SCREEN_HEIGHT;

	if ( sceDisplaySetFrameBuf( &vitaDisplayFrame, SCE_DISPLAY_SETBUF_NEXTFRAME ) < 0 ) {
		vitaFrameBuffer = NULL;
		sceKernelFreeMemBlock( vitaDisplayBlock );
		vitaDisplayBlock = -1;
		return false;
	}
	vitaDisplayFrameValid = true;
	sceDisplayWaitVblankStart();
	return true;
}

void VitaDiagScreen_Clear( void ) {
	if ( vitaFrameBuffer == NULL ) {
		return;
	}
	const int pixels = VITA_SCREEN_PITCH * VITA_SCREEN_HEIGHT;
	for ( int i = 0; i < pixels; ++i ) {
		vitaFrameBuffer[i] = VITA_COLOR_BLACK;
	}
	vitaCursorY = VITA_MARGIN_Y;
}

void VitaDiagScreen_DrawText( int x, int y, vitaDiagColor_t color, const char *text ) {
	if ( vitaFrameBuffer == NULL || text == NULL ) {
		return;
	}

	const uint32_t pixelColor = Vita_ColorForLine( color );
	int cursorX = x;
	int cursorY = y;
	for ( const char *scan = text; *scan != '\0'; ++scan ) {
		if ( *scan == '\n' ) {
			cursorY += VITA_LINE_ADVANCE;
			cursorX = x;
			continue;
		}
		if ( cursorX + VITA_CHAR_ADVANCE >= VITA_SCREEN_WIDTH - 4 ) {
			break;
		}
		if ( cursorY + VITA_FONT_HEIGHT * VITA_FONT_SCALE >= VITA_SCREEN_HEIGHT - 4 ) {
			break;
		}
		Vita_DrawChar( cursorX, cursorY, *scan, pixelColor );
		cursorX += VITA_CHAR_ADVANCE;
	}
}

void VitaDiagScreen_PrintLine( vitaDiagColor_t color, const char *text ) {
	if ( vitaFrameBuffer == NULL || text == NULL ) {
		return;
	}

	if ( vitaCursorY + VITA_FONT_HEIGHT * VITA_FONT_SCALE >= VITA_SCREEN_HEIGHT - VITA_MARGIN_Y ) {
		VitaDiagScreen_Clear();
	}

	VitaDiagScreen_DrawText( VITA_MARGIN_X, vitaCursorY, color, text );
	vitaCursorY += VITA_LINE_ADVANCE;
}

void VitaDiagScreen_Present( void ) {
	if ( !vitaDisplayFrameValid || vitaFrameBuffer == NULL ) {
		return;
	}

	// Re-submit the static framebuffer once per vblank. Besides keeping the
	// diagnostic screen alive on hardware, this prevents emulator watchdogs
	// from treating the intentionally static pre-render screen as a stalled
	// renderer.
	sceDisplaySetFrameBuf( &vitaDisplayFrame, SCE_DISPLAY_SETBUF_NEXTFRAME );
	sceDisplayWaitVblankStart();
}

void VitaDiagScreen_Finish( void ) {
	if ( vitaDisplayFrameValid ) {
		// Do not free or detach the backing store here. Vita3K currently treats
		// sceDisplaySetFrameBuf(NULL, ...) as a successful no-op and keeps the old
		// sce_frame.base pointer. Freeing this CDRAM block at that point leaves the
		// display thread pointing at the now-unmapped 0x60000000 region.
		//
		// Keep the diagnostic framebuffer alive across VitaGL initialization.
		// VitaGL's first successful swap installs its own framebuffer; the bootstrap
		// then calls VitaDiagScreen_ReleaseBacking() after that handoff.
		sceDisplayWaitVblankStart();
		vitaDisplayFrameValid = false;
	}

	// Stop all CPU-side drawing immediately, but intentionally retain
	// vitaDisplayFrame/vitaDisplayBlock until the renderer has presented.
	vitaFrameBuffer = NULL;
}

void VitaDiagScreen_ReleaseBacking( void ) {
	if ( vitaDisplayBlock < 0 ) {
		return;
	}

	// VitaGL queues its display callback asynchronously. Do not guess how many
	// vblanks it needs: wait until every queued display callback has completed.
	// On Vita3K sceGxmDisplayQueueFinish() blocks on display_queue.wait_empty();
	// on hardware it provides the same ownership barrier before freeing CDRAM.
	sceGxmDisplayQueueFinish();
	sceDisplayWaitVblankStart();

	sceKernelFreeMemBlock( vitaDisplayBlock );
	vitaDisplayBlock = -1;
	memset( &vitaDisplayFrame, 0, sizeof( vitaDisplayFrame ) );
}

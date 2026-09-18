#ifndef __VITA_DEBUG_SCREEN_H__
#define __VITA_DEBUG_SCREEN_H__

enum vitaDiagColor_t {
	VITA_DIAG_INFO = 0,
	VITA_DIAG_OK,
	VITA_DIAG_ERROR
};

bool VitaDiagScreen_Init( void );
void VitaDiagScreen_Clear( void );
void VitaDiagScreen_PrintLine( vitaDiagColor_t color, const char *text );
void VitaDiagScreen_Present( void );
void VitaDiagScreen_Finish( void );

#endif

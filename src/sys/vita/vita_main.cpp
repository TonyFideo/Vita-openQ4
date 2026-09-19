#include "../../idlib/precompiled.h"
#pragma hdrstop

#include "vita_public.h"
#include "vita_loading_hud.h"

#include <psp2/kernel/clib.h>

/*
================
main

Vita owns no desktop message pump. idCommonLocal::Init performs Sys_Init()
itself, then the normal idTech 4 frame loop drives session/game/rendering.
Keeping this entry point intentionally small makes the Vita executable follow
the same engine lifecycle as the desktop builds.
================
*/
int main( int argc, char **argv ) {
	sceClibPrintf( "[VOQ4] engine entry\n" );
	VitaLoadingHud_Init();
	VitaLoadingHud_SetEngineProgress( 0, 11, "Entrada del motor", false );

	const char **engineArgv = const_cast<const char **>( argv );
	if ( argc > 1 ) {
		common->Init( argc - 1, engineArgv + 1, NULL );
	} else {
		common->Init( 0, NULL, NULL );
	}

	VitaLoadingHud_SetEngineProgress( 11, 11, "Inicializacion completa", true );
	VitaLoadingHud_LogOk( "Entrando al bucle principal" );

	for ( ;; ) {
		common->Frame();
	}

	return 0;
}

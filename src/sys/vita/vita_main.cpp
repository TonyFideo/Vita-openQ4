#include "../../idlib/precompiled.h"
#pragma hdrstop

#include "vita_public.h"

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

	const char **engineArgv = const_cast<const char **>( argv );
	if ( argc > 1 ) {
		common->Init( argc - 1, engineArgv + 1, NULL );
	} else {
		common->Init( 0, NULL, NULL );
	}

	for ( ;; ) {
		common->Frame();
	}

	return 0;
}

#include "../../idlib/precompiled.h"
#include "../sys_local.h"

#include <psp2/kernel/clib.h>

namespace {

char vitaFatalError[4096] = {};

}

int Sys_GetDriveFreeSpace( const char *path ) {
	(void)path;
	// Match the conservative bring-up behaviour used by the Vita idTech4
	// reference port. Accurate free-space reporting can be wired to the final
	// filesystem backend without blocking engine startup.
	return 1000 * 1024;
}

void Sys_SetFatalError( const char *error ) {
	const char *safeError = error != NULL ? error : "";
	sceClibStrncpy( vitaFatalError, safeError, sizeof( vitaFatalError ) - 1 );
	vitaFatalError[sizeof( vitaFatalError ) - 1] = '\0';
}

void Sys_DoPreferences( void ) {
}

bool Sys_LoadOpenAL( void ) {
	// Hardware audio starts after the pre-render milestone. Returning false keeps
	// the core engine on its no-hardware path until the Vita OpenAL backend is
	// deliberately enabled.
	return false;
}

void Sys_FreeOpenAL( void ) {
}

void idSysLocal::OpenURL( const char *url, bool quit ) {
	Sys_Printf( "Vita: OpenURL unsupported during bring-up: %s\n", url != NULL ? url : "" );
	if ( quit ) {
		Sys_Quit();
	}
}

void idSysLocal::StartProcess( const char *exeName, bool quit ) {
	Sys_Printf( "Vita: StartProcess unsupported during monolithic bring-up: %s\n",
		exeName != NULL ? exeName : "" );
	if ( quit ) {
		Sys_Quit();
	}
}

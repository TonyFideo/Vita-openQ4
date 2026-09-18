#include "../../idlib/precompiled.h"

#include <psp2/kernel/clib.h>

#include <string.h>

idPort clientPort;
idPort serverPort;

namespace {

static bool Vita_AsciiIEquals( const char *left, const char *right ) {
	if ( left == NULL || right == NULL ) {
		return false;
	}
	while ( *left != '\0' && *right != '\0' ) {
		char a = *left++;
		char b = *right++;
		if ( a >= 'A' && a <= 'Z' ) {
			a = static_cast<char>( a - 'A' + 'a' );
		}
		if ( b >= 'A' && b <= 'Z' ) {
			b = static_cast<char>( b - 'A' + 'a' );
		}
		if ( a != b ) {
			return false;
		}
	}
	return *left == '\0' && *right == '\0';
}

}

void Sys_InitNetworking( void ) {
	Sys_Printf( "Vita networking: socket backend deferred; single-player bring-up mode\n" );
}

void Sys_ShutdownNetworking( void ) {
}

bool Sys_StringToNetAdr( const char *text, netadr_t *address, bool doDNSResolve ) {
	(void)doDNSResolve;
	if ( address == NULL ) {
		return false;
	}
	memset( address, 0, sizeof( *address ) );
	address->type = NA_BAD;

	if ( text == NULL || text[0] == '\0' ) {
		return false;
	}
	if ( Vita_AsciiIEquals( text, "localhost" ) ) {
		address->type = NA_LOOPBACK;
		address->ip[0] = 127;
		address->ip[1] = 0;
		address->ip[2] = 0;
		address->ip[3] = 1;
		return true;
	}

	return false;
}

const char *Sys_NetAdrToString( const netadr_t address ) {
	static char text[96];
	if ( address.type == NA_LOOPBACK ) {
		sceClibSnprintf( text, sizeof( text ), "localhost:%u",
			static_cast<unsigned int>( address.port ) );
	} else if ( address.type == NA_IP ) {
		sceClibSnprintf( text, sizeof( text ), "%u.%u.%u.%u:%u",
			static_cast<unsigned int>( address.ip[0] ),
			static_cast<unsigned int>( address.ip[1] ),
			static_cast<unsigned int>( address.ip[2] ),
			static_cast<unsigned int>( address.ip[3] ),
			static_cast<unsigned int>( address.port ) );
	} else {
		sceClibSnprintf( text, sizeof( text ), "unavailable" );
	}
	return text;
}

bool Sys_IsLANAddress( const netadr_t address ) {
	if ( address.type == NA_LOOPBACK ) {
		return true;
	}
	if ( address.type != NA_IP ) {
		return false;
	}

	return address.ip[0] == 10 ||
		address.ip[0] == 127 ||
		( address.ip[0] == 192 && address.ip[1] == 168 ) ||
		( address.ip[0] == 172 && address.ip[1] >= 16 && address.ip[1] <= 31 );
}

bool Sys_CompareNetAdrBase( const netadr_t a, const netadr_t b ) {
	if ( a.type != b.type ) {
		return false;
	}
	if ( a.type == NA_LOOPBACK ) {
		return true;
	}
	if ( a.type == NA_IP ) {
		return memcmp( a.ip, b.ip, sizeof( a.ip ) ) == 0;
	}
	if ( a.type == NA_IP6 ) {
		return a.scopeId == b.scopeId && memcmp( a.ip6, b.ip6, sizeof( a.ip6 ) ) == 0;
	}
	return false;
}

idPort::idPort() {
	memset( &bound_to, 0, sizeof( bound_to ) );
	netSocket = 0;
	netSocket6 = 0;
	platformData = NULL;
	packetsRead = 0;
	bytesRead = 0;
	packetsWritten = 0;
	bytesWritten = 0;
}

idPort::~idPort() {
	Close();
}

bool idPort::InitForPort( int portNumber ) {
	(void)portNumber;
	Close();
	return false;
}

void idPort::Close() {
	netSocket = 0;
	netSocket6 = 0;
	platformData = NULL;
	memset( &bound_to, 0, sizeof( bound_to ) );
}

bool idPort::GetPacket( netadr_t &from, void *data, int &size, int maxSize ) {
	(void)from;
	(void)data;
	(void)maxSize;
	size = 0;
	return false;
}

bool idPort::GetPacketBlocking( netadr_t &from, void *data, int &size, int maxSize, int timeout ) {
	(void)timeout;
	return GetPacket( from, data, size, maxSize );
}

void idPort::SendPacket( const netadr_t to, const void *data, int size ) {
	(void)to;
	(void)data;
	(void)size;
}

idTCP::idTCP() {
	memset( &address, 0, sizeof( address ) );
	fd = 0;
}

idTCP::~idTCP() {
	Close();
}

bool idTCP::Init( const char *host, int port ) {
	(void)host;
	(void)port;
	Close();
	return false;
}

void idTCP::Close() {
	fd = 0;
}

int idTCP::Read( void *data, int size ) {
	(void)data;
	(void)size;
	return -1;
}

int idTCP::Write( void *data, int size ) {
	(void)data;
	(void)size;
	return -1;
}

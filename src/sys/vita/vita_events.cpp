#include "../../idlib/precompiled.h"

#include <string.h>

namespace {

unsigned char vitaScanTable[256] = {};

}

void Sys_GenerateEvents( void ) {
}

sysEvent_t Sys_GetEvent( void ) {
	sysEvent_t event;
	memset( &event, 0, sizeof( event ) );
	event.evType = SE_NONE;
	return event;
}

void Sys_ClearEvents( void ) {
}

void Sys_InitInput( void ) {
}

void Sys_ShutdownInput( void ) {
}

void Sys_ClearInputEvents( void ) {
}

void Sys_InitScanTable( void ) {
	memset( vitaScanTable, 0, sizeof( vitaScanTable ) );
}

const unsigned char *Sys_GetScanTable( void ) {
	return vitaScanTable;
}

unsigned char Sys_GetConsoleKey( bool shifted ) {
	(void)shifted;
	return '`';
}

unsigned char Sys_MapCharForKey( int key ) {
	return key >= 0 && key <= 255 ? static_cast<unsigned char>( key ) : 0;
}

int Sys_PollKeyboardInputEvents( void ) {
	return 0;
}

int Sys_ReturnKeyboardInputEvent( const int n, int &ch, bool &state ) {
	(void)n;
	ch = 0;
	state = false;
	return 0;
}

void Sys_EndKeyboardInputEvents( void ) {
}

int Sys_PollMouseInputEvents( void ) {
	return 0;
}

int Sys_ReturnMouseInputEvent( const int n, int &action, int &value ) {
	(void)n;
	action = 0;
	value = 0;
	return 0;
}

void Sys_EndMouseInputEvents( void ) {
}

int Sys_PollJoystickInputEvents( void ) {
	return 0;
}

int Sys_ReturnJoystickInputEvent( const int n, int &axis, int &value ) {
	(void)n;
	axis = 0;
	value = 0;
	return 0;
}

void Sys_EndJoystickInputEvents( void ) {
}

bool Sys_GetJoystickAxisState( int axis, int &value ) {
	(void)axis;
	value = 0;
	return false;
}

bool Sys_SetJoystickRumble( float lowFrequency, float highFrequency, int durationMsec ) {
	(void)lowFrequency;
	(void)highFrequency;
	(void)durationMsec;
	return false;
}

void Sys_GrabMouseCursor( bool grabIt ) {
	(void)grabIt;
}

void Sys_ShowWindow( bool show ) {
	(void)show;
}

bool Sys_IsWindowVisible( void ) {
	return true;
}

void Sys_ShowConsole( int visLevel, bool quitOnClose ) {
	(void)visLevel;
	(void)quitOnClose;
}

void Sys_ShowSplash( void ) {
}

void Sys_DestroySplash( void ) {
}

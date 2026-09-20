#include "../../idlib/precompiled.h"

#include <psp2/ctrl.h>

#include <math.h>
#include <string.h>

namespace {

static const int VITA_EVENT_QUEUE_SIZE = 128;
static const int VITA_KEY_QUEUE_SIZE = 128;
static const int VITA_PRIMARY_EXTERNAL_PORT = 1;

struct vitaKeyEvent_t {
	int key;
	bool down;
};

struct vitaJoystickEvent_t {
	int axis;
	int value;
};

unsigned char vitaScanTable[256] = {};

sysEvent_t vitaEventQueue[VITA_EVENT_QUEUE_SIZE] = {};
int vitaEventHead = 0;
int vitaEventTail = 0;

vitaKeyEvent_t vitaKeyQueue[VITA_KEY_QUEUE_SIZE] = {};
int vitaKeyHead = 0;
int vitaKeyTail = 0;
vitaKeyEvent_t vitaPolledKeys[VITA_KEY_QUEUE_SIZE] = {};
int vitaPolledKeyCount = 0;

vitaJoystickEvent_t vitaPolledJoystick[MAX_JOYSTICK_AXIS] = {};
int vitaJoystickAxisState[MAX_JOYSTICK_AXIS] = {};

bool vitaLogicalKeyDown[K_LAST_KEY] = {};
bool vitaInputReady = false;
bool vitaUsingExternalPad = false;
int vitaPrimaryPadPort = 0;

bool vitaRumbleActive = false;
int vitaRumbleUntilMsec = 0;

idCVar in_joystick( "in_joystick", "1", CVAR_SYSTEM | CVAR_ARCHIVE | CVAR_BOOL,
	"enable Vita controller input" );
idCVar in_joystickDeadZone( "in_joystickDeadZone", "0.18", CVAR_SYSTEM | CVAR_ARCHIVE | CVAR_FLOAT,
	"controller stick radial dead zone", 0.0f, 0.95f );
idCVar in_joystickTriggerThreshold( "in_joystickTriggerThreshold", "0.35", CVAR_SYSTEM | CVAR_ARCHIVE | CVAR_FLOAT,
	"external controller trigger button threshold", 0.0f, 1.0f );
idCVar in_joystickLookSensitivity( "in_joystickLookSensitivity", "0.75", CVAR_SYSTEM | CVAR_ARCHIVE | CVAR_FLOAT,
	"controller look sensitivity scale", 0.1f, 4.0f );
idCVar in_joystickLookCurve( "in_joystickLookCurve", "1.35", CVAR_SYSTEM | CVAR_ARCHIVE | CVAR_FLOAT,
	"controller look response curve", 1.0f, 3.0f );
idCVar in_joystickMoveCurve( "in_joystickMoveCurve", "1.0", CVAR_SYSTEM | CVAR_ARCHIVE | CVAR_FLOAT,
	"controller movement response curve", 1.0f, 3.0f );
idCVar in_joystickInvertLook( "in_joystickInvertLook", "0", CVAR_SYSTEM | CVAR_ARCHIVE | CVAR_BOOL,
	"invert controller look pitch" );
idCVar in_joystickSouthpaw( "in_joystickSouthpaw", "0", CVAR_SYSTEM | CVAR_ARCHIVE | CVAR_BOOL,
	"swap controller movement and look sticks" );
idCVar in_joystickRumble( "in_joystickRumble", "1", CVAR_SYSTEM | CVAR_ARCHIVE | CVAR_BOOL,
	"enable rumble on paired external controllers" );
idCVar in_joystickRumbleScale( "in_joystickRumbleScale", "1.0", CVAR_SYSTEM | CVAR_ARCHIVE | CVAR_FLOAT,
	"external controller rumble strength scale", 0.0f, 2.0f );

static float Vita_ClampFloat( float value, float minimum, float maximum ) {
	if ( value < minimum ) {
		return minimum;
	}
	if ( value > maximum ) {
		return maximum;
	}
	return value;
}

static int Vita_ClampAxisValue( int value ) {
	if ( value < -127 ) {
		return -127;
	}
	if ( value > 127 ) {
		return 127;
	}
	return value;
}

static float Vita_NormalizeRawAxis( unsigned char value ) {
	const int centered = static_cast<int>( value ) - 128;
	if ( centered < 0 ) {
		return static_cast<float>( centered ) / 128.0f;
	}
	return static_cast<float>( centered ) / 127.0f;
}

static void Vita_NormalizeStick( unsigned char rawX, unsigned char rawY, float deadZone, float curve, int &outX, int &outY ) {
	const float x = Vita_NormalizeRawAxis( rawX );
	const float y = Vita_NormalizeRawAxis( rawY );
	const float length = sqrtf( x * x + y * y );
	const float clampedDeadZone = Vita_ClampFloat( deadZone, 0.0f, 0.95f );

	if ( length <= clampedDeadZone || length <= 0.00001f ) {
		outX = 0;
		outY = 0;
		return;
	}

	const float normalizedLength = length > 1.0f ? 1.0f : length;
	float adjustedLength = ( normalizedLength - clampedDeadZone ) / ( 1.0f - clampedDeadZone );
	adjustedLength = Vita_ClampFloat( adjustedLength, 0.0f, 1.0f );

	const float responseCurve = Vita_ClampFloat( curve, 1.0f, 3.0f );
	if ( responseCurve != 1.0f && adjustedLength > 0.0f ) {
		adjustedLength = powf( adjustedLength, responseCurve );
	}

	const float unitScale = adjustedLength / length;
	outX = Vita_ClampAxisValue( static_cast<int>( x * unitScale * 127.0f ) );
	outY = Vita_ClampAxisValue( static_cast<int>( y * unitScale * 127.0f ) );
}

static void Vita_ClearEventQueueLocked( void ) {
	vitaEventHead = 0;
	vitaEventTail = 0;
	memset( vitaEventQueue, 0, sizeof( vitaEventQueue ) );
}

static void Vita_ClearKeyQueueLocked( void ) {
	vitaKeyHead = 0;
	vitaKeyTail = 0;
	vitaPolledKeyCount = 0;
	memset( vitaKeyQueue, 0, sizeof( vitaKeyQueue ) );
	memset( vitaPolledKeys, 0, sizeof( vitaPolledKeys ) );
}

static void Vita_QueueSystemKeyLocked( int key, bool down ) {
	const int next = ( vitaEventHead + 1 ) % VITA_EVENT_QUEUE_SIZE;
	if ( next == vitaEventTail ) {
		vitaEventTail = ( vitaEventTail + 1 ) % VITA_EVENT_QUEUE_SIZE;
	}

	sysEvent_t &event = vitaEventQueue[vitaEventHead];
	memset( &event, 0, sizeof( event ) );
	event.evType = SE_KEY;
	event.evValue = key;
	event.evValue2 = down ? 1 : 0;
	vitaEventHead = next;
}

static void Vita_QueueUsercmdKeyLocked( int key, bool down ) {
	const int next = ( vitaKeyHead + 1 ) % VITA_KEY_QUEUE_SIZE;
	if ( next == vitaKeyTail ) {
		vitaKeyTail = ( vitaKeyTail + 1 ) % VITA_KEY_QUEUE_SIZE;
	}

	vitaKeyQueue[vitaKeyHead].key = key;
	vitaKeyQueue[vitaKeyHead].down = down;
	vitaKeyHead = next;
}

static void Vita_SetLogicalKey( bool *logicalKeys, int key, bool down ) {
	if ( key > 0 && key < K_LAST_KEY ) {
		logicalKeys[key] = down;
	}
}

static bool Vita_ReadPrimaryPad( SceCtrlData &pad, bool &external, int &port ) {
	memset( &pad, 0, sizeof( pad ) );

	// Match the SDL-vitaGL strategy: prefer the first paired external pad on
	// PSTV/paired-controller setups, then fall back to the Vita's built-in pad.
	int result = sceCtrlPeekBufferPositiveExt2( VITA_PRIMARY_EXTERNAL_PORT, &pad, 1 );
	if ( result > 0 ) {
		external = true;
		port = VITA_PRIMARY_EXTERNAL_PORT;
		return true;
	}

	memset( &pad, 0, sizeof( pad ) );
	result = sceCtrlPeekBufferPositive( 0, &pad, 1 );
	if ( result > 0 ) {
		external = false;
		port = 0;
		return true;
	}

	return false;
}

static void Vita_BuildLogicalKeys( const SceCtrlData &pad, bool external, bool *logicalKeys ) {
	memset( logicalKeys, 0, sizeof( bool ) * K_LAST_KEY );

	if ( !in_joystick.GetBool() ) {
		return;
	}

	const unsigned int buttons = pad.buttons;

	Vita_SetLogicalKey( logicalKeys, K_JOY3, ( buttons & SCE_CTRL_CROSS ) != 0 );
	Vita_SetLogicalKey( logicalKeys, K_JOY4, ( buttons & SCE_CTRL_CIRCLE ) != 0 );
	Vita_SetLogicalKey( logicalKeys, K_JOY5, ( buttons & SCE_CTRL_TRIANGLE ) != 0 );
	Vita_SetLogicalKey( logicalKeys, K_JOY6, ( buttons & SCE_CTRL_SQUARE ) != 0 );
	Vita_SetLogicalKey( logicalKeys, K_JOY7, ( buttons & SCE_CTRL_START ) != 0 );
	Vita_SetLogicalKey( logicalKeys, K_JOY8, ( buttons & SCE_CTRL_SELECT ) != 0 );
	Vita_SetLogicalKey( logicalKeys, K_JOY9, ( buttons & SCE_CTRL_UP ) != 0 );
	Vita_SetLogicalKey( logicalKeys, K_JOY10, ( buttons & SCE_CTRL_DOWN ) != 0 );
	Vita_SetLogicalKey( logicalKeys, K_JOY11, ( buttons & SCE_CTRL_RIGHT ) != 0 );
	Vita_SetLogicalKey( logicalKeys, K_JOY12, ( buttons & SCE_CTRL_LEFT ) != 0 );

	if ( external ) {
		Vita_SetLogicalKey( logicalKeys, K_JOY1, ( buttons & SCE_CTRL_L1 ) != 0 );
		Vita_SetLogicalKey( logicalKeys, K_JOY2, ( buttons & SCE_CTRL_R1 ) != 0 );
		Vita_SetLogicalKey( logicalKeys, K_JOY13, ( buttons & SCE_CTRL_L3 ) != 0 );
		Vita_SetLogicalKey( logicalKeys, K_JOY14, ( buttons & SCE_CTRL_R3 ) != 0 );

		const int threshold = static_cast<int>(
			Vita_ClampFloat( in_joystickTriggerThreshold.GetFloat(), 0.0f, 1.0f ) * 255.0f );
		const bool rightTriggerDown = ( buttons & SCE_CTRL_R2 ) != 0 || static_cast<int>( pad.rt ) >= threshold;
		const bool leftTriggerDown = ( buttons & SCE_CTRL_L2 ) != 0 || static_cast<int>( pad.lt ) >= threshold;
		Vita_SetLogicalKey( logicalKeys, K_JOY15, rightTriggerDown );
		Vita_SetLogicalKey( logicalKeys, K_JOY16, leftTriggerDown );
	} else {
		Vita_SetLogicalKey( logicalKeys, K_JOY1, ( buttons & SCE_CTRL_LTRIGGER ) != 0 );
		Vita_SetLogicalKey( logicalKeys, K_JOY2, ( buttons & SCE_CTRL_RTRIGGER ) != 0 );
	}
}

static void Vita_UpdateAxesLocked( const SceCtrlData &pad ) {
	if ( !in_joystick.GetBool() ) {
		memset( vitaJoystickAxisState, 0, sizeof( vitaJoystickAxisState ) );
		return;
	}

	const bool southpaw = in_joystickSouthpaw.GetBool();
	const unsigned char moveXRaw = southpaw ? pad.rx : pad.lx;
	const unsigned char moveYRaw = southpaw ? pad.ry : pad.ly;
	const unsigned char lookXRaw = southpaw ? pad.lx : pad.rx;
	const unsigned char lookYRaw = southpaw ? pad.ly : pad.ry;

	int moveX = 0;
	int moveY = 0;
	int lookX = 0;
	int lookY = 0;
	const float deadZone = in_joystickDeadZone.GetFloat();

	Vita_NormalizeStick( moveXRaw, moveYRaw, deadZone, in_joystickMoveCurve.GetFloat(), moveX, moveY );
	Vita_NormalizeStick( lookXRaw, lookYRaw, deadZone, in_joystickLookCurve.GetFloat(), lookX, lookY );

	// SceCtrl Y grows downward. idTech expects positive movement to mean forward,
	// while positive look Y means look down, matching SDL gamepad convention.
	moveY = -moveY;
	if ( in_joystickInvertLook.GetBool() ) {
		lookY = -lookY;
	}

	vitaJoystickAxisState[AXIS_SIDE] = lookX;
	vitaJoystickAxisState[AXIS_FORWARD] = lookY;
	vitaJoystickAxisState[AXIS_UP] = 0;
	vitaJoystickAxisState[AXIS_ROLL] = 127; // dedicated right-stick look axes are available
	vitaJoystickAxisState[AXIS_YAW] = moveX;
	vitaJoystickAxisState[AXIS_PITCH] = moveY;
}

static void Vita_StopRumbleLocked( void ) {
	if ( vitaRumbleActive && vitaUsingExternalPad && vitaPrimaryPadPort > 0 ) {
		SceCtrlActuator actuator;
		memset( &actuator, 0, sizeof( actuator ) );
		(void)sceCtrlSetActuator( vitaPrimaryPadPort, &actuator );
	}
	vitaRumbleActive = false;
	vitaRumbleUntilMsec = 0;
}

static void Vita_UpdateRumbleLocked( int nowMsec ) {
	if ( vitaRumbleActive &&
			( !vitaUsingExternalPad || !in_joystickRumble.GetBool() || nowMsec >= vitaRumbleUntilMsec ) ) {
		Vita_StopRumbleLocked();
	}
}

static void Vita_ApplyPadStateLocked( const SceCtrlData &pad, bool external, int port, bool queueTransitions ) {
	bool logicalKeys[K_LAST_KEY];
	Vita_BuildLogicalKeys( pad, external, logicalKeys );

	if ( queueTransitions ) {
		for ( int key = 1; key < K_LAST_KEY; ++key ) {
			if ( logicalKeys[key] == vitaLogicalKeyDown[key] ) {
				continue;
			}
			Vita_QueueSystemKeyLocked( key, logicalKeys[key] );
			Vita_QueueUsercmdKeyLocked( key, logicalKeys[key] );
		}
	}

	memcpy( vitaLogicalKeyDown, logicalKeys, sizeof( vitaLogicalKeyDown ) );
	vitaUsingExternalPad = external;
	vitaPrimaryPadPort = port;
	Vita_UpdateAxesLocked( pad );
	Vita_UpdateRumbleLocked( Sys_Milliseconds() );
}

static void Vita_EnsureInputInitialized( void ) {
	if ( vitaInputReady ) {
		return;
	}

	Sys_EnterCriticalSection( CRITICAL_SECTION_ONE );
	if ( !vitaInputReady ) {
		const int modeResult = sceCtrlSetSamplingMode( SCE_CTRL_MODE_ANALOG_WIDE );
		const int extModeResult = sceCtrlSetSamplingModeExt( SCE_CTRL_MODE_ANALOG_WIDE );
		memset( vitaLogicalKeyDown, 0, sizeof( vitaLogicalKeyDown ) );
		memset( vitaJoystickAxisState, 0, sizeof( vitaJoystickAxisState ) );
		Vita_ClearEventQueueLocked();
		Vita_ClearKeyQueueLocked();
		vitaInputReady = true;
		common->Printf( "Vita input: SceCtrl initialized (analog-wide=%d external-analog-wide=%d)\n",
			modeResult, extModeResult );
	}
	Sys_LeaveCriticalSection( CRITICAL_SECTION_ONE );
}

static void Vita_PumpInput( bool queueTransitions ) {
	Vita_EnsureInputInitialized();

	SceCtrlData pad;
	bool external = false;
	int port = 0;
	if ( !Vita_ReadPrimaryPad( pad, external, port ) ) {
		memset( &pad, 0, sizeof( pad ) );
		pad.lx = pad.ly = pad.rx = pad.ry = 128;
	}

	Sys_EnterCriticalSection( CRITICAL_SECTION_ONE );
	Vita_ApplyPadStateLocked( pad, external, port, queueTransitions );
	Sys_LeaveCriticalSection( CRITICAL_SECTION_ONE );
}

}

void Sys_GenerateEvents( void ) {
	Vita_PumpInput( true );
}

sysEvent_t Sys_GetEvent( void ) {
	Vita_EnsureInputInitialized();

	sysEvent_t event;
	memset( &event, 0, sizeof( event ) );
	event.evType = SE_NONE;

	Sys_EnterCriticalSection( CRITICAL_SECTION_ONE );
	if ( vitaEventTail != vitaEventHead ) {
		event = vitaEventQueue[vitaEventTail];
		memset( &vitaEventQueue[vitaEventTail], 0, sizeof( sysEvent_t ) );
		vitaEventTail = ( vitaEventTail + 1 ) % VITA_EVENT_QUEUE_SIZE;
	}
	Sys_LeaveCriticalSection( CRITICAL_SECTION_ONE );

	return event;
}

void Sys_ClearEvents( void ) {
	Vita_EnsureInputInitialized();
	Sys_EnterCriticalSection( CRITICAL_SECTION_ONE );
	Vita_ClearEventQueueLocked();
	Sys_LeaveCriticalSection( CRITICAL_SECTION_ONE );
}

void Sys_InitInput( void ) {
	Vita_EnsureInputInitialized();
}

void Sys_ShutdownInput( void ) {
	if ( !vitaInputReady ) {
		return;
	}

	Sys_EnterCriticalSection( CRITICAL_SECTION_ONE );
	Vita_StopRumbleLocked();
	Vita_ClearEventQueueLocked();
	Vita_ClearKeyQueueLocked();
	memset( vitaLogicalKeyDown, 0, sizeof( vitaLogicalKeyDown ) );
	memset( vitaJoystickAxisState, 0, sizeof( vitaJoystickAxisState ) );
	vitaInputReady = false;
	Sys_LeaveCriticalSection( CRITICAL_SECTION_ONE );
}

void Sys_ClearInputEvents( void ) {
	Vita_EnsureInputInitialized();

	// Clear queued transitions and synchronize to the physical state without
	// generating a new press. This prevents the button that dismissed a loading
	// gate from leaking into the first gameplay tic.
	Sys_EnterCriticalSection( CRITICAL_SECTION_ONE );
	Vita_ClearKeyQueueLocked();
	Vita_ClearEventQueueLocked();
	Sys_LeaveCriticalSection( CRITICAL_SECTION_ONE );
	Vita_PumpInput( false );
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
	Vita_PumpInput( true );

	Sys_EnterCriticalSection( CRITICAL_SECTION_ONE );
	vitaPolledKeyCount = 0;
	while ( vitaKeyTail != vitaKeyHead && vitaPolledKeyCount < VITA_KEY_QUEUE_SIZE ) {
		vitaPolledKeys[vitaPolledKeyCount++] = vitaKeyQueue[vitaKeyTail];
		vitaKeyTail = ( vitaKeyTail + 1 ) % VITA_KEY_QUEUE_SIZE;
	}
	Sys_LeaveCriticalSection( CRITICAL_SECTION_ONE );

	return vitaPolledKeyCount;
}

int Sys_ReturnKeyboardInputEvent( const int n, int &ch, bool &state ) {
	if ( n < 0 || n >= vitaPolledKeyCount ) {
		ch = 0;
		state = false;
		return 0;
	}

	ch = vitaPolledKeys[n].key;
	state = vitaPolledKeys[n].down;
	return ( ch > 0 && ch < K_LAST_KEY ) ? 1 : 0;
}

void Sys_EndKeyboardInputEvents( void ) {
	vitaPolledKeyCount = 0;
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
	Vita_PumpInput( true );

	Sys_EnterCriticalSection( CRITICAL_SECTION_ONE );
	for ( int axis = 0; axis < MAX_JOYSTICK_AXIS; ++axis ) {
		vitaPolledJoystick[axis].axis = axis;
		vitaPolledJoystick[axis].value = vitaJoystickAxisState[axis];
	}
	Sys_LeaveCriticalSection( CRITICAL_SECTION_ONE );

	return MAX_JOYSTICK_AXIS;
}

int Sys_ReturnJoystickInputEvent( const int n, int &axis, int &value ) {
	if ( n < 0 || n >= MAX_JOYSTICK_AXIS ) {
		axis = 0;
		value = 0;
		return 0;
	}

	axis = vitaPolledJoystick[n].axis;
	value = vitaPolledJoystick[n].value;
	return 1;
}

void Sys_EndJoystickInputEvents( void ) {
}

bool Sys_GetJoystickAxisState( int axis, int &value ) {
	if ( !in_joystick.GetBool() || axis < 0 || axis >= MAX_JOYSTICK_AXIS ) {
		value = 0;
		return false;
	}

	Vita_PumpInput( true );
	Sys_EnterCriticalSection( CRITICAL_SECTION_ONE );
	value = vitaJoystickAxisState[axis];
	Sys_LeaveCriticalSection( CRITICAL_SECTION_ONE );
	return true;
}

bool Sys_SetJoystickRumble( float lowFrequency, float highFrequency, int durationMsec ) {
	Vita_EnsureInputInitialized();

	Sys_EnterCriticalSection( CRITICAL_SECTION_ONE );
	if ( !vitaUsingExternalPad || vitaPrimaryPadPort <= 0 || !in_joystickRumble.GetBool() || durationMsec <= 0 ) {
		Vita_StopRumbleLocked();
		Sys_LeaveCriticalSection( CRITICAL_SECTION_ONE );
		return false;
	}

	const float scale = Vita_ClampFloat( in_joystickRumbleScale.GetFloat(), 0.0f, 2.0f );
	const int large = static_cast<int>( Vita_ClampFloat( lowFrequency * scale, 0.0f, 1.0f ) * 255.0f );
	const int small = static_cast<int>( Vita_ClampFloat( highFrequency * scale, 0.0f, 1.0f ) * 255.0f );

	SceCtrlActuator actuator;
	memset( &actuator, 0, sizeof( actuator ) );
	actuator.large = static_cast<unsigned char>( large );
	actuator.small = static_cast<unsigned char>( small );

	if ( sceCtrlSetActuator( vitaPrimaryPadPort, &actuator ) < 0 ) {
		vitaRumbleActive = false;
		vitaRumbleUntilMsec = 0;
		Sys_LeaveCriticalSection( CRITICAL_SECTION_ONE );
		return false;
	}

	vitaRumbleActive = large != 0 || small != 0;
	vitaRumbleUntilMsec = vitaRumbleActive ? Sys_Milliseconds() + durationMsec : 0;
	Sys_LeaveCriticalSection( CRITICAL_SECTION_ONE );
	return true;
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

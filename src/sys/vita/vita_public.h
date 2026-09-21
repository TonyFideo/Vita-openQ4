#ifndef __SYS_VITA_PUBLIC_H__
#define __SYS_VITA_PUBLIC_H__

#define VITA_OPENQ4_WRITABLE_ROOT "ux0:data/Vita-OpenQ4"
#define VITA_OPENQ4_DATA_ROOT_UX0 "ux0:data/Vita-OpenQ4"
#define VITA_OPENQ4_DATA_ROOT_UMA0 "uma0:data/Vita-OpenQ4"
#define VITA_OPENQ4_DATA_ROOT_UR0 "ur0:data/Vita-OpenQ4"

void Vita_InitThreads( void );
void Vita_ShutdownThreads( void );
bool Vita_StartAsyncTimer( void );
void Vita_StopAsyncTimer( void );

#endif

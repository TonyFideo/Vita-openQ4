#ifndef __VITA_LOADING_HUD_H__
#define __VITA_LOADING_HUD_H__

enum vitaLoadingStage_t {
	VITA_LOAD_ENGINE = 0,
	VITA_LOAD_Q4_PAKS,
	VITA_LOAD_OPENQ4_PAKS,
	VITA_LOAD_MATERIALS,
	VITA_LOAD_IMAGES,
	VITA_LOAD_GUI,
	VITA_LOAD_SOUND,
	VITA_LOAD_SESSION,
	VITA_LOAD_STAGE_COUNT
};

enum vitaLoadingLogColor_t {
	VITA_LOAD_LOG_INFO = 0,
	VITA_LOAD_LOG_OK,
	VITA_LOAD_LOG_WARN,
	VITA_LOAD_LOG_ERROR
};

static const int VITA_LOADING_HUD_MAX_LOG_LINES = 10;

struct vitaLoadingStageSnapshot_t {
	char label[24];
	char detail[72];
	int done;
	int total;
};

struct vitaLoadingLogSnapshot_t {
	vitaLoadingLogColor_t color;
	char text[128];
};

struct vitaLoadingHudSnapshot_t {
	bool active;
	bool rendererHandoffComplete;
	char buildLabel[96];
	char status[96];
	char lastStage[96];
	char lastAsset[128];
	char lastPak[128];
	vitaLoadingStageSnapshot_t stages[VITA_LOAD_STAGE_COUNT];
	int logCount;
	vitaLoadingLogSnapshot_t logs[VITA_LOADING_HUD_MAX_LOG_LINES];
};

void VitaLoadingHud_Init( void );
void VitaLoadingHud_Shutdown( void );

void VitaLoadingHud_SetCheckpoint( const char *text );
void VitaLoadingHud_SetEngineProgress( int done, int total, const char *detail, bool completed );
void VitaLoadingHud_SetStageProgress( vitaLoadingStage_t stage, int done, int total, const char *detail );
void VitaLoadingHud_AddStageTotal( vitaLoadingStage_t stage, int amount );
void VitaLoadingHud_AdvanceStage( vitaLoadingStage_t stage, int amount, const char *detail );

void VitaLoadingHud_PakDirectoryDiscovered( const char *gameDir, int count );
void VitaLoadingHud_PakProcessed( const char *gameDir, const char *pakName, bool loaded, bool skipped );
void VitaLoadingHud_IndexAsset( const char *relativePath );
void VitaLoadingHud_SetAssetContext( const char *relativePath, const char *pakPath );
void VitaLoadingHud_AssetLoaded( const char *relativePath, const char *pakPath, bool firstLoad );
void VitaLoadingHud_AssetError( const char *relativePath, const char *pakPath, const char *reason );

void VitaLoadingHud_LogInfo( const char *fmt, ... );
void VitaLoadingHud_LogOk( const char *fmt, ... );
void VitaLoadingHud_LogWarn( const char *fmt, ... );
void VitaLoadingHud_LogError( const char *fmt, ... );

void VitaLoadingHud_TickNative( bool force );
void VitaLoadingHud_RendererInitialized( void );
void VitaLoadingHud_BeginRendererHandoff( void );
void VitaLoadingHud_EndRendererHandoff( void );
bool VitaLoadingHud_RendererHandoffComplete( void );

void VitaLoadingHud_GetSnapshot( vitaLoadingHudSnapshot_t *snapshot );

#endif

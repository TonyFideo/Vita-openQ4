// SPDX-License-Identifier: GPL-3.0-or-later
// Silent backend for the non-OpenAL/non-XAudio2 bring-up configuration.
#ifndef OPENQ4_SOUND_STUB_H
#define OPENQ4_SOUND_STUB_H

// These are logical, empty samples, not decoded audio. Keep resource lifetime
// and reference bookkeeping valid without allocating PCM or driver buffers.
// Duration/amplitude are deliberately zero: this backend is for renderer
// bring-up, not validation of dialogue, cinematic timing, or sound-driven FX.
class idSoundSample {
public:
    idSoundSample() : loaded( false ), neverPurge( false ),
        levelLoadReferenced( false ), lastPlayedTime( 0 ) {}
    virtual ~idSoundSample() = default;

    virtual void LoadResource() { MakeDefault(); }
    void SetName( const char* value ) { name = value != NULL ? value : ""; }
    const char* GetName() const { return name.c_str(); }
    ID_TIME_T GetTimestamp() const { return FILE_NOT_FOUND_TIMESTAMP; }
    void MakeDefault() { loaded = true; }
    void FreeData() { loaded = false; }
    int LengthInMsec() const { return 0; }
    // A valid placeholder format prevents division by zero in generic callers.
    int SampleRate() const { return 44100; }
    int NumSamples() const { return 0; }
    int NumChannels() const { return 1; }
    int BufferSize() const { return 0; }
    const byte* GetNonCacheData() const { return NULL; }
    bool IsCompressed() const { return false; }
    bool IsDefault() const { return true; }
    bool IsLoaded() const { return loaded; }
    void SetNeverPurge() { neverPurge = true; }
    bool GetNeverPurge() const { return neverPurge; }
    void SetLevelLoadReferenced() { levelLoadReferenced = true; }
    void ResetLevelLoadReferenced() { levelLoadReferenced = false; }
    bool GetLevelLoadReferenced() const { return levelLoadReferenced; }
    int GetLastPlayedTime() const { return lastPlayedTime; }
    void SetLastPlayedTime( int value ) { lastPlayedTime = value; }
    float GetAmplitude( int /*timeMS*/ ) const { return 0.0f; }

private:
    idStr name;
    bool loaded;
    bool neverPurge;
    bool levelLoadReferenced;
    int lastPlayedTime;
};

// The generic channel code still needs the voice interface at compile time.
// The hardware below never allocates one; direct calls fail closed as well.
class idSoundVoice : public idSoundVoice_Base {
public:
    void Create( const idSoundSample*, const idSoundSample* ) {}
    bool Start( int /*offsetMS*/, int /*flags*/ ) { return false; }
    void Stop() {}
    void Pause() {}
    bool UnPause() { return false; }
    bool Update() { return false; }
    float GetAmplitude() { return 0.0f; }
    uint32 GetSampleRate() const { return 0; }
    bool IsPlaying() const { return false; }
    bool GetPlaybackLatencyMS( float& offsetMS, float& latencyMS ) const override {
        offsetMS = latencyMS = 0.0f;
        return false;
    }
};

class idSoundHardware {
public:
    void Init() {
        idLib::Printf( "Sound: silent backend; audio output is disabled for bring-up.\n" );
    }
    // Both generic device accessors use this legacy name without OpenAL.
    void* GetIXAudio2() const { return NULL; }
    void Shutdown() {}
    void BeginDeferredUpdates() {}
    void EndDeferredUpdates() {}
    void Update() {}
    idSoundVoice* AllocateVoice( const idSoundSample*, const idSoundSample* ) {
        return NULL;
    }
    void FreeVoice( idSoundVoice* /*voice*/ ) {}
    int ListPlayingVoices() const {
        idLib::Printf( "0 playing voices (silent backend)\n" );
        return 0;
    }
    int GetNumZombieVoices() const { return 0; }
    int GetNumFreeVoices() const { return 0; }
    bool HasEFX() const { return false; }
    bool HasEFXFilters() const { return false; }
    // Deliberately disabled, not a recoverable device failure. Do not cause
    // snd_system's periodic hardware reinitialization loop to run forever.
    bool InitFailed() const { return false; }
};

#endif // OPENQ4_SOUND_STUB_H

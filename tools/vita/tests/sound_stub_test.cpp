// Host-side contract tests. Real engine declarations are tested by the ARM
// sound-object gate in build_engine.py, not by these lightweight substitutes.
#include <cassert>
#include <cstdint>
#include <string>
using byte = unsigned char;
using uint32 = std::uint32_t;
using ID_TIME_T = std::int64_t;
constexpr ID_TIME_T FILE_NOT_FOUND_TIMESTAMP = -1;
class idStr {
    std::string value;
public:
    idStr& operator=(const char* text) { value = text; return *this; }
    const char* c_str() const { return value.c_str(); }
};
class idLib {
public:
    static void Printf(const char*, ...) {}
};
class idSoundVoice_Base {
public:
    virtual bool GetPlaybackLatencyMS(float&, float&) const { return false; }
};
#include "../../../src/sound/stub/SoundStub.h"

int main() {
    idSoundSample sample;
    assert(!sample.IsLoaded());
    assert(!sample.GetNeverPurge());
    assert(!sample.GetLevelLoadReferenced());
    assert(sample.GetLastPlayedTime() == 0);
    sample.SetName("sound/test");
    assert(std::string(sample.GetName()) == "sound/test");
    sample.LoadResource();
    assert(sample.IsLoaded() && sample.IsDefault());
    assert(sample.GetTimestamp() == FILE_NOT_FOUND_TIMESTAMP);
    assert(sample.BufferSize() == 0 && sample.GetNonCacheData() == nullptr);
    assert(sample.NumSamples() == 0 && sample.LengthInMsec() == 0);
    assert(sample.SampleRate() > 0 && sample.NumChannels() == 1);
    assert(!sample.IsCompressed() && sample.GetAmplitude(10) == 0.0f);
    sample.SetNeverPurge();
    sample.SetLevelLoadReferenced();
    sample.SetLastPlayedTime(42);
    for (int i = 0; i < 100; ++i) {
        sample.FreeData();
        assert(!sample.IsLoaded());
        assert(sample.GetNeverPurge() && sample.GetLastPlayedTime() == 42);
        sample.LoadResource();
        assert(sample.IsLoaded());
    }
    sample.ResetLevelLoadReferenced();
    assert(!sample.GetLevelLoadReferenced());
    sample.SetName(nullptr);
    assert(std::string(sample.GetName()).empty());
    idSoundHardware hardware;
    for (int i = 0; i < 10; ++i) {
        hardware.Init();
        assert(!hardware.InitFailed());
        assert(hardware.AllocateVoice(&sample, &sample) == nullptr);
        assert(hardware.AllocateVoice(nullptr, nullptr) == nullptr);
        hardware.FreeVoice(nullptr);
        hardware.BeginDeferredUpdates();
        hardware.Update();
        hardware.EndDeferredUpdates();
        assert(hardware.GetNumFreeVoices() == 0);
        assert(hardware.GetNumZombieVoices() == 0);
        assert(hardware.ListPlayingVoices() == 0);
        assert(!hardware.HasEFX() && !hardware.HasEFXFilters());
        hardware.Shutdown();
    }
    idSoundVoice voice;
    assert(!voice.Start(0, 0) && !voice.UnPause() && !voice.Update());
    assert(!voice.IsPlaying() && voice.GetAmplitude() == 0.0f);
    float offset = 5.0f, latency = 6.0f;
    assert(!voice.GetPlaybackLatencyMS(offset, latency));
    assert(offset == 0.0f && latency == 0.0f);
    voice.Stop();
    voice.Pause();
    return 0;
}

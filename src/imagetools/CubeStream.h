/* Row-bounded, source-authoritative cube preparation; no graphics API here. */
#ifndef OPENQ4_CUBE_STREAM_H
#define OPENQ4_CUBE_STREAM_H
#include "TgaStream.h"

// The callback consumes pixels before returning. Rows may map to columns after
// camera-to-native cube orientation, and always contain tightly packed RGBA8.
typedef bool ( *cubeStreamSink_t )( void *, int, int, int, int, int, int, const byte * );
extern float mip_gammaTable[256];

class idCubeStreamRows {
public:
	idCubeStreamRows( int dimension, int skipped, int levels, int face, bool camera,
		bool downsizeGamma, bool mipGamma, cubeStreamSink_t consumer, void *context ) :
		size( dimension ), first( skipped ), count( skipped + levels ), side( face ),
		rotate( camera && ( face == 0 || face == 1 || face == 4 || face == 5 ) ),
		flipX( camera && ( face == 1 || face == 3 ) ),
		flipY( camera && ( face == 1 || face == 2 ) ),
		sourceGamma( downsizeGamma ), targetGamma( mipGamma ), sink( consumer ), user( context ) {
		memset( saved, 0, sizeof( saved ) );
		memset( reduced, 0, sizeof( reduced ) );
		memset( waiting, 0, sizeof( waiting ) );
		reversed = static_cast<byte *>( Mem_Alloc( size * 4 ) );
		for ( int level = 0; level + 1 < count; ++level ) {
			const int width = size >> level;
			saved[level] = static_cast<byte *>( Mem_Alloc( width * 4 ) );
			reduced[level] = static_cast<byte *>( Mem_Alloc( width * 2 ) );
		}
	}
	~idCubeStreamRows() {
		for ( int i = 0; i < 13; ++i ) { Mem_Free( saved[i] ); Mem_Free( reduced[i] ); }
		Mem_Free( reversed );
	}
	bool Push( int level, int y, const byte *row ) {
		const int width = size >> level;
		if ( level >= first ) {
			int x = 0, destY = y, w = width, h = 1;
			if ( rotate ) { x = y; destY = 0; w = 1; h = width; }
			const bool reverse = rotate ? flipY : flipX;
			if ( flipX ) x = width - x - w;
			if ( flipY ) destY = width - destY - h;
			const byte *pixels = row;
			if ( reverse ) {
				for ( int i = 0; i < width; ++i ) memcpy( reversed + i * 4, row + ( width - i - 1 ) * 4, 4 );
				pixels = reversed;
			}
			if ( !sink( user, side, level - first, x, destY, w, h, pixels ) ) return false;
		}
		if ( level + 1 >= count ) return true;
		if ( !waiting[level] ) {
			memcpy( saved[level], row, width * 4 );
			waiting[level] = true;
			return true;
		}
		waiting[level] = false;
		// Pair in canonical source order even when the file scans bottom-up.
		const byte *top = ( y & 1 ) ? saved[level] : row;
		const byte *bottom = ( y & 1 ) ? row : saved[level];
		const bool gamma = level < first ? sourceGamma : targetGamma;
		for ( int i = 0; i < width / 2; ++i ) {
			const byte *p[4] = { top + i * 8, top + i * 8 + 4, bottom + i * 8, bottom + i * 8 + 4 };
			// Match the arithmetic order of filtering AFTER native orientation,
			// including gamma floats: transpose/reflection may change that order.
			const int normal[4] = { 0, 1, 2, 3 }, transposed[4] = { 0, 2, 1, 3 };
			const int *order = rotate ? transposed : normal;
			for ( int c = 0; c < 4; ++c ) {
				int indexes[4];
				for ( int j = 0; j < 4; ++j ) indexes[j] = order[j ^ ( flipX ? 1 : 0 ) ^ ( flipY ? 2 : 0 )];
				const int a = p[indexes[0]][c], b = p[indexes[1]][c], d = p[indexes[2]][c], e = p[indexes[3]][c];
				reduced[level][i * 4 + c] = gamma ?
					idMath::Ftob( 255.0f * idMath::Pow( 0.25f * ( mip_gammaTable[a] + mip_gammaTable[b] + mip_gammaTable[d] + mip_gammaTable[e] ), 1.0f / 2.2f ) ) :
					static_cast<byte>( ( a + b + d + e ) >> 2 );
			}
		}
		return Push( level + 1, y >> 1, reduced[level] );
	}
private:
	idCubeStreamRows( const idCubeStreamRows & ) = delete;
	idCubeStreamRows &operator=( const idCubeStreamRows & ) = delete;
	int size, first, count, side;
	bool rotate, flipX, flipY, sourceGamma, targetGamma;
	cubeStreamSink_t sink;
	void *user;
	byte *saved[13], *reduced[13], *reversed;
	bool waiting[13];
};

class idCubeImageStream {
public:
	idCubeImageStream();
	~idCubeImageStream();
	bool Open( const char *name, cubeFiles_t extensions );
	bool Upload( int firstLevel, int levels, bool downsizeGamma, bool mipGamma,
		cubeStreamSink_t sink, void *context );
	void Close() { Clear(); }
	int Size() const { return headers[0].width; }
	ID_TIME_T Timestamp() const { return timestamp; }
private:
	void Clear();
	idCubeImageStream( const idCubeImageStream & ) = delete;
	idCubeImageStream &operator=( const idCubeImageStream & ) = delete;
	idFile *faces[6];
	tgaStreamHeader_t headers[6];
	ID_TIME_T timestamp;
	bool camera;
};
#endif

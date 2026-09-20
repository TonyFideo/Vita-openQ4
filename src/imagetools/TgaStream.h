/* Incremental TGA decoding. Source ownership stays with the caller. */
#ifndef OPENQ4_TGA_STREAM_H
#define OPENQ4_TGA_STREAM_H

struct tgaStreamHeader_t {
	int width, height, type, bytesPerPixel, attributes;
};

static bool R_TgaReadExact( idFile *file, void *data, int bytes ) {
	byte *out = static_cast<byte *>( data );
	while ( bytes > 0 ) {
		const int n = file->Read( out, bytes );
		if ( n <= 0 || n > bytes ) return false;
		out += n;
		bytes -= n;
	}
	return true;
}

static bool R_TgaStreamHeader( idFile *file, tgaStreamHeader_t &h ) {
	byte b[18];
	if ( file == NULL || !R_TgaReadExact( file, b, sizeof( b ) ) ) return false;
	h.width = b[12] | ( b[13] << 8 );
	h.height = b[14] | ( b[15] << 8 );
	h.type = b[2];
	h.bytesPerPixel = b[16] / 8;
	h.attributes = b[17];
	const bool gray = h.type == 3 || h.type == 11;
	if ( b[1] != 0 || ( b[17] & 0xc0 ) != 0 || h.width <= 0 || h.height <= 0 ||
		( h.type != 2 && h.type != 3 && h.type != 10 && h.type != 11 ) ||
		( gray ? b[16] != 8 : ( b[16] != 24 && b[16] != 32 ) ) ) return false;
	const int64 pixels = static_cast<int64>( h.width ) * h.height;
	if ( pixels > 0x7fffffff / 4 || file->Length() < 18 + b[0] ) return false;
	if ( h.type < 10 && pixels * h.bytesPerPixel > file->Length() - 18 - b[0] ) return false;
	byte id[255];
	return R_TgaReadExact( file, id, b[0] );
}

class idTgaStreamDecoder {
public:
	idTgaStreamDecoder( idFile *source, const tgaStreamHeader_t &header ) :
		file( source ), h( header ), next( 0 ), available( 0 ),
		remaining( header.width * header.height ), packet( 0 ), repeat( false ) {}

	// Emit one row in canonical left-to-right order. Canonical row number is
	// supplied separately so bottom-origin files never require a whole image.
	bool ReadRow( byte *rgba ) {
		if ( remaining < h.width ) return false;
		for ( int x = 0; x < h.width; ++x ) {
			if ( h.type >= 10 ) {
				if ( packet == 0 ) {
					byte code;
					if ( !Read( &code, 1 ) ) return false;
					packet = ( code & 127 ) + 1;
					repeat = ( code & 128 ) != 0;
					if ( packet > remaining ) return false;
					if ( repeat && !ReadPixel( repeated ) ) return false;
				}
			} else {
				packet = 1;
				repeat = false;
			}
			const int destX = ( h.attributes & 0x10 ) ? h.width - 1 - x : x;
			byte *dest = rgba + 4 * destX;
			if ( repeat ) memcpy( dest, repeated, 4 );
			else if ( !ReadPixel( dest ) ) return false;
			--packet;
			--remaining;
		}
		return true;
	}
	bool Finished() const { return remaining == 0 && packet == 0; }
private:
	bool Read( byte *out, int bytes ) {
		while ( bytes > 0 ) {
			if ( next == available ) {
				available = file->Read( input, sizeof( input ) );
				next = 0;
				if ( available <= 0 || available > static_cast<int>( sizeof( input ) ) ) return false;
			}
			const int n = Min( bytes, available - next );
			memcpy( out, input + next, n );
			out += n; next += n; bytes -= n;
		}
		return true;
	}
	bool ReadPixel( byte *rgba ) {
		byte raw[4] = {};
		if ( h.bytesPerPixel != 1 && h.bytesPerPixel != 3 && h.bytesPerPixel != 4 ) return false;
		if ( !Read( raw, h.bytesPerPixel ) ) return false;
		if ( h.bytesPerPixel == 1 ) rgba[0] = rgba[1] = rgba[2] = raw[0];
		else { rgba[0] = raw[2]; rgba[1] = raw[1]; rgba[2] = raw[0]; }
		rgba[3] = h.bytesPerPixel == 4 ? raw[3] : 255;
		return true;
	}
	idFile *file;
	tgaStreamHeader_t h;
	byte input[4096], repeated[4];
	int next, available, remaining, packet;
	bool repeat;
};
#endif

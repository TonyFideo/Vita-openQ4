/*
===========================================================================

Doom 3 BFG Edition GPL Source Code
Copyright (C) 1993-2012 id Software LLC, a ZeniMax Media company. 

This file is part of the Doom 3 BFG Edition GPL Source Code ("Doom 3 BFG Edition Source Code").  

Doom 3 BFG Edition Source Code is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Doom 3 BFG Edition Source Code is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Doom 3 BFG Edition Source Code.  If not, see <http://www.gnu.org/licenses/>.

In addition, the Doom 3 BFG Edition Source Code is also subject to certain additional terms. You should have received a copy of these additional terms immediately following the terms and conditions of the GNU General Public License which accompanied the Doom 3 BFG Edition Source Code.  If not, please request a copy in writing from id Software at the address below.

If you have questions concerning this license or the applicable additional terms, you may contact in writing id Software LLC, c/o ZeniMax Media Inc., Suite 120, Rockville, Maryland 20850 USA.

===========================================================================
*/
#ifndef __BINARYIMAGE_H__
#define __BINARYIMAGE_H__

#include "BinaryImageData.h"

class idFile;

/*
================================================
idBinaryImage is used by the idImage class for constructing mipmapped 
textures and for loading and saving generated files by idImage.
Also used in a memory-mapped form for imageCPU for offline megatexture
generation.
================================================
*/
class idBinaryImage {
public:
	idBinaryImage( const char * name ) : imgName( name ), loadedFileData( NULL ), sourceStream( NULL ) { }
	~idBinaryImage() { Clear(); }

	const char *		GetName() const { return imgName.c_str(); }
	void				SetName( const char *_name ) { imgName = _name; }

	void				Load2DFromMemory( int width, int height, const byte * pic_const, int numLevels, textureFormat_t & textureFormat, textureColor_t & colorFormat, bool gammaMips, bool filterNeutralAlpha = false );
	void				Load2DFromOwnedCompressedData( int width, int height, int numLevels, textureFormat_t textureFormat, textureColor_t colorFormat, byte *fileBuffer, const int *levelOffsets, const int *levelSizes );
	void				LoadCubeFromMemory( int width, const byte * pics[6], int numLevels, textureFormat_t & textureFormat, bool gammaMips );

	// File-backed compressed staging is consumed one mip at a time. The file
	// is adopted only on success and closed by Clear; the caller must call
	// ReadImageData before GetImageData and ReleaseImageData after the upload.
	bool                Load2DFromCompressedFile( int width, int height, int numLevels, textureFormat_t format, textureColor_t color, idFile *file, const int *offsets, const int *sizes );
	bool                ReadImageData( int i );
	void                ReleaseImageData( int i );
	bool                IsFileBacked() const { return sourceStream != NULL; }
	void				Clear();
	ID_TIME_T			LoadFromGeneratedFile( ID_TIME_T sourceFileTime );
	ID_TIME_T			LoadFromGeneratedFileUnchecked( bool *fileFound = NULL );
	ID_TIME_T			LoadFromCompactGeneratedFileUnchecked();
	ID_TIME_T			WriteGeneratedFile( ID_TIME_T sourceFileTime );
	bool				LoadFromFile( idFile *file, int dataBytes = -1 );
	bool				WriteToFile( idFile *file, ID_TIME_T sourceFileTime );

	const bimageFile_t &	GetFileHeader() const { return fileData; }

	int					NumImages() const { return images.Num(); }
	const bimageImage_t &	GetImageHeader( int i ) const { return images[i]; }
	const byte *			GetImageData( int i ) const { return images[i].data; }
	static void			GetGeneratedFileName( idStr & gfn, const char *imageName );
private:
	idStr				imgName;			// game path, including extension (except for cube maps), may be an image program
	bimageFile_t		fileData;

	class idBinaryImageData : public bimageImage_t {
	public:
		byte * data;
		bool ownsData;

		idBinaryImageData() : data( NULL ), ownsData( false ) { }
		~idBinaryImageData() { Free(); }
		idBinaryImageData & operator=( const idBinaryImageData & other ) {
			if ( this == &other ) {
				return *this;
			}

			level = other.level;
			destZ = other.destZ;
			width = other.width;
			height = other.height;
			if ( other.dataSize > 0 && other.data != NULL ) {
				Alloc( other.dataSize );
				memcpy( data, other.data, other.dataSize );
			} else {
				Free();
			}
			return *this;
		}
		void Free() {
			if ( data != NULL && ownsData ) {
				Mem_Free( data );
			}
			data = NULL;
			dataSize = 0;
			ownsData = false;
		}
		void Alloc( int size ) {
			Free();
			if ( size <= 0 ) {
				return;
			}
			dataSize = size;
			data = (byte *)Mem_Alloc( size );
			ownsData = true;
		}
		void SetExternalData( byte *externalData, int size ) {
			Free();
			data = externalData;
			dataSize = size;
			ownsData = false;
		}
	};

	idList< idBinaryImageData> images;
	byte *				loadedFileData;
	idFile *            sourceStream;
	idList<int>         sourceOffsets;

private:
	void				MakeGeneratedFileName( idStr & gfn );
	bool				LoadFromGeneratedFile( idFile * f, ID_TIME_T sourceFileTime, bool validateSourceFileTime, int dataBytes = -1 );
};

#endif // __BINARYIMAGE_H__

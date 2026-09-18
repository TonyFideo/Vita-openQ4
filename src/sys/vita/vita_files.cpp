#include "../../idlib/precompiled.h"

#include <dirent.h>
#include <errno.h>
#include <sys/stat.h>

int Sys_ListFiles( const char *directory, const char *extension, idStrList &list ) {
	list.Clear();

	if ( directory == NULL || directory[0] == '\0' ) {
		return -1;
	}
	if ( extension == NULL ) {
		extension = "";
	}

	bool directoriesOnly = false;
	if ( extension[0] == '/' && extension[1] == '\0' ) {
		directoriesOnly = true;
		extension = "";
	}

	DIR *dir = opendir( directory );
	if ( dir == NULL ) {
		return -1;
	}

	struct dirent *entry;
	while ( ( entry = readdir( dir ) ) != NULL ) {
		if ( entry->d_name[0] == '.' &&
			( entry->d_name[1] == '\0' ||
			  ( entry->d_name[1] == '.' && entry->d_name[2] == '\0' ) ) ) {
			continue;
		}

		idStr path = directory;
		path.AppendPath( entry->d_name );

		struct stat info;
		if ( stat( path.c_str(), &info ) != 0 ) {
			continue;
		}

		const bool isDirectory = ( info.st_mode & S_IFDIR ) != 0;
		if ( directoriesOnly != isDirectory ) {
			continue;
		}

		if ( !directoriesOnly && extension[0] != '\0' ) {
			idStr actualExtension;
			path.ExtractFileExtension( actualExtension );
			const char *wantedExtension = extension[0] == '.' ? extension + 1 : extension;
			if ( actualExtension.Icmp( wantedExtension ) != 0 ) {
				continue;
			}
		}

		list.Append( entry->d_name );
	}

	closedir( dir );
	return list.Num();
}

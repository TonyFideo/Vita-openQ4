#include "vita_glesd3_shader_compat.h"

#if defined(VITA) || defined(__vita__)

#include <cstring>

namespace {

static bool StartsWith( const std::string &s, size_t pos, const char *prefix ) {
	const size_t length = std::strlen( prefix );
	return pos + length <= s.size() && s.compare( pos, length, prefix ) == 0;
}

static void ReplaceAll( std::string &text, const std::string &from, const std::string &to ) {
	if ( from.empty() ) {
		return;
	}
	size_t pos = 0;
	while ( ( pos = text.find( from, pos ) ) != std::string::npos ) {
		text.replace( pos, from.length(), to );
		pos += to.length();
	}
}

}

std::string Vita_GLESD3_NormalizeShaderSource( const char *source, GLenum stage ) {
	if ( source == NULL ) {
		return std::string();
	}

	std::string input( source );
	std::string output;
	output.reserve( input.size() + 128 );

	std::string fragmentOutput;
	size_t cursor = 0;
	while ( cursor <= input.size() ) {
		const size_t end = input.find( '\n', cursor );
		std::string line = input.substr(
			cursor,
			end == std::string::npos ? std::string::npos : end - cursor );

		size_t first = line.find_first_not_of( " \t\r" );
		if ( first == std::string::npos ) {
			output += "\n";
			if ( end == std::string::npos ) {
				break;
			}
			cursor = end + 1;
			continue;
		}

		// GLES3 explicit attribute locations are redundant here because
		// gles_program.cpp binds every OpenQ4 attribute before program link.
		if ( StartsWith( line, first, "layout(" ) ) {
			const size_t close = line.find( ')', first );
			if ( close != std::string::npos ) {
				size_t after = close + 1;
				while ( after < line.size() && ( line[after] == ' ' || line[after] == '\t' ) ) {
					++after;
				}
				line.erase( first, after - first );
			}
		}

		first = line.find_first_not_of( " \t\r" );
		if ( first != std::string::npos && StartsWith( line, first, "invariant gl_Position;" ) ) {
			// VitaGL emits gl_Position with the POSITION semantic itself.
			line.clear();
		} else if ( first != std::string::npos && stage == GL_VERTEX_SHADER ) {
			if ( StartsWith( line, first, "in " ) ) {
				line.replace( first, 3, "attribute " );
			} else if ( StartsWith( line, first, "out " ) ) {
				line.replace( first, 4, "varying " );
			}
		} else if ( first != std::string::npos && stage == GL_FRAGMENT_SHADER ) {
			if ( StartsWith( line, first, "in " ) ) {
				line.replace( first, 3, "varying " );
			} else if ( StartsWith( line, first, "out " ) ) {
				// GLES3 names the fragment output; VitaGL's translator targets
				// gl_FragColor. Record that name and remove the declaration.
				const size_t semicolon = line.find( ';', first );
				if ( semicolon != std::string::npos ) {
					size_t nameEnd = semicolon;
					while ( nameEnd > first && ( line[nameEnd - 1] == ' ' || line[nameEnd - 1] == '\t' ) ) {
						--nameEnd;
					}
					size_t nameStart = nameEnd;
					while ( nameStart > first && line[nameStart - 1] != ' ' && line[nameStart - 1] != '\t' ) {
						--nameStart;
					}
					fragmentOutput = line.substr( nameStart, nameEnd - nameStart );
					line.clear();
				}
			}
		}

		output += line;
		output += "\n";

		if ( end == std::string::npos ) {
			break;
		}
		cursor = end + 1;
	}

	if ( stage == GL_FRAGMENT_SHADER && !fragmentOutput.empty() ) {
		ReplaceAll( output, fragmentOutput, "gl_FragColor" );
	}

	return output;
}

#endif

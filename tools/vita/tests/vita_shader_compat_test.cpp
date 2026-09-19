#include "vita_glesd3_shader_compat.h"

#include <cstdlib>
#include <iostream>
#include <string>

static bool RequireContains( const std::string &text, const char *needle ) {
	if ( text.find( needle ) != std::string::npos ) {
		return true;
	}
	std::cerr << "missing normalized shader text: " << needle << "\n" << text << "\n";
	return false;
}

static bool RequireAbsent( const std::string &text, const char *needle ) {
	if ( text.find( needle ) == std::string::npos ) {
		return true;
	}
	std::cerr << "unexpected normalized shader text: " << needle << "\n" << text << "\n";
	return false;
}

int main() {
	static const unsigned int vertexStage = 0x8B31u;
	static const unsigned int fragmentStage = 0x8B30u;

	const char *vertexSource =
		"#version 300 es\n"
		"layout(location = 0) in vec3 inPosition;\n"
		"out vec2 vTexCoord;\n"
		"out vec3 vDirection;\n"
		"uniform sampler2D uDiffuse;\n"
		"uniform samplerCube uCube;\n"
		"void main() {\n"
		"  vec4 a = texture(uDiffuse, vTexCoord);\n"
		"  vec4 b = texture(uCube, vDirection);\n"
		"  vec4 c = textureProj(uDiffuse, vec3(vTexCoord, 1.0));\n"
		"}\n";

	const char *fragmentSource =
		"#version 300 es\n"
		"in vec2 vTexCoord;\n"
		"uniform sampler2D uDiffuse;\n"
		"out vec4 outColor;\n"
		"void main() { outColor = texture(uDiffuse, vTexCoord); }\n";

	const std::string vertex = Vita_GLESD3_NormalizeShaderSource( vertexSource, vertexStage );
	const std::string fragment = Vita_GLESD3_NormalizeShaderSource( fragmentSource, fragmentStage );

	bool ok = true;
	ok &= RequireContains( vertex, "attribute vec3 inPosition;" );
	ok &= RequireContains( vertex, "varying vec2 vTexCoord;" );
	ok &= RequireContains( vertex, "texture2D(uDiffuse, vTexCoord)" );
	ok &= RequireContains( vertex, "textureCube(uCube, vDirection)" );
	ok &= RequireContains( vertex, "texture2DProj(uDiffuse, vec3(vTexCoord, 1.0))" );
	ok &= RequireContains( fragment, "varying vec2 vTexCoord;" );
	ok &= RequireContains( fragment, "gl_FragColor = texture2D(uDiffuse, vTexCoord)" );
	ok &= RequireAbsent( fragment, "out vec4 outColor;" );
	ok &= RequireAbsent( vertex, "layout(location" );

	if ( !ok ) {
		return EXIT_FAILURE;
	}
	std::cout << "Vita GLES_D3 shader compatibility test passed\n";
	return EXIT_SUCCESS;
}

#include <cassert>
#include <cstdarg>
#include <cstdio>
#include "gl_constants.h"
#define VITA 1
#ifndef GL_TEXTURE_CUBE_MAP_EXT
#define GL_TEXTURE_CUBE_MAP_EXT GL_TEXTURE_CUBE_MAP
#define GL_TEXTURE_CUBE_MAP_POSITIVE_X_EXT GL_TEXTURE_CUBE_MAP_POSITIVE_X
#endif
using GLenum=unsigned;using GLuint=unsigned;using GLint=int;using GLboolean=int;
enum{TT_CUBIC=1};
struct idImage{struct{int textureType=0,width=64,height=64;}opts;unsigned texnum=1,internalFormat=GL_RGBA16F,dataFormat=GL_RGBA,dataType=GL_HALF_FLOAT;const char*GetName(){return "_currentRender";}bool CopyFramebuffer(int,int,int,int,int=0);};
struct RenderTexture{unsigned GetDeviceHandle(){return 9;}int GetNumColorImages(){return 1;}};
static struct{RenderTexture*renderTexture=nullptr;}backEnd;
struct Common{void Warning(const char*,...){};}comm;static Common*common=&comm;
static bool GLEW_EXT_framebuffer_blit=false,GLEW_ARB_framebuffer_object=false,GLEW_VERSION_3_0=false;
static GLuint r_copyFramebufferFbo=0;
static GLenum error=0,readBuffer=GL_FRONT;static GLint readFbo=0,drawFbo=0;static bool scissor=true,fail=false;
static unsigned copies=0,blits=0;
static void R_BindTextureForDirectAccess(GLenum,GLuint){}
static void R_AllocateCopyTextureStorage(bool,GLenum,GLint,int,int,GLenum,GLenum){}
static GLenum glGetError(){auto e=error;error=0;return e;}
static void glGetIntegerv(GLenum e,GLint*v){if(e==GL_READ_FRAMEBUFFER_BINDING)*v=readFbo;else if(e==GL_DRAW_FRAMEBUFFER_BINDING)*v=drawFbo;else if(e==GL_READ_BUFFER)*v=readBuffer;else if(e==GL_SCISSOR_BOX){v[0]=1;v[1]=2;v[2]=3;v[3]=4;}else assert(false);}
static void glGenFramebuffers(int,GLuint*v){*v=7;}
static void glTexParameterf(GLenum,GLenum,float){}
static void glBindFramebuffer(GLenum e,GLuint v){if(e==GL_READ_FRAMEBUFFER)readFbo=v;else drawFbo=v;}
static void glReadBuffer(GLenum v){readBuffer=v;}
static void glFramebufferTexture2D(GLenum,GLenum,GLenum,GLuint,int){}
static void glDrawBuffer(GLenum){}
static GLboolean glIsEnabled(GLenum){return scissor;}
static void glDisable(GLenum){scissor=false;}static void glEnable(GLenum){scissor=true;}
static void glScissor(int x,int y,int w,int h){assert(x==1&&y==2&&w==3&&h==4);}
static void glBlitFramebuffer(int,int,int,int,int,int,int,int,GLenum,GLenum){assert(!scissor);++blits;if(fail)error=GL_OUT_OF_MEMORY;}
static void glCopyTexImage2D(GLenum,int,GLenum,int,int,int,int,int){assert(!scissor);++copies;if(fail)error=GL_OUT_OF_MEMORY;}
static void glCopyTexSubImage2D(GLenum,int,int,int,int,int,int,int){assert(!scissor);++copies;if(fail)error=GL_INVALID_OPERATION;}
static int sceClibPrintf(const char*,...){return 0;}
#include "owner.inc"
int main(){idImage image;fail=true;assert(!image.CopyFramebuffer(0,0,960,544));assert(image.opts.width==64&&image.opts.height==64);assert(readFbo==0&&readBuffer==GL_FRONT&&scissor);
fail=false;assert(image.CopyFramebuffer(0,0,960,544));assert(image.opts.width==960&&readBuffer==GL_FRONT&&scissor);assert(image.CopyFramebuffer(0,0,960,544)&&copies==3);
// A half-float destination stays a texture: even when blit is advertised, the
// Vita profile uses the typed CopyTex path rather than attaching RGBA16F as a
// GXM color surface. Precision/storage stay unchanged.
GLEW_EXT_framebuffer_blit=true;readFbo=0;drawFbo=0;readBuffer=GL_FRONT;
assert(image.CopyFramebuffer(0,0,320,180));assert(blits==0&&copies==4&&readFbo==0&&drawFbo==0&&readBuffer==GL_FRONT&&scissor);

// Non-floating captures retain the native GPU blit path.
idImage rgba8;rgba8.internalFormat=GL_RGBA8;rgba8.dataType=GL_UNSIGNED_BYTE;
assert(rgba8.CopyFramebuffer(0,0,320,180));assert(blits==1&&copies==4&&readFbo==0&&drawFbo==0&&readBuffer==GL_FRONT&&scissor);
RenderTexture render;backEnd.renderTexture=&render;readFbo=13;readBuffer=GL_COLOR_ATTACHMENT0;drawFbo=42;
assert(rgba8.CopyFramebuffer(0,0,128,64));assert(blits==2&&readFbo==13&&drawFbo==42&&readBuffer==GL_COLOR_ATTACHMENT0&&scissor);

// F16 remains on the typed path for an internal render source as well.
assert(image.CopyFramebuffer(0,0,128,64));assert(blits==2&&copies==5&&readFbo==13&&drawFbo==42&&readBuffer==GL_COLOR_ATTACHMENT0&&scissor);
fail=true;assert(!image.CopyFramebuffer(0,0,256,128));assert(image.opts.width==128&&image.opts.height==64&&readFbo==13&&drawFbo==42&&scissor);
puts("PASS production CopyFramebuffer: F16 typed-copy policy, RGBA8 GPU blits, fallback error propagation, state restore, no format downgrade");}

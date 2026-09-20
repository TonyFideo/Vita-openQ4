"""Execute production ownership/gating boundaries; this is not target gameplay.

Geometry math and GXM are mocked, but source fragments and lifetime decisions
come from the engine being built. Test the CPU-only path as well as the default
non-Vita policy. A full engine cross build remains necessary.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


def function(source, signature):
    a = source.index(signature)
    b = source.index('{', a)
    depth = 1
    e = b + 1
    while depth:
        depth += (source[e] == '{') - (source[e] == '}')
        e += 1
    return source[a:e]


def run_cpp(code, defines=()):
    compiler = shutil.which('c++')
    if not compiler:
        raise RuntimeError('native C++ compiler required')
    with tempfile.TemporaryDirectory(prefix='voq-gameplay-memory-') as directory:
        root = Path(directory)
        (root / 'test.cpp').write_text(code)
        result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
            *defines, str(root / 'test.cpp'), '-o', str(root / 'test')], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        result = subprocess.run([str(root / 'test')], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result.stdout


class GameplayMemoryTest(unittest.TestCase):
    def policy(self):
        return function((ROOT/'src/renderer/GpuSkinning.cpp').read_text(),
                        'bool R_GpuSkinning_UsesSourceSidecars(')

    def test_compiled_backend_policy(self):
        for define, expected in [((), 'true'), (('-DVITA=1',), 'false'), (('-D__vita__=1',), 'false')]:
            run_cpp('#include <cassert>\n' + self.policy() +
                '\nint main(){assert(R_GpuSkinning_UsesSourceSidecars() == ' + expected + ');}', define)

    def test_load_sidecars_stop_before_gpu_allocations(self):
        # Execute the actual prefix through the capability boundary. All code
        # past that boundary is deliberately a trap: an unsupported renderer
        # must not inspect CPU data or allocate GPU source streams at all.
        md5 = function((ROOT/'src/renderer/Model_md5.cpp').read_text(),
                       'void idMD5Mesh::BuildGpuSkinningSidecar(')
        md5 = md5[:md5.index('\tif ( deformInfo')] + '\tthrow 1;\n}'
        md5r = function((ROOT/'src/renderer/Model_md5r.cpp').read_text(),
                        'void rvRenderModelMD5R::BuildGpuSkinningSidecar(')
        md5r = md5r[:md5r.index('\n\tconst idList<rvMD5RVertexBufferDesc>')] + '\n\tthrow 1;\n}'
        prelude = r'''
#include <cassert>
struct List { int live=123; void Clear(){live=0;} };
enum {GPU_SKINNING_FALLBACK_NONE, GPU_SKINNING_FALLBACK_BACKEND_UNAVAILABLE};
struct idMD5Mesh { List gpuBindPoseVerts,gpuSkinningVerts; int gpuSkinningNumJoints=0,gpuSkinningFallback=0;
 unsigned cpuWeights=0x12345678; void BuildGpuSkinningSidecar(int); };
struct rvMD5RMesh { List gpuBindPoseVerts,gpuSkinningVerts; int gpuSkinningSourceVerts=0,gpuSkinningFallback=0;
 unsigned cpuWeights=0x12345678; };
struct rvRenderModelMD5R {void BuildGpuSkinningSidecar(rvMD5RMesh&) const;};
'''
        checks = r'''
int main() {
 for(int i=0;i<1024;++i) {
  idMD5Mesh mesh; mesh.BuildGpuSkinningSidecar(71);
  assert(mesh.gpuSkinningNumJoints==71 && mesh.gpuSkinningFallback==GPU_SKINNING_FALLBACK_BACKEND_UNAVAILABLE);
  assert(mesh.gpuBindPoseVerts.live==0 && mesh.gpuSkinningVerts.live==0 && mesh.cpuWeights==0x12345678);
  rvMD5RMesh packed; rvRenderModelMD5R model; model.BuildGpuSkinningSidecar(packed);
  assert(packed.gpuSkinningSourceVerts==0 && packed.gpuSkinningFallback==GPU_SKINNING_FALLBACK_BACKEND_UNAVAILABLE);
  assert(packed.cpuWeights==0x12345678 && packed.gpuBindPoseVerts.live==0 && packed.gpuSkinningVerts.live==0);
 }
}
'''
        run_cpp(prelude + self.policy() + '\n' + md5 + '\n' + md5r + checks, ('-DVITA=1',))
        # The same production prefixes on desktop still enter the original
        # builder, independent of initial cvar values (runtime toggle preserved).
        run_cpp(prelude + self.policy() + '\n' + md5 + '\n' + md5r + r'''
int main(){idMD5Mesh m;bool entered=false;try{m.BuildGpuSkinningSidecar(2);}catch(int){entered=true;}assert(entered);
 rvMD5RMesh p;rvRenderModelMD5R r;entered=false;try{r.BuildGpuSkinningSidecar(p);}catch(int){entered=true;}assert(entered);}
''')

    def test_surface_admission_retains_cpu_fallback(self):
        body = function((ROOT/'src/renderer/GpuSkinning.cpp').read_text(),
                        'bool R_GpuSkinning_AttachSurfaceContract(')
        body = body[body.index('{')+1:body.index('\tif ( sourceFallback')]
        run_cpp(r'''
#include <cassert>
#include <cstddef>
using srfTriangles_s = struct Tri {int reason=0;};
enum {GPU_SKINNING_FALLBACK_BACKEND_UNAVAILABLE=2};
int cleared=0;
void R_ClearStaticGpuSkinningJointPalette(Tri*){++cleared;}
void R_GpuSkinning_ClearSurfaceContract(Tri*t,int r){t->reason=r;}
''' + self.policy() + '\nbool admit(Tri *tri){' + body + r'''
 throw 1; }
int main(){Tri tri;assert(!admit(nullptr));assert(!admit(&tri));assert(cleared==1);
 assert(tri.reason==GPU_SKINNING_FALLBACK_BACKEND_UNAVAILABLE);}
''', ('-DVITA=1',))
        text = (ROOT/'src/renderer/Model_md5r.cpp').read_text()
        expr = re.search(r'const bool skipPackedCpuTangents = (.*?);', text, re.S)[1]
        run_cpp('#include <cassert>\n' + self.policy() + r'''
struct List {int Num()const{return 10;}};
struct Mesh {int gpuSkinningFallback=0,numDrawVertices=10;List gpuBindPoseVerts,gpuSkinningVerts;} mesh;
struct CVar{bool GetBool()const{return true;}}r_gpuSkinning;
const int GPU_SKINNING_FALLBACK_NONE=0;
int main(){bool allowGpuSkinning=true;assert(!(''' + expr + '));}', ('-DVITA=1',))

    def test_md5_bind_basis_scratch_released_without_frame_boundary(self):
        body = function((ROOT/'src/renderer/Model_md5.cpp').read_text(), 'void idMD5Mesh::ParseMesh(')
        tail = body[body.index('\tbaseVectors = (idVec4 *)Mem_Alloc16( deformInfo->numOutputVerts * 4'):]
        code = r'''
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <vector>
struct V {float x=0,y=0,z=0,w=0;void Set(float a,float b,float c,float d){x=a;y=b;z=c;w=d;}};
using idVec4=V;
struct idDrawVert {V xyz,normal,tangents[2];};
struct Tri {idDrawVert *verts;int numVerts;bool submitted=false;};
struct modelSurface_t {Tri *geometry;};
struct Deform {int numOutputVerts=32;} deform,*deformInfo=&deform;
idVec4 *baseVectors;
int live=0,peak=0; bool deferred=false;
std::vector<Tri*> queue;
void *Mem_Alloc16(size_t n){return malloc(n);}
void R_FreeStaticTriSurf(Tri*t){deferred=true;queue.push_back(t);}
void R_ReallyFreeStaticTriSurf(Tri*t){assert(!t->submitted);delete[]t->verts;delete t;--live;}
void UpdateSurface(void*,void*,modelSurface_t*t,bool a,bool b){assert(!a&&!b);
 t->geometry=new Tri{new idDrawVert[32],32,false};++live;if(live>peak)peak=live;
 for(int i=0;i<32;++i){t->geometry->verts[i].xyz.Set(i,2*i,3*i,0);}}
void R_DeriveTangents(Tri*t,bool){for(int i=0;i<32;++i){t->verts[i].normal.Set(1,0,0,0);
 t->verts[i].tangents[0].Set(0,1,0,0);t->verts[i].tangents[1].Set(0,0,1,0);}}
void BuildGpuSkinningSidecar(int){assert(live==0);}
void build(){int i;int numJoints=2;void*joints=nullptr;
'''
        checks = r'''
int main(){for(int j=0;j<1024;++j){build();assert(live==0&&!deferred);
 for(int i=0;i<32;++i){assert(baseVectors[4*i].x==i&&baseVectors[4*i].z==3*i&&baseVectors[4*i].w==1);
 assert(baseVectors[4*i+1].x==1&&baseVectors[4*i+2].y==1&&baseVectors[4*i+3].z==1);}
 free(baseVectors);}assert(peak==1&&queue.empty());}
'''
        run_cpp(code + tail + checks)

    def test_md5r_template_scratch_and_failure_paths(self):
        body = function((ROOT/'src/renderer/Model_md5r.cpp').read_text(),
                        'bool rvRenderModelMD5R::BuildDynamicMeshTemplate(')
        run_cpp(r'''
#include <cassert>
#include <cstring>
#include <vector>
#include <algorithm>
template<class T>struct idList {std::vector<T>v;void Clear(){v.clear();}void SetNum(int n){v.resize(n);}int Num()const{return v.size();}
 T*Ptr(){return v.data();}T&operator[](int i){return v[i];}};
struct Vert{int value;};struct Deform{int n;};
struct srfTriangles_t{Vert*verts;int*indexes;int numVerts,numIndexes;};
struct rvMD5RMesh{Deform*deformInfo=nullptr;idList<Vert>baseDrawVerts;};
struct rvRenderModelMD5R{bool BuildDynamicMeshTemplate(rvMD5RMesh&);};
int live=0,mode=0,derived=0,deferred=0;
void R_FreeDeformInfo(Deform*p){delete p;}
srfTriangles_t*GenerateStaticTriSurface(rvMD5RMesh&){if(mode==1)return nullptr;++live;
 return new srfTriangles_t{new Vert[3]{{4},{5},{6}},new int[3]{0,1,2},mode==2?0:3,3};}
void R_ReallyFreeStaticTriSurf(srfTriangles_t*p){delete[]p->verts;delete[]p->indexes;delete p;--live;}
void R_FreeStaticTriSurf(srfTriangles_t*){++deferred;}
Deform*R_BuildDeformInfo(int n,Vert*v,int ni,int*indices,bool){assert(n==3&&ni==3&&v[2].value==6&&indices[2]==2);
 ++derived;return mode==3?nullptr:new Deform{n};}
''' + body + r'''
int main(){rvRenderModelMD5R model;for(mode=0;mode<4;++mode){rvMD5RMesh mesh;
 bool ok=model.BuildDynamicMeshTemplate(mesh);assert(live==0&&deferred==0);
 if(mode==0){assert(ok&&mesh.baseDrawVerts[2].value==6&&mesh.deformInfo->n==3);
 int old=derived;assert(model.BuildDynamicMeshTemplate(mesh)&&derived==old);R_FreeDeformInfo(mesh.deformInfo);}
 else assert(!ok&&mesh.baseDrawVerts.Num()==0);}}
''')

    def test_stage_checkpoints_bracket_real_work(self):
        body = function((ROOT/'src/framework/Session.cpp').read_text(),
                        'void idSessionLocal::ExecuteMapChange(')
        markers = ['load:world:begin', 'rw->InitFromMap(', 'load:world:done',
                   'game->InitFromNewMap(', 'load:game-init:done', 'load:player:begin',
                   'game->SpawnPlayer(', 'load:player:done', 'load:renderer-finalize:begin',
                   'renderSystem->EndLevelLoad()', 'load:renderer-finalize:done',
                   'FS_ReleaseLevelLoadCache()', 'load:media:done', 'game->RunFrame(',
                   'load:settle:done', 'mapSpawned = true', 'load:ready']
        positions = [body.index(m) for m in markers]
        self.assertEqual(positions, sorted(positions))


if __name__ == '__main__': unittest.main()

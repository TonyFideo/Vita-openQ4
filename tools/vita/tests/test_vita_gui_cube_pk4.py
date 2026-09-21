"""Execute cube streaming over the in-tree PK4 reader, not a mock byte stream.

Only synthetic assets are generated. GXM storage/submission remain mocked by
CubeStreamTest.cpp. This is not a device, emulator, or gameplay test.
"""
from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[3]


class CubePk4IntegrationTest(unittest.TestCase):
    def test_stored_and_deflated_source_to_all_native_mips(self):
        spec = importlib.util.spec_from_file_location(
            'cube_test_support', ROOT / 'tools/vita/tests/test_vita_gui_cube_stream.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        support = module.CubeStreamTest
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler, 'A native C++ compiler is required')
        with tempfile.TemporaryDirectory(prefix='voq-cube-pk4-') as directory:
            out = Path(directory)
            support.setUpClass()
            try:
                for name in ('TgaStream.h', 'CubeStream.h', 'cube_production.inc',
                             'cube_gpu.inc', 'cube_api.inc'):
                    shutil.copy(Path(support.tmp.name) / name, out / name)
            finally:
                support.tearDownClass()
            source = (ROOT / 'tools/vita/tests/native/CubeStreamTest.cpp').read_text()
            source = source.replace('    int Read(void *out,int n) {',
                '    virtual ~idFile() {}\n    virtual int Read(void *out,int n) {')
            source = source.replace('    int Length() const {', '    virtual int Length() {')
            original_open = ('    idFile *OpenFileRead(const char *path){auto it=files.find(path);'
                'if(it==files.end())return nullptr;auto f=new idFile;f->bytes=it->second;'
                'if(partial)f->partial=7;++opened;return f;}')
            self.assertEqual(source.count(original_open), 1)
            source = source.replace(original_open,
                '    idFile *OpenFileRead(const char *path);\n'
                '    size_t readBytes=0; void AddToReadCount(int n){readBytes+=n;}')
            adapter = r'''
#include "Unzip.h"
static const char *zipPath = nullptr;
class idFile_InZip : public idFile {
public:
    unzFile z=nullptr; int fileSize=0;
    explicit idFile_InZip(const char *path) {
        z=unzOpen(zipPath); assert(z);
        // This fork requires an initialized current entry before name lookup.
        assert(unzGoToFirstFile(z)==UNZ_OK);
        assert(unzLocateFile(z,path,1)==UNZ_OK);
        unz_file_info info={};
        assert(unzGetCurrentFileInfo(z,&info,nullptr,0,nullptr,0,nullptr,0)==UNZ_OK);
        fileSize=info.uncompressed_size;
        assert(unzOpenCurrentFile(z)==UNZ_OK);
    }
    ~idFile_InZip() override;
    int Read(void *,int) override;
    int Length(void) override;
};
idFile *FakeFS::OpenFileRead(const char *path) {
    ++opened; return new idFile_InZip(path);
}
'''
            file_source = (ROOT / 'src/framework/File.cpp').read_text()
            for signature in ('idFile_InZip::~idFile_InZip(', 'int idFile_InZip::Read(',
                              'int idFile_InZip::Length('):
                adapter += '\n' + module.function(file_source, signature) + '\n'
            marker = 'static FakeFS *fileSystem=&fs;'
            self.assertEqual(source.count(marker), 1)
            source = source.replace(marker, marker + '\n' + adapter)
            source = source[:source.index('int main(int argc,char**argv)')] + r'''
int main(int argc,char**argv) {
    assert(argc==3);
    if (std::string(argv[1]) == "fixtures") {
        for (bool camera:{false,true}) for(int size:{8,32,128}) for(int flags:{0,0x10,0x20,0x30})
        for(int bpp:{1,3,4}) for(bool rle:{false,true}) {
            fixtures(size,bpp,(bpp==1?3:2)+(rle?8:0),flags,camera);
            std::string prefix=std::to_string(camera)+"-"+std::to_string(size)+"-"+
                std::to_string(flags)+"-"+std::to_string(bpp)+"-"+std::to_string(rle)+"-";
            for(auto &entry:fs.files) {
                std::string path=std::string(argv[2])+"/"+prefix+entry.first;
                FILE *file=fopen(path.c_str(),"wb"); assert(file);
                assert(fwrite(entry.second.data(),1,entry.second.size(),file)==entry.second.size());
                assert(fclose(file)==0);
            }
        }
        return 0;
    }
    unsigned cases=0;
    for(int archive=1;archive<3;++archive) {
        zipPath=argv[archive];
        for(bool camera:{false,true}) for(int size:{8,32,128}) for(int flags:{0,0x10,0x20,0x30})
        for(int bpp:{1,3,4}) for(bool rle:{false,true}) for(bool gamma:{false,true}) {
            std::string name=std::to_string(camera)+"-"+std::to_string(size)+"-"+
                std::to_string(flags)+"-"+std::to_string(bpp)+"-"+std::to_string(rle)+"-sky";
            for(int skip:{0,2}) {
                const int outputSize=size>>skip, count=levels(outputSize); texture tex;
                assert(voq_cube_storage(&tex,count,GL_RGBA8,outputSize,outputSize)==GL_NO_ERROR);
                const size_t originalRead=fs.readBytes;
                {
                    idCubeImageStream stream;
                    assert(stream.Open(name.c_str(),camera?CF_CAMERA:CF_NATIVE));
                    assert(fs.opened-fs.closed==6);
                    assert(stream.Upload(skip,count,!gamma,gamma,upload,&tex));
                    assert(fs.opened==fs.closed);
                }
                assert(fs.readBytes>originalRead);
                for(int side=0;side<6;++side) {
                    auto expected=orient(rgba(size,side,bpp),size,side,camera); int w=size;
                    for(int level=0;level<levels(size);++level) {
                        if(level>=skip) {
                            const byte *stored=(byte*)tex.data+side*voq_cube_face_bytes(outputSize,count)+
                                voq_cube_level_offset(outputSize,level-skip);
                            for(int y=0;y<w;++y) for(int x=0;x<w;++x)
                                assert(!memcmp(stored+4*referenceIndex(x,y,w),expected.data()+4*(y*w+x),4));
                        }
                        if(w>1) {
                            byte *lower=(level<skip?!gamma:gamma) ?
                                R_MipMapWithGamma(expected.data(),w,w):R_MipMap(expected.data(),w,w);
                            expected.assign(lower,lower+w*w); Mem_Free(lower); w>>=1;
                        }
                    }
                }
                gpu_free_texture_data(&tex); assert(live==0 && gpu.empty()); ++cases;
            }
        }
    }
    assert(cases==1152);
    printf("PASS %u real-PK4 cube cases: in-tree Unzip.cpp and exact idFile_InZip Read/Length/destructor; "
        "stored+deflated, six faces, native/camera, raw/RLE gray/RGB/RGBA, origins, gamma/downsize, "
        "all mip bytes and exactly-once close. GPU services mocked.\n",cases);
}
'''
            (out / 'real_cube.cpp').write_text(source)
            (out / 'prefix.h').write_text(
                '#include <cstdio>\n#include <cstdlib>\n#include <cstring>\n'
                '#include <cstddef>\n#include <cstdint>\n'
                'inline void *Mem_Alloc(size_t n){return std::malloc(n);}\n'
                'inline void *Mem_ClearedAlloc(size_t n){return std::calloc(1,n);}\n'
                'inline void Mem_Free(void *p){std::free(p);}\n')
            flags = ['-std=c++17', '-O1', '-g']
            if os.environ.get('VOQ_CUBE_SANITIZERS') == '1':
                flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            self.run_command([compiler, *flags, '-include', str(out / 'prefix.h'), '-c',
                str(ROOT / 'src/framework/Unzip.cpp'), '-o', str(out / 'Unzip.o')])
            executable = str(out / 'real_cube')
            self.run_command([compiler, *flags, '-I', str(out), '-I', str(ROOT / 'src/framework'),
                str(out / 'real_cube.cpp'), str(out / 'Unzip.o'), '-o', executable])
            fixtures_dir = out / 'fixtures'
            fixtures_dir.mkdir()
            self.run_command([executable, 'fixtures', str(fixtures_dir)])
            archives = []
            for name, method in (('stored.pk4', zipfile.ZIP_STORED),
                                 ('deflated.pk4', zipfile.ZIP_DEFLATED)):
                path = out / name
                with zipfile.ZipFile(path, 'w', compression=method) as archive:
                    for file in sorted(fixtures_dir.glob('*.tga')):
                        archive.write(file, file.name)
                archives.append(str(path))
            print(self.run_command([executable, *archives]).strip())

    def run_command(self, command):
        result = subprocess.run(command, text=True, capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout


if __name__ == '__main__':
    unittest.main()

from gub import mirrors
from gub.specs.cross import gcc as cross_gcc
from gub import misc

class Gcc (cross_gcc.Gcc_from_source):
    source = 'http://ftp.gnu.org/pub/gnu/gcc/gcc-3.4.6/gcc-3.4.6.tar.bz2'
    def patch (self):
        cross_gcc.Gcc_from_source.patch (self)
        self.system ('''
cd %(srcdir)s && patch -p1 < %(patchdir)s/gcc-3.4.0-arm-lib1asm.patch
cd %(srcdir)s && patch -p1 < %(patchdir)s/gcc-3.4.0-arm-nolibfloat.patch
''')
    configure_flags = (cross_gcc.Gcc_from_source.configure_flags
                + misc.join_lines ('''
--with-float=soft
#--with-fpu=vfp
'''))

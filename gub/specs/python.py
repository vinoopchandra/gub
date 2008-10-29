import re
import sys
#
from gub import build
from gub import context
from gub import misc
from gub import targetbuild
from gub import toolsbuild

class Python (targetbuild.AutoBuild):
    source = 'http://python.org/ftp/python/2.4.2/Python-2.4.2.tar.bz2'
    def __init__ (self, settings, source):
        targetbuild.AutoBuild.__init__ (self, settings, source)
        ## don't from gub import settings from build system.
	self.BASECFLAGS = ''
        self.CROSS_ROOT = '%(targetdir)s'

    def get_subpackage_names (self):
        return ['doc', 'devel', 'runtime', '']

    def get_build_dependencies (self):
        return ['expat-devel', 'zlib-devel', 'tools::python']

    def get_dependency_dict (self):
        return { '': ['expat', 'python-runtime', 'zlib'],
                 'devel' : ['libtool', 'python-devel'],
                 'runtime': [], }

    def patch (self):
        targetbuild.AutoBuild.patch (self)
        self.apply_patch ('python-2.4.2-1.patch')
        self.apply_patch ('python-configure.in-posix.patch', strip_component=0)
        self.apply_patch ('python-configure.in-sysname.patch', strip_component=0)
        self.apply_patch ('python-2.4.2-configure.in-sysrelease.patch')
        self.apply_patch ('python-2.4.2-setup.py-import.patch', strip_component=0)
        self.apply_patch ('python-2.4.2-setup.py-cross_root.patch', strip_component=0)
        self.file_sub ([('@CC@', '@CC@ -I$(shell pwd)')],
                        '%(srcdir)s/Makefile.pre.in')

    def force_autoupdate (self):
        return True

    def compile_command (self):
        ##
        ## UGH.: darwin Python vs python (case insensitive FS)
        c = targetbuild.AutoBuild.compile_command (self)
        c += ' BUILDPYTHON=python-bin '
        return c

    def install_command (self):
        ##
        ## UGH.: darwin Python vs python (case insensitive FS)
        c = targetbuild.AutoBuild.install_command (self)
        c += ' BUILDPYTHON=python-bin '
        return c

    # FIXME: c&p linux.py:install ()
    def install (self):
        targetbuild.AutoBuild.install (self)
        cfg = open (self.expand ('%(sourcefiledir)s/python-config.py.in')).read ()
        cfg = re.sub ('@PYTHON_VERSION@', self.expand ('%(version)s'), cfg)
        cfg = re.sub ('@PREFIX@', self.expand ('%(system_prefix)s/'), cfg)
        cfg = re.sub ('@PYTHON_FOR_BUILD@', sys.executable, cfg)
        self.dump (cfg, '%(install_prefix)s/cross/bin/python-config',
                   expand_string=False)
        self.system ('chmod +x %(install_prefix)s/cross/bin/python-config')


    ### Ugh.
    @context.subst_method
    def python_version (self):
        return '.'.join (self.version ().split ('.')[0:2])

class Python__mingw_binary (build.BinaryBuild):
    source = 'http://lilypond.org/~hanwen/python-2.4.2-windows.tar.gz'

    def python_version (self):
        return '2.4'

    def install (self):
        build.BinaryBuild.install (self)

        self.system ("cd %(install_root)s/ && mkdir usr && mv Python24/include  usr/ ")
        self.system ("cd %(install_root)s/ && mkdir -p usr/bin/ && mv Python24/* usr/bin/ ")
        self.system ("rmdir %(install_root)s/Python24/")


class Python__mingw (Python):

    def __init__ (self, settings, source):
        Python.__init__ (self, settings, source)
        self.target_gcc_flags = '-DMS_WINDOWS -DPy_WIN_WIDE_FILENAMES -I%(system_prefix)s/include' % self.settings.__dict__

    def get_build_dependencies (self):
        return Python.get_build_dependencies (self) + ['pthreads-w32-devel']

    # FIXME: first is cross compile + mingw patch, backported to
    # 2.4.2 and combined in one patch; move to cross-Python?
    def patch (self):
        Python.patch (self)
        self.apply_patch ('python-2.4.2-winsock2.patch')
        self.apply_patch ('python-2.4.2-setup.py-selectmodule.patch')

        ## to make subprocess.py work.
        self.file_sub ([
                ("import fcntl", ""),
                ], "%(srcdir)s/Lib/subprocess.py",
               must_succeed=True)

    def config_cache_overrides (self, str):
        # Ok, I give up.  The python build system wins.  Once
        # someone manages to get -lwsock32 on the
        # sharedmodules link command line, *after*
        # timesmodule.o, this can go away.
        return (str.replace ('ac_cv_func_select=yes', 'ac_cv_func_select=no')
                + '''
ac_cv_pthread_system_supported=yes,
ac_cv_sizeof_pthread_t=12
''')
##$(eval echo $((echo $ac_cv_sizeof_int + $ac_cv_sizeof_void_p)))
    def install (self):
        Python.install (self)
        self.file_sub ([('extra = ""', 'extra = "-lpython2.4 -lpthread"')],
                       '%(install_prefix)s/cross/bin/python-config')

        def rename_so (logger, fname):
            dll = re.sub ('\.so*', '.dll', fname)
            loggedos.rename (logger, fname, dll)

        self.map_locate (rename_so,
                         self.expand ('%(install_prefix)s/lib/python%(python_version)s/lib-dynload/'),
                                      '*.so*')
        ## UGH.
        self.system ('''
cp %(install_prefix)s/lib/python%(python_version)s/lib-dynload/* %(install_prefix)s/bin
''')
        self.system ('''
chmod 755 %(install_prefix)s/bin/*
''')
        self.system (misc.join_lines ('''
cd %(install_prefix)s
&& echo EXPORTS > lib/libpython2.4.a.def
&& %(toolchain_prefix)snm bin/libpython2.4.dll | grep ' T _' | sed -e 's/.* T _//' -e 's/@.*//' >> lib/libpython2.4.a.def
&& %(toolchain_prefix)sdlltool --def lib/libpython2.4.a.def --dllname bin/libpython2.4.dll --output-lib lib/libpython2.4.dll.a
'''))
        self.copy ('%(sourcefiledir)s/libtool.la', '%(install_prefix)s/lib/libpython2.4.la')
        self.file_sub ([('LIBRARY', 'python2.4'),
                        ('STATICLIB', ''),
                        ('DEPEND', ' -lpthread'),
                        ('LIBDIR', '%(prefix_dir)s/lib')],
                       '%(install_prefix)s/lib/libpython2.4.la')

class Python__tools (toolsbuild.AutoBuild, Python):
    source = 'http://python.org/ftp/python/2.4.5/Python-2.4.5.tar.bz2'
    def get_build_dependencies (self):
        return ['autoconf', 'libtool']
    def force_autoupdate (self):
        return True
    def install (self):
        toolsbuild.AutoBuild.install (self)
    def wrap_executables (self):
        pass

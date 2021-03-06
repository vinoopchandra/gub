from gub import tools

class Fakeroot__tools (tools.AutoBuild):
    source = 'http://ftp.debian.nl/debian/pool/main/f/fakeroot/fakeroot_1.5.10.tar.gz'
    dependencies = [
            'libtool',
            'util-linux', # fakeroot script uses /usr/bin/getopt
            ]
    def libs (self):
        return '-ldl'
    configure_variables = (tools.AutoBuild.configure_variables
                + ' CC=%(system_prefix)s/bin/%(toolchain_prefix)sgcc'
                + ' CCLD=%(system_prefix)s/bin/%(toolchain_prefix)sgcc'
                + ' CXX=%(system_prefix)s/bin/%(toolchain_prefix)sg++')
    def compile (self):
        tools.AutoBuild.compile (self)
        self.file_sub ([('BINDIR=.*', 'BINDIR=%(system_prefix)s/bin'),
                        ('PATHS=', 'PATHS=%(system_prefix)s/lib:'),],
                       '%(builddir)s/scripts/fakeroot')

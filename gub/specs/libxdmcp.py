from gub import target

class Libxdmcp (target.AutoBuild):
    source = 'http://xorg.freedesktop.org/releases/X11R7.4/src/everything/libXdmcp-1.0.2.tar.gz'
    dependencies = ['tools::libtool', 'xproto-devel']

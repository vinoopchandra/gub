"""
    Copyright (c) 2005--2007
    Jan Nieuwenhuizen <janneke@gnu.org>
    Han-Wen Nienhuys <hanwen@xs4all.nl>

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2, or (at your option)
    any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the Free Software
    Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
"""

import datetime
import difflib
import pickle
import os
import sys
import time
#
from gub.syntax import printf
from gub import cross
from gub import build
from gub import misc
from gub import gup
from gub import loggedos
from gub import logging
from gub import runner
import gub.settings   # otherwise naming conflict with settings local vars.


def checksum_diff (a, b, fromfile='', tofile='',
                   fromfiledate='', tofiledate=''):
    return '\n'.join (difflib.unified_diff (a.split ('\n'),
                                            b.split ('\n'),
                                            fromfile,
                                            tofile,
                                            fromfiledate,
                                            tofiledate))

# FIXME s/spec/build/, but we also have two definitions of package/pkg
# here: sub packages and name of global package under build

#FIXME: split spec_* into SpecBuiler?
class BuildRunner:
    def __init__ (self, manager, settings, options, specs):
        self.managers = {settings.platform : manager }
        self.settings = settings
        self.options = options
        self.specs = specs

        # spec name -> string
        self.checksums = dict ()
        self.failed_checksums = dict ()

        # PATH = os.environ['PATH']
        # cross_prefix is also necessary for building cross packages, such as GCC
        # yes, so we set that in cross.AutoBuild.get_substitution_dict ()
        # we cannot do it here, as this will break all tools::* checksums
        # going from mingw::libtool to darwin-x86::libtool
        # os.environ['PATH'] = self.settings.expand ('%(cross_prefix)s/bin:' + PATH, locals ())
        self.add_packages_to_manager (self.specs)

    def manager (self, platform):
        if platform not in self.managers:
            settings = gub.settings.Settings (platform)
            self.managers[platform] = gup.DependencyManager (settings.system_root)
        return self.managers[platform]
        
    def add_packages_to_manager (self, package_object_dict):
        ## Ugh, this sucks: we now have to have all packages
        ## registered at the same time.
        for spec in list (package_object_dict.values ()):
            for package in spec.get_packages ():
                self.manager (package.platform ()).register_package_dict (package.dict ())

    def calculate_checksums (self):
        logging.verbose ('calculating checksums\n')
        for spec in list (self.specs.values ()):
            name = spec.platform_name ()
            logger = logging.NullCommandLogger ()

            command_runner = runner.DeferredRunner (logger)
            spec.connect_command_runner (command_runner)
            spec.build ()
            spec.connect_command_runner (None)

            self.checksums[name] = command_runner.checksum ()
            reason = self.spec_checksums_fail_reason (spec)
            if reason:
                self.failed_checksums[name] = reason

    # FIXME: move to gup.py or to build.py?
    def spec_checksums_fail_reason (self, spec):
        # need to read package header to read checksum_file.  since
        # checksum is per buildspec, only need to inspect one package.
        pkg = spec.get_packages ()[0]    
        name = pkg.name ()
        pkg_dict = self.manager (pkg.platform ()).package_dict (name)

        checksum_file = pkg_dict['checksum_file']
        try:
            build_checksum_ondisk = open (pkg_dict['checksum_file']).read ()
            checksum_time = time.ctime (os.stat (checksum_file).st_mtime)
        except IOError:
            build_checksum_ondisk = '0000'
            checksum_time = '0000'

        # fixme: spec.build_checksum () should be method.
        reason = ''
        hdr = pkg.expand ('%(split_hdr)s')
        if spec.source_checksum () != pkg_dict['source_checksum']:
            reason = 'source %s -> %s (memory)' % (spec.source_checksum (), pkg_dict['source_checksum'])

        if reason == '' and self.checksums[spec.platform_name ()] != build_checksum_ondisk:
            failure = 'diff'
            spec_name = spec.name ()
            spec_platform = spec.platform ()
            diff = checksum_diff (build_checksum_ondisk,
                                  self.checksums[spec.platform_name ()],
                                  checksum_file,
                                  'THIS BUILD',
                                  checksum_time,
                                  time.ctime (time.time ()))
            message = '\n' + diff
            reason = '\n *** Checksum mismatch: %(failure)s (%(spec_name)s, %(spec_platform)s)%(message)s\n' % locals ()

        if reason == '' and not os.path.exists (hdr):
            reason = 'hdr missing'
            
        if reason == '':
            hdr_dict = dict (pickle.load (open (hdr, 'rb')))
            if spec.source_checksum () != hdr_dict['source_checksum']:
                reason = 'source %s -> %s (disk)' % (spec.source_checksum (), hdr_dict['source_checksum'])

        # we don't use cross package checksums, otherwise we have to
        # rebuild everything for every cross package change.
        return reason

    # FIXME: this should be in gpkg/gup.py otherwise it's impossible
    # to install packages in a conflict situation manually
    def spec_conflict_resolution (self, spec, pkg):
        pkg_name = pkg.name ()
        install_candidate = pkg
        subname = ''
        if spec.name () != pkg_name:
            subname = pkg_name.split ('-')[-1]
        manager = self.manager (spec.platform ())
        if subname in spec.get_conflict_dict ():
            for c in spec.get_conflict_dict ()[subname]:
                if manager.is_installed (c):
                    printf ('  %(c)s conflicts with %(pkg_name)s' % locals ())
                    conflict_source = manager.source_name (c)
                    # FIXME: implicit provides: foo-* provides foo-core,
                    # should implement explicit provides
                    if conflict_source + '-core' == pkg_name:
                        printf ('    non-core %(conflict_source)s already installed'
                               % locals ())
                        printf ('      skipping request to install %(pkg_name)s'
                               % locals ())
                        install_candidate = None
                        continue
                    printf ('    removing %(c)s' % locals ())
                    manager.uninstall_package (c)
        return install_candidate

    def pkg_install (self, spec, pkg):
        manager = self.manager (spec.platform ())
        if not manager.is_installed (pkg.name ()):
            install_candidate = self.spec_conflict_resolution (spec, pkg)
            if install_candidate:
                manager.unregister_package_dict (install_candidate.name ())
                manager.register_package_dict (install_candidate.dict ())
                manager.install_package (install_candidate.name ())

    def spec_install (self, spec):
        for pkg in spec.get_packages ():
            self.pkg_install (spec, pkg)

    def get_skip_stages (self):
        """Returns list of stages (strings) to be skipped.

        Uses command line options as input.
        """
        skip = []
        if self.options.offline:
            skip += ['download']
        if not self.options.src_package:
            skip += ['src_package']
        if self.options.keep_build:
            skip += ['clean']
        return skip
    
    def spec_build (self, spec_name):
        spec = self.specs[spec_name]
        
        all_installed = True
        for p in spec.get_packages ():
            all_installed = (all_installed
                             and self.manager (p.platform ()).is_installed (p.name ()))
        if all_installed:
            return

        checksum_fail_reason = self.failed_checksums.get (spec_name, '')
        logger = logging.default_logger
        if checksum_fail_reason:
            logger.write_log ('must rebuild: %(spec_name)s\n' % locals (), 'verbose')
        else:
            logger.write_log ('checksum ok: %(spec_name)s\n' % locals (), 'verbose')

        if logging.get_numeric_loglevel ('verbose') > logger.threshold:
            logger.write_log ('\n'.join (checksum_fail_reason.split ('\n')[:10]), 'verbose')
        logger.write_log (checksum_fail_reason, 'output')

        is_installable = misc.forall (self.manager (p.platform ()).is_installable (p.name ())
                                      for p in spec.get_packages ())
        if (not is_installable or checksum_fail_reason):
            deferred_runner = runner.DeferredRunner (logger)
            spec.connect_command_runner (deferred_runner)
            spec.runner.stage ('building package: %s\n' % spec_name)
            skip = self.get_skip_stages () + spec.get_done ()
            skip = [x for x in skip if x != self.options.stage]
            
            spec.build (self.options, skip)
            spec.connect_command_runner (None)
            deferred_runner.execute_deferred_commands ()
            if len (self.checksums[spec_name].split ('\n')) < 5:
                # Sanity check.  This can't be right.  Do not
                # overwrite precious [possibly correct] checksum.
                raise Exception ('BROKEN CHECKSUM:' + self.checksums[spec_name])
            open (spec.expand ('%(checksum_file)s'), 'w').write (self.checksums[spec_name])
            #spec.set_done ('')
            loggedos.system (logging.default_logger, spec.expand ('rm -f %(stamp_file)s'))
        logger.write_log (spec.stage_message ('pkg_install'), 'stage')
        # Ugh, pkg_install should be stage
        if spec.install_after_build:
            self.spec_install (spec)
        logging.default_logger.write_log ('\n', 'stage')

    def is_outdated_spec (self, spec_name):
        spec = self.specs[spec_name]
        checksum_fail_reason = self.failed_checksums.get (spec_name, '')
        checksum_ok = '' == checksum_fail_reason
        for pkg in spec.get_packages ():
            if (self.manager (pkg.platform ()).is_installed (pkg.name ())
                and (not self.manager (pkg.platform ()).is_installable (pkg.name ())
                     or not checksum_ok)):
                return True
        return False

    def uninstall_spec (self, spec):
        for pkg in spec.get_packages ():
            if (self.manager (pkg.platform ()).is_installed (pkg.name ())):
                self.manager (pkg.platform ()).uninstall_package (pkg.name ())

    def uninstall_outdated_specs (self, deps):
        outdated = list (reversed ([name for name in deps
                                    if self.is_outdated_spec (name)]))
        if outdated:
            platform = self.settings.platform
            outdated_str = (' '.join (outdated)
                            .replace (misc.with_platform ('', platform), ''))
            logging.default_logger.write_log ('removing outdated[%(platform)s]: %(outdated_str)s\n' % locals (), 'stage')
            for name in outdated:
                self.uninstall_spec (self.specs[name])

    def build_source_packages (self, names):
        deps = [d for d in names if d in self.specs]
        platform = self.settings.platform
        # fail_str: keep ordering of names
        fail_str = ' '.join ([s for s in deps if s in list (self.failed_checksums.keys ())]).replace (misc.with_platform ('', platform), '')
        if not fail_str:
            fail_str = '<nothing to be done>.'
        logging.default_logger.write_log ('must rebuild[%(platform)s]: %(fail_str)s\n' % locals (), 'stage')
        self.uninstall_outdated_specs (deps)
        global target
        for spec_name in deps:
            target = spec_name
            self.spec_build (spec_name)
        target = None
                
target = None

def main ():
    boe

if __name__ == '__main__':
    main ()

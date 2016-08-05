from __future__ import print_function
from setuptools.command.sdist import sdist
#from pythonforandroid import toolchain
import subprocess
import shlex
import sys
from os.path import realpath, join, exists, dirname, curdir, basename, split
from os import makedirs
from glob import glob
from shutil import rmtree, copyfile


def argv_contains(t):
    for arg in sys.argv:
        if arg.startswith(t):
            return True
    return False


class BdistAPK(sdist):
    description = 'Create an APK with python-for-android'

    user_options = []

    def initialize_options(self):


        sdist.initialize_options(self)

        for option in self.user_options:
            setattr(self, option[0].strip('=').replace('-', '_'), None)

        option_dict = self.distribution.get_option_dict('apk')

        # This is a hack, we probably aren't supposed to loop through
        # the option_dict so early because distutils does exactly the
        # same thing later to check that we support the
        # options. However, it works...
        for (option, (source, value)) in option_dict.items():
            setattr(self, option, str(value))

    def add_defaults(self):
        # Believe it or not, this actually has the opposite effect!
        self.distribution.include_package_data = False
        sdist.add_defaults(self)

    def finalize_options(self):

        sdist.finalize_options(self)
        self.keep_temp = True
        setup_options = self.distribution.get_option_dict('apk')
        self.main_entry_point = self.search_entry_points()
        if self.main_entry_point is not None:
            requirements = getattr(self, 'requirements', '').split(',')
            requirements.append(self.distribution.get_name())
            self.requirements = ','.join([r for r in requirements if len(r)])
            setup_options['requirements'] = ('setup script', self.requirements)


        for (option, (source, value)) in setup_options.items():
            if source == 'command line':
                continue
            if not argv_contains('--' + option):
                if value in (None, 'None'):
                    sys.argv.append('--{}'.format(option))
                else:
                    sys.argv.append('--{}={}'.format(option, value))

        # Inject some argv options from setup.py if the user did not
        # provide them
        if not argv_contains('--name'):
            name = self.distribution.get_name()
            sys.argv.append('--name={}'.format(name))
            self.name = name

        if not argv_contains('--package'):
            package = 'org.test.{}'.format(self.name.lower().replace(' ', ''))
            print('WARNING: You did not supply an Android package '
                  'identifier, trying {} instead.'.format(package))
            print('         This may fail if this is not a valid identifier')
            sys.argv.append('--package={}'.format(package))

        if not argv_contains('--version'):
            version = self.distribution.get_version()
            sys.argv.append('--version={}'.format(version))

        if not argv_contains('--arch'):
            arch = 'armeabi'
            self.arch = arch
            sys.argv.append('--arch={}'.format(arch))

        self.bdist_dir = 'build/bdist.android-{}'.format(self.arch)
        if self.main_entry_point is not None:
            script_path = join(self.bdist_dir, 'main.py')
            self.main_entry_point['script_path'] = script_path

    def run(self):
        sdist.run(self)
        self.prepare_build_dir()

        from pythonforandroid.toolchain import main
        sys.argv[1] = 'apk'
        main()

    def prepare_build_dir(self):
        bdist_dir = self.bdist_dir
        if exists(bdist_dir):
            rmtree(bdist_dir)
        makedirs(bdist_dir)

        if argv_contains('--private'):
            print('WARNING: Received --private argument when this would '
                  'normally be generated automatically.')
            print('         This is probably bad unless you meant to do '
                  'that.')
        if self.main_entry_point is not None:
            self.build_entry_point()
            self.build_sdist_recipe()
            main_py_dir = dirname(self.main_entry_point['script_path'])
        else:
            main_py_dir = self.search_dirs()

        sys.argv.append('--private={}'.format(join(realpath(curdir), main_py_dir)))

    def search_dirs(self):
        main_py_dirs = []
        for filen in self.filelist.files:
            if basename(filen) in ('main.py', 'main.pyo'):
                main_py_dirs.append(filen)

        # This feels ridiculous, but how else to define the main.py dir?
        # Maybe should just fail?
        if len(main_py_dirs) == 0:
            print('ERROR: Could not find main.py, so no app build dir defined')
            print('You should name your app entry point main.py')
            exit(1)
        if len(main_py_dirs) > 1:
            print('WARNING: Multiple main.py dirs found, using the shortest path')
        main_py_dirs = sorted(main_py_dirs, key=lambda j: len(split(j)))
        return join(dirname(main_py_dirs[0]))

    def search_entry_points(self):
        package_names = [p for p in self.distribution.packages if '.' not in p]
        if len(package_names) == 1:
            self.top_level_package = package_names[0]
        else:
            self.top_level_package = None
            return None
        main_entry_point = None
        for entry_points in self.distribution.entry_points.values():
            for entry_point in entry_points:
                script_name, package_ident = entry_point.split('=')
                package_ident = package_ident.strip(' ')
                modpath, func_name = package_ident.split(':')
                if '.' not in package_ident:
                    if modpath == 'main':
                        package_name = self.top_level_package
                        main_entry_point = {
                            'modpath':modpath,
                            'func_name':func_name,
                            'package_name':package_name,
                        }
                        break
                else:
                    package_name = package_ident.split('.')[0]
                    if package_name != self.top_level_package:
                        continue
                    if modpath.split('.')[1] == 'main':
                        main_entry_point = {
                            'modpath':modpath,
                            'func_name':func_name,
                            'package_name':package_name,
                        }
                        break
        return main_entry_point

    def build_entry_point(self):
        template = '\n'.join([
            'from {modpath} import {func_name}',
            '',
            'if __name__ == "__main__":',
            '    {func_name}()',
            '',
        ])
        script_text = template.format(**self.main_entry_point)
        script_path = self.main_entry_point['script_path']
        with open(join(realpath(curdir), script_path), 'w') as f:
            f.write(script_text)

    def build_sdist_recipe(self):
        recipes = subprocess.check_output(shlex.split('p4a recipes --compact'))
        recipes = [r.rstrip('\n') for r in recipes.split(' ')]

        requirements = ['python2', 'setuptools']
        for req in self.requirements.split(','):
            req = req.strip(' ')
            if req in recipes:
                requirements.append(req)
        #requirements.extend(self.requirements.split(','))
        requirements = ', '.join(['"{}"'.format(r) for r in requirements])
        script_text = '\n'.join([
            'from pythonforandroid.recipe import PythonRecipe, IncludedFilesBehaviour',
            'class SdistRecipe(IncludedFilesBehaviour, PythonRecipe):',
            '    site_packages_name = "{pkg_name}"',
            '    src_filename = "{filename}"',
            '    version = "{version}"',
            '    depends = [{requirements}]',
            '    call_hostpython_via_targetpython = False',
            'recipe = SdistRecipe()',
        ]).format(
            filename=join(realpath(curdir), self.distribution.get_fullname()),
            #filename=join(realpath(curdir), self.get_archive_files()[0]),
            pkg_name=self.top_level_package,
            version=self.distribution.get_version(),
            requirements=requirements,
        )
        name = self.distribution.get_name()
        recipe_dir = join(realpath(curdir), 'p4a-recipes', name)
        #recipe_dir = join(realpath(curdir), self.bdist_dir, 'p4a-recipes', name)
        if not exists(recipe_dir):
            makedirs(recipe_dir)
        with open(join(recipe_dir, '__init__.py'), 'w') as f:
            f.write(script_text)


def _set_user_options():
    # This seems like a silly way to do things, but not sure if there's a
    # better way to pass arbitrary options onwards to p4a
    user_options = [('requirements=', None, None),]
    for i, arg in enumerate(sys.argv):
        if arg.startswith('--'):
            if ('=' in arg or
                (i < (len(sys.argv) - 1) and not sys.argv[i+1].startswith('-'))):
                user_options.append((arg[2:].split('=')[0] + '=', None, None))
            else:
                user_options.append((arg[2:], None, None))

    BdistAPK.user_options = user_options

_set_user_options()

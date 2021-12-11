#!/usr/bin/env python3
# vim: set expandtab tabstop=4 shiftwidth=4:

# Copyright 2021 Christopher J. Kucera
# <cj@apocalyptech.com>
# <http://apocalyptech.com/contact.php>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the development team nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL CJ KUCERA BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import sys
import shlex
import shutil
import argparse
import tempfile
import subprocess

# NOTES:
#
#  - All the heavy lifting here is done by GNU diff/diff3
#  - Witcher 3 script files are UTF-16 by default, and GNU diff/diff3 can't
#    cope with that, alas.  So this util uses a tmpdir to store UTF-8-encoded
#    conversions and does all its work in there, and then re-converts to
#    UTF-16 once done.
#  - Not all mod scripts are UTF-16 encoded (also alas).  At the moment, we
#    look for a UTF-16 BOM and assume the file is latin1/ISO-8859 if that's
#    not found.  This logic will obviously fail if we come across a mod
#    file that's UTF-8 or something.  If I run into that, I may have to pull
#    in chardet: https://github.com/chardet/chardet
#

class ScriptFile:
    """
    A single Witcher 3 script filen instance, whether it be a stock game file,
    modded version, or our final merged version.  This class keeps track of both
    the original/eventual on-disk location and the tmpdir-cache that we actually
    use while processing.
    """

    def __init__(self, filename, mod, tmpdir, path_orig, force_cache=True, create_dummy_if_missing=False):
        self.tmpdir = tmpdir
        self.filename = filename
        self.mod = mod
        self.path_orig = path_orig
        self.dir_orig = os.path.dirname(path_orig)
        self.path_cached = os.path.join(tmpdir, mod, filename)
        self.dir_cached = os.path.dirname(self.path_cached)
        #print('Paths:')
        #print(f'  - Orig: {self.path_orig}')
        #print(f'  - Cache: {self.path_cached}')
        if not os.path.exists(self.dir_cached):
            os.makedirs(self.dir_cached, exist_ok=True)
        if os.path.exists(self.path_orig):
            # "new" files added to the game via mods, such as `noTimeForGwent.ws`,
            # might not actually be UTF-16 (it looks like other mods might even
            # "overwrite" previously-UTF-16 files with non-UTF-16).  We'll check
            # for a BOM and assume anything without a BOM is latin1/ISO-8859.
            # Hopefully we don't run into something which starts encoding in UTF-8.
            with open(self.path_orig, 'rb') as df:
                bom = df.read(3)
                if bom[:2] == b"\xFF\xFE" or bom[:2] == b"\xFE\xFF":
                    encoding='utf-16'
                elif bom == b"\xEF\xBB\xBF":
                    encoding='utf-8-sig'
                else:
                    encoding='latin1'
            with open(self.path_orig, 'rt', encoding=encoding) as df:
                with open(self.path_cached, 'wt', encoding='utf-8') as odf:
                    odf.write(df.read())
        elif create_dummy_if_missing:
            with open(self.path_cached, 'wt', encoding='utf-8') as odf:
                pass
        elif force_cache:
            raise RuntimeError('Original script not found: {}'.format(self.path_orig))

    def copy_to_orig(self):
        """
        Copies the file in our cached location to the original in-game location
        (intended to just be used during merge, to write out our merged copy to
        the mods dir)
        """
        if not os.path.exists(self.dir_orig):
            os.makedirs(self.dir_orig, exist_ok=True)
        with open(self.path_cached, 'rt', encoding='utf-8') as df:
            with open(self.path_orig, 'wt', encoding='utf-16', newline="\r\n") as odf:
                odf.write(df.read())

class ModScript:
    """
    A single Witcher 3 mod script.  This class encapsulates all variants found
    for the script, namely:
        1) The original "stock" script version found in the W3 base dir
        2) The final "merged" version which we'll eventually create
        3) The individual modified versions of the script found in the
           associated mod dirs.
    Those individual bits are stored as ScriptFile objects.
    """

    stock_key = '_basegame_'
    merged_key = 'mod0000_apoc_merged'

    def __init__(self, witcher3_dir, filename, tmpdir):
        self.tmpdir = tmpdir
        self.filename = filename
        self.stock = ScriptFile(filename, self.stock_key, self.tmpdir,
                os.path.join(witcher3_dir, 'content', 'content0', filename),
                create_dummy_if_missing=True)
        self.merged = ScriptFile(filename, self.merged_key, self.tmpdir,
                os.path.join(self.merged_key, 'content', filename),
                force_cache=False)
        self.mods = {}
        self.merge_problems = False

    def import_from_mod(self, mod):
        """
        Load in a version of this file from the specified mod
        """
        if mod.endswith(os.sep):
            mod = mod[:-1]
        if mod in self.mods:
            raise RuntimeError('Got a duplicate mod addition for {}: {}'.format(
                self.filename,
                mod,
                ))
        self.mods[mod] = ScriptFile(self.filename, mod, self.tmpdir,
                os.path.join(mod, 'content', self.filename))

    def show_diffs(self, mod, diff_command):
        """
        Show a diff from the stock/basegame script to the version in the
        specified `mod`, using `diff_command` to show the diff.
        """
        if mod.endswith(os.sep):
            mod = mod[:-1]
        cmp_to = None
        if mod == self.merged_key:
            cmp_to = self.merged
        elif mod in self.mods:
            cmp_to = self.mods[mod]
        if cmp_to:
            diff_args = list(diff_command)
            diff_args.append(self.stock.path_cached)
            diff_args.append(cmp_to.path_cached)
            subprocess.run(diff_args)
        else:
            raise RuntimeError('Could not figure out "to" path for diffs')

    def merge(self, editor=None):
        """
        Merge all mods into our single merged file (even if there's only
        one mod with a version of this file).  If `editor` is not None,
        the user will be prompted to fix the merged file.  Note that this
        only writes out to our tmpdir/cached location -- use `copy_merged_to_live`
        to copy the final file to its ultimate location.
        """
        mod_files = list(self.mods.values())

        # Just copy the first one
        with open(mod_files[0].path_cached, 'rt', encoding='utf-8') as df:
            with open(self.merged.path_cached, 'wt', encoding='utf-8') as odf:
                odf.write(df.read())

        # And now loop through the rest
        for mod_file in mod_files[1:]:
            cp = subprocess.run(['diff3', '-m',
                self.merged.path_cached,
                self.stock.path_cached,
                mod_file.path_cached,
                ], capture_output=True, encoding='utf-8')
            with open(self.merged.path_cached, 'wt', encoding='utf-8') as odf:
                odf.write(cp.stdout)
            file_data = cp.stdout
            # Was originally checking for `<<<<<<<`, and was planning on expanding that,
            # but I think mentions of our tmp directory will be a far better check
            while self.tmpdir in file_data:
                if editor is None:
                    break
                else:
                    resp = input(f' ! {mod_file.mod}: conflicts in {self.filename}.  Manually fix now [Y|n]? ')
                    resp = resp.strip()
                    if resp == '' or resp[0].lower() == 'y':
                        subprocess.run([editor, self.merged.path_cached])
                        with open(self.merged.path_cached, 'rt', encoding='utf-8') as df:
                            file_data = df.read()
                    else:
                        break
            if self.tmpdir in file_data:
                self.merge_problems = True

    def copy_merged_to_live(self):
        """
        Copies our merged file in its tmpdir/cached location to the ultimate
        in-game location (intended to be called after all mod merging has
        finished).
        """
        self.merged.copy_to_orig()

class ScriptRegistry:
    """
    Registry of all scripts found in all mods.  Intended to be used as
    a context manager using the `with `statement.
    """

    def __init__(self, witcher3_dir):
        self.witcher3_dir = witcher3_dir
        self._tmpdir = None
        self.tmpdirname = None
        self.scripts = {}
        self.mods = set()

    def __enter__(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdirname = self._tmpdir.name
        #print('Created tmpdir: {}'.format(self.tmpdirname))
        return self

    def __exit__(self, exit_type, value, traceback):
        self._tmpdir.cleanup()
        self._tmpdir = None
        self.tmpdirname = None

    def add_mod_dir(self, mod, allow_merged=False):
        """
        Adds the specified `mod` directory to the registry, creating ModScript
        objects to represent the scripts, as needed.  If `allow_merged` is `False`
        (the default), our final merged-mod directory will be ignored.  If it
        is `True`, though, we'll allow the creation of a modless entry for
        scripts we find, which will allow us to use the -d/--diff option on the
        merged mod.
        """
        if mod.endswith(os.sep):
            mod = mod[:-1]
        if mod.startswith('~') or os.sep in mod:
            raise RuntimeError('This only supports operating on mod dirs in the current directory')
        if mod in self.mods:
            raise RuntimeError(f'Duplicate mod-add detected: {mod}')
        if mod == ModScript.stock_key:
            raise RuntimeError(f'Not allowing stock key: {mod}')
        if mod == ModScript.merged_key and not allow_merged:
            # Just skip this one silently
            return
        content_prefix = f'{mod}/content/'
        content_prefix_len = len(content_prefix)
        for dirpath, _, filenames in os.walk(mod):
            for filename in filenames:
                if filename.endswith('.ws'):
                    filename_script = os.path.join(dirpath, filename)
                    if not filename_script.startswith(content_prefix):
                        raise RuntimeError(f'Does not start with expected prefix: {filename_script}')
                    filename_script = filename_script[content_prefix_len:]
                    if filename_script not in self.scripts:
                        self.scripts[filename_script] = ModScript(self.witcher3_dir, filename_script, self.tmpdirname)
                    if mod != ModScript.merged_key:
                        self.scripts[filename_script].import_from_mod(mod)
        self.mods.add(mod)

    def show_diffs(self, mod, diff_command):
        """
        Show all diff from the stock/basegame scripts to the versions in the
        specified `mod`, using `diff_command` to show the diff.
        """
        if mod.endswith(os.sep):
            mod = mod[:-1]
        if mod != ModScript.merged_key and mod not in self.mods:
            raise RuntimeError(f'Mod "{mod}" not found in registry')
        for filename, script in sorted(self.scripts.items()):
            script.show_diffs(mod, diff_command)

    def merge(self, editor=None):
        """
        Merge all scripts into our single merged dir.  If `editor` is not None,
        the user will be prompted to fix the merged file.  Copies the resulting
        mod dir to the final location.
        """

        # First do all the merges
        print('Merging mods...')
        problematic = []
        for script in self.scripts.values():
            script.merge(editor)
            if script.merge_problems:
                problematic.append(script.merged.path_orig)
        if len(self.mods) == 1:
            mod_plural = ''
        else:
            mod_plural = 's'
        if len(self.scripts) == 1:
            script_plural = ''
        else:
            script_plural = 's'
        print(' -> Merged {} mod{} with {} script{}'.format(
            len(self.mods), mod_plural,
            len(self.scripts), script_plural
            ))
        if problematic:
            if len(problematic) == 1:
                problem_plural = ''
            else:
                problem_plural = 's'
            print(' -> {} problem{} detected (manual intervention required)'.format(
                len(problematic), problem_plural,
                ))
        print('')

        # If we got here, nothing errored out, so clear out an
        # existing merged dir, if it exists
        if os.path.exists(ModScript.merged_key):
            print(f'Clearing out {ModScript.merged_key}...')
            if not os.path.isdir(ModScript.merged_key):
                raise RuntimeError(f'{ModScript.merged_key} is not a directory')
            shutil.rmtree(ModScript.merged_key)

        # ... and copy our cached area over to "live"
        print(f'Copying to {ModScript.merged_key}...')
        for script in self.scripts.values():
            script.copy_merged_to_live()

        # Report on finish
        print('Done!')
        print('')

        # Return a list of problematic files
        return sorted(problematic)

def main():

    parser = argparse.ArgumentParser(
            description='Witcher 3 CLI Mod Script Merger',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            )

    parser.add_argument('-w', '--w3dir',
            type=str,
            default='/games/Steam/steamapps/common/The Witcher 3',
            help="Base install directory for Witcher 3",
            )

    action = parser.add_mutually_exclusive_group(required=True)

    action.add_argument('-m', '--merge',
            action='store_true',
            help="Merge mods",
            )

    action.add_argument('-d', '--diff',
            type=str,
            metavar='MOD_DIR',
            help="Show diff of specified mod dir to the vanilla basegame scripts",
            )

    if 'EDITOR' in os.environ:
        default_editor = os.environ['EDITOR']
    else:
        default_editor = 'vim'
    parser.add_argument('-e', '--editor',
            type=str,
            default=default_editor,
            help="Editor to use when resolving merge conflicts",
            )

    parser.add_argument('-n', '--no-fix',
            action='store_true',
            help="Don't prompt the user to fix merge conflicts -- instead just report at the end",
            )

    parser.add_argument('--diff-command',
            type=str,
            default='diff -u --color=always',
            help="Command to use while showing diffs via the -d/--diff option",
            )

    # Parse args
    args = parser.parse_args()

    # If we're diffing a single mod, strip out any trailing directory slash
    if args.diff:
        if args.diff.endswith(os.sep):
            args.diff = args.diff[:-1]

    # Prevent anything weird in --diff-command, if we've been given it
    diff_cmd = []
    if '|' in args.diff_command \
            or '&' in args.diff_command \
            or '<' in args.diff_command \
            or '>' in args.diff_command \
            or '(' in args.diff_command \
            or ')' in args.diff_command \
            or '[' in args.diff_command \
            or ']' in args.diff_command \
            or '{' in args.diff_command \
            or '}' in args.diff_command \
            or '$' in args.diff_command \
            or '!' in args.diff_command \
            or '*' in args.diff_command \
            or '#' in args.diff_command \
            or '"' in args.diff_command \
            or "'" in args.diff_command \
            or ';' in args.diff_command:
        parser.error("Fancy shell shenanigans are not allowed in --diff-command")
    args.diff_command = shlex.split(args.diff_command)

    # Check to see if w3dir is actually a Witcher 3 dir -- if not, check to see
    # if we're running this inside the `mods` dir.
    if not os.path.exists(os.path.join(args.w3dir, 'bin', 'x64', 'witcher3.exe')):
        if os.path.exists(os.path.join('..', 'bin', 'x64', 'witcher3.exe')):
            args.w3dir = os.path.realpath('..')
            print(f'NOTICE: Using Witcher 3 install path: {args.w3dir}')
        else:
            parser.error(f'ERROR: Could not find Witcher 3 install at {args.w3dir}')

    # Now actually do something
    with ScriptRegistry(args.w3dir) as registry:
        if args.diff:
            registry.add_mod_dir(args.diff, allow_merged=True)
            registry.show_diffs(args.diff, args.diff_command)
        elif args.merge:
            for mod in sorted(os.listdir(), key=str.lower):
                if mod.startswith('mod') and os.path.isdir(os.path.realpath(mod)):
                    registry.add_mod_dir(mod)
            if args.no_fix:
                editor = None
            else:
                editor = args.editor
            problematic = registry.merge(editor)
            if problematic:
                print('Files requiring manual merge fixes:')
                print('')
                for problem in problematic:
                    print(problem)
                print('')

if __name__ == '__main__':
    main()


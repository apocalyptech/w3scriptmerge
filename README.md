Witcher 3 CLI Script Merger
===========================

Disclaimer
----------

You almost certainly want to be using the community-approved Witcher 3
[Script Merger](https://www.nexusmods.com/witcher3/mods/484) app, even
if you're running Witcher 3 on Linux, with Proton/Wine.  If you *are*
a CLI-friendly Linux user going the Proton/Wine route, though, maybe
this will be to your liking.

About
-----

This is a simple commandline-only [Python 3](https://www.python.org/)
script to merge mod scripts for the game Witcher 3.  Witcher 3 mods
often do their thing by altering various scripts bundled with the game,
which the engine compiles on startup when changed.  Once the engine
sees an overridden script in one mod, it will ignore the same
overridden script from any other mod.  So, if there are two mods
which alter the same script, only one of them will fully work.
Therefore, something like a Script Merger is needed to do that!  (For
simple cases it's easy enough to do it by hand, of course, but that
quickly grows tiresome even for a handful of mods.)

So, that's what this, and the "official" [Script Merger](https://www.nexusmods.com/witcher3/mods/484)
does.  That main merger is a GUI app which is quite featureful, and
is probably what most people want, but running Windows game utils
under Proton/Wine, when on Linux, is often a bit of a hassle, and I'm
personally happier in the commandline anyway, so I went ahead and
wrote this CLI version.

The heavy lifting in here is all done with GNU diff/diff3, so make
sure that those are available on your default `$PATH`.  (It'd be
shocking if they aren't, if you're on Linux.)  The app itself is a
single Python 3 script with no dependencies.

Installation / Usage
--------------------

Just stick `w3scriptmerge.py` in your `$PATH` somewhere (`~/bin` seems
like a good location) and run it in the same directory as your extracted
mod directories.  (This will generally be inside a `mods` directory in
the Witcher 3 install root, but the util will happily work outside that
dir, so long as the mod directories are found at the same level you are.)

The full output from the `-h`/`--help` options is as follows:

    usage: w3scriptmerge.py [-h] [-w W3DIR] (-m | -d MOD_DIR) [-e EDITOR] [-n]
                            [--diff-command DIFF_COMMAND]

    Witcher 3 CLI Mod Script Merger

    optional arguments:
      -h, --help            show this help message and exit
      -w W3DIR, --w3dir W3DIR
                            Base install directory for Witcher 3 (default:
                            /games/Steam/steamapps/common/The Witcher 3)
      -m, --merge           Merge mods (default: False)
      -d MOD_DIR, --diff MOD_DIR
                            Show diff of specified mod dir to the vanilla basegame
                            scripts (default: None)
      -e EDITOR, --editor EDITOR
                            Editor to use when resolving merge conflicts (default:
                            vim)
      -n, --no-fix          Don't prompt the user to fix merge conflicts --
                            instead just report at the end (default: False)
      --diff-command DIFF_COMMAND
                            Command to use while showing diffs via the -d/--diff
                            option (default: diff -u --color=always)

### Witcher 3 Base Dir

This script needs to know where to find the default/stock Witcher 3 scripts (or
at least, those updated via the [Community Patch](https://www.nexusmods.com/witcher3/mods/3652)),
both for merging and for showing diffs.  If you run this script from inside
Witcher 3's main `mods` directory, it will detect the script location properly.
Alternatively, you can specify the base directory with the `-w`/`--w3dir`
argument, and/or update the script with your own default, if you like.

### Merging Mods

To merge, change to a directory which contains your set of mod directories
(likely Witcher 3's main `mods` dir, though it can be anywhere), and run it
with the `-m` or `--merge` arg:

	$ w3scriptmerge.py -m
	Merging mods...
	 ! modFOVTweak: conflicts in scripts/game/player/r4Player.ws.  Manually fix now [Y|n]? y
	 -> Merged 8 mods with 15 scripts

	Clearing out mod0000_apoc_merged...
	Copying to mod0000_apoc_merged...
	Done!

If there are any files which need manual fixes due to the merging, the app
will prompt if you want to fix them.  If you agree, the script will launch
the editor specified by your `$EDITOR` environment variable (or `vim`, if
that environment var is unset), but you can override that by specifying the
`-e`/`--editor` option on the commandline.  Alternatively, you can specify
`-n`/`--no-fix` to tell the script to leave the merge as-is, and leave it
for you to fix after the fact.  If any problems remain in the merged files,
they will be reported at the end of the output.  Note that if three or more
mods create conflicts in the same script file, letting the merge problems
pile up could create an unwieldy mess.

The merge conflicts you see in the file will be very familiar to anyone
used to working with commandline file diffs, or version control systems
like git/svn/whatever where merge conflicts can pop up.  For instance, my
own conflict mentioned above us due to Natural Cat Vision and FOV Tweak
adding a bit to the same spot in the same file, and looks like this
while manually resolving:

```
<<<<<<< /tmp/tmpf6x6svik/mod0000_apoc_merged/scripts/game/player/r4Player.ws
        //++modNCV
        NCV = new CNCV in this;
        NCV.Init();
        AddTimer('CheckNCVLoop', 1.0, true);
        //--modNCV

||||||| /tmp/tmpf6x6svik/_basegame_/scripts/game/player/r4Player.ws

=======
        //modFOVTweak begin
        ModFOVTweakUpdateFOV();
        //modFOVTweak end


>>>>>>> /tmp/tmpf6x6svik/modFOVTweak/scripts/game/player/r4Player.ws
```

In that case, I want to keep both new stanzas, so I'd basically just remove
all the failed-merge notation in there: any line that starts with `<<<<<<<`,
`|||||||`, `=======`, or `>>>>>>>`.  See the `--merge` section of the
[patch(1) manpage](https://man7.org/linux/man-pages/man1/patch.1.html) or
various [git merge-conflict resolution docs](http://tedfelix.com/software/git-conflict-resolution.html)
for some details on that format, if you're not familiar with it.

Regardless, the script outputs the complete merged set of scripts into
the new mod directory `mod0000_apoc_merged`.  This will include all scripts
from all mods found in the dir, whether or not they actually required
merging.  This is one situation where its behavior might differ from the
community-approved Script Merger: that app may only write out files which
needed merging (I've never actually used it, myself, so I'm not sure).

Witcher 3 loads mods in case-insensitive ASCII sort order, with numbers first,
then underscores, then letters, so unless you have some other mod which
intentionally tries to be "first," this merged meta-mod will be loaded by W3
first.  After the engine sees all the scripts in this mod dir, all the ones
from the individual mod dirs will be ignored.  (This is also what the main
Script Merger does, though I believe its directory name is
`mod0000_MergedFiles`.)

Merged files are written out using UTF-16 encoding, just like the stock
Witcher 3 scripts.  Sometimes mods themselves haven't distributed their scripts
using that encoding, so in those cases the script in `mod0000_apoc_merged`
won't be byte-identical to the original, even if no merging needed to take
place for that file.

### Viewing diffs

The script can also be used to show the differences between the "stock"
Witcher 3 script files and the versions found in any mod directory.  To
do that, use the `-d`/`--diff` option, and specify a mod directory:

```patch
$ w3scriptmerge.py -d modGetFullXPFromQuestsNoMatterTheLevelCommunity/
--- /tmp/tmpt88qgzjt/_basegame_/scripts/game/r4Game.ws  2021-11-29 21:15:29.807520915 -0600
+++ /tmp/tmpt88qgzjt/modGetFullXPFromQuestsNoMatterTheLevelCommunity/scripts/game/r4Game.ws     2021-11-29 21:15:29.807520915 -0600
@@ -896,7 +896,7 @@
                }
                else
                {
-                       lvlDiff = rewrd.level - thePlayer.GetLevel();
+                       lvlDiff = 0;


                        if(FactsQuerySum("NewGamePlus") > 0)
```

By default, this mode calls out to the command `diff -u --color=always`, but you
can specify an alternate diff command using the `--diff-command` argument.

Uninstallation
--------------

To remove the script itself, just remove it from wherever you stored it.  To
get rid of the merged meta-mod itself, just remove the `mod0000_apoc_merged`
dir in your Witcher 3 mods dir.  Since the script doesn't alter any of the
vanilla mods, everything'll be put back in order.

TODO / Known Bugs
-----------------

 - This has only been tested on a very small subset of mods, and while it
   works great for my personal mod set, I would not be surprised if there
   are edge cases where it fails.
 - If a script in a mod uses an encoding other than UTF-16 or
   latin1/ISO-8859, the merging/processing is likely to fail.
 - Might be nice to be able to run `-m`/`--merge` from anywhere, and have
   it default to the install dir, if there aren't any mods found in the
   current dir.

License
-------

All code in here is licensed under the
[3-clause BSD license](https://opensource.org/licenses/BSD-3-Clause).
See [COPYING.txt](COPYING.txt) for the full text of the license.

Changelog
---------

 - November 30, 2021
   - Initial release
   - Tweaked failed-merge detection slightly


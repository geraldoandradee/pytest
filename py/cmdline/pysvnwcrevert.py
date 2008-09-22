#! /usr/bin/env python
"""\
py.svnwcrevert WCPATH [precious...]

Running this script and then 'svn up' puts the working copy WCPATH in a state
as clean as a fresh check-out.

WARNING: you'll loose all local changes, obviously!

This script deletes all files that have been modified
or that svn doesn't explicitly know about, including svn:ignored files
(like .pyc files, hint hint).

The goal of this script is to leave the working copy with some files and
directories possibly missing, but - most importantly - in a state where
the following 'svn up' won't just crash.

Optionally filenames that should be left untouched can be passed as arguments
too.
"""

import py

def kill(p, root):
    print '<    %s' % (p.relto(root),)
    p.remove(rec=1)

def svnwcrevert(path, root=None, precious=[]):
    if root is None:
        root = path
    wcpath = py.path.svnwc(path)
    try:
        st = wcpath.status()
    except ValueError:   # typically, "bad char in wcpath"
        kill(path, root)
        return
    for p in path.listdir():
        if p.basename == '.svn' or p.basename in precious:
            continue
        wcp = py.path.svnwc(p)
        if wcp not in st.unchanged and wcp not in st.external:
            kill(p, root)
        elif p.check(dir=1):
            svnwcrevert(p, root)


# XXX use optparse, and add a functional test 

def main():
    import sys
    if len(sys.argv) < 2:
        print __doc__
        sys.exit(2)
    svnwcrevert(py.path.local(sys.argv[1]), precious=sys.argv[1:])
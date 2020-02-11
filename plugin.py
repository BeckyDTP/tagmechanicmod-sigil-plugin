#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

from __future__ import unicode_literals, division, absolute_import, print_function

import sys

from dialogs import launch_gui
from utilities import setupPrefs


prefs = {}


def run(bk):
    # before Sigil 0.8.900 and plugin launcher 20150909, bk.selected_iter doesn't exist.
    if bk.launcher_version() < 20150909:
        print('Error: The %s plugin requires Sigil version 0.8.900 or higher.' % bk._w.plugin_name)
        return -1

    # Fail if no Text files are selected in Sigil's Book Browser
    count = 0
    for (typ, ident) in bk.selected_iter():
        if bk.id_to_mime(ident) == 'application/xhtml+xml':
            count += 1
    if not count:
        print('No text files selected in Book Browser!')
        return -1

    global prefs
    prefs = bk.getPrefs()
    prefs = setupPrefs(prefs)

    bailOut = launch_gui(bk, prefs)

    # Save prefs to back to json
    bk.savePrefs(prefs)
    if bailOut:
        print('Nothing changed.\n')
        return -1
    return 0


def main():
    return -1


if __name__ == "__main__":
    sys.exit(main())

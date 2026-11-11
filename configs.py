#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

''' Saved configurations (TagMechanicMod 0.7.0)

Each configuration is one JSON file:
    <Sigil prefs>/plugins_prefs/<plugin name>/configs/<name>.json

The keys are the same as in DiapDealer's "headless.json" proof of concept
(tag, action, attrib, srch_str, srch_method, new_tag, new_str, copy),
plus an optional "description" shown in the plugin's lists.
The file name (without .json) is the value used with SetPluginParameter
in Sigil's Automate Lists.

This module does not import Qt, so it can be used in headless runs. '''

from __future__ import unicode_literals, division, absolute_import, print_function

import os
import re
import json

from parsing_engine import MarkupParser


CONFIGS_FOLDER = 'configs'
CONFIG_EXT = '.json'

CRITERIA_KEYS = ('tag', 'action', 'attrib', 'srch_str', 'srch_method', 'new_tag', 'new_str', 'copy')

_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = re.compile(r'^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$', re.IGNORECASE)


def configs_dir(bk, create=False):
    path = os.path.join(os.path.dirname(bk._w.plugin_dir), 'plugins_prefs',
                        bk._w.plugin_name, CONFIGS_FOLDER)
    if create and not os.path.isdir(path):
        os.makedirs(path)
    return path


def valid_name(name):
    ''' Name must be usable as a file name on Windows, macOS and Linux
    and as a SetPluginParameter value (which Sigil trims). '''
    if name is None:
        return False
    if name != name.strip() or not len(name) or len(name) > 100:
        return False
    if name.endswith('.') or _BAD_CHARS.search(name) or _RESERVED.match(name):
        return False
    return True


def config_path(folder, name):
    return os.path.join(folder, name + CONFIG_EXT)


def normalize(data):
    ''' Return a clean criteria dict built from loaded JSON data.
    Missing keys get the GUI's defaults; options irrelevant to "delete" are reset. '''
    c = {
        'tag': data.get('tag'),
        'action': data.get('action'),
        'attrib': data.get('attrib') or None,
        'srch_str': data.get('srch_str') or None,
        'srch_method': data.get('srch_method') or 'normal',
        'new_tag': data.get('new_tag') or None,
        'new_str': data.get('new_str') or '',
        'copy': bool(data.get('copy', False)),
    }
    if c['attrib'] is None:
        c['srch_str'] = None
        c['srch_method'] = 'normal'
    if c['copy']:
        c['new_str'] = ''
    if c['action'] == 'delete':
        c['new_tag'] = None
        c['new_str'] = ''
        c['copy'] = False
    return c


def check_criteria(c):
    ''' None if the criteria can be run, otherwise an error key
    (same rules as the plugin's main window). '''
    if not isinstance(c.get('tag'), str) or not c['tag'].strip():
        return 'bad_tag'
    if c.get('action') not in ('delete', 'modify'):
        return 'bad_action'
    if c.get('srch_method') not in ('normal', 'regex'):
        return 'bad_method'
    for key in ('attrib', 'srch_str', 'new_tag'):
        if c.get(key) is not None and not isinstance(c[key], str):
            return 'bad_value'
    if not isinstance(c.get('new_str'), str):
        return 'bad_value'
    if c['attrib'] is not None and c['srch_str'] is None:
        return 'no_value'
    if c['srch_method'] == 'regex':
        try:
            re.compile(c['srch_str'])
        except Exception:
            return 'bad_regex'
    if c['action'] == 'modify' and c['new_tag'] is None and c['copy']:
        return 'pointless'
    return None


ERRORS_EN = {
    'bad_tag': 'No tag name given',
    'bad_action': 'Action must be "delete" or "modify"',
    'bad_method': 'srch_method must be "normal" or "regex"',
    'bad_value': 'Wrong value type in configuration',
    'no_value': 'Must enter a value for the attribute selected',
    'bad_regex': 'Invalid regular expression',
    'pointless': 'What--exactly--would that achieve?',
    'not_found': 'Configuration file not found',
    'bad_json': 'Configuration file is not valid JSON',
    'bad_name': 'Invalid configuration name',
}


def load_config(folder, name):
    ''' Returns (criteria, description, error_key). '''
    if not valid_name(name):
        return None, '', 'bad_name'
    path = config_path(folder, name)
    if not os.path.isfile(path):
        return None, '', 'not_found'
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except Exception:
        return None, '', 'bad_json'
    if not isinstance(data, dict):
        return None, '', 'bad_json'
    description = data.get('description') or ''
    if not isinstance(description, str):
        description = str(description)
    criteria = normalize(data)
    return criteria, description.strip(), check_criteria(criteria)


def list_configs(folder):
    ''' Returns a list of dicts: name, description, criteria, error,
    sorted by the text shown to the user (description, or name if none). '''
    result = []
    if not os.path.isdir(folder):
        return result
    for fname in os.listdir(folder):
        if not fname.lower().endswith(CONFIG_EXT):
            continue
        name = fname[:-len(CONFIG_EXT)]
        if not valid_name(name):
            continue
        criteria, description, error = load_config(folder, name)
        result.append({'name': name, 'description': description,
                       'criteria': criteria, 'error': error})
    result.sort(key=lambda x: ((x['description'] or x['name']).casefold(), x['name'].casefold()))
    return result


def save_config(folder, name, criteria, description=''):
    if not os.path.isdir(folder):
        os.makedirs(folder)
    data = {}
    description = (description or '').strip()
    if description:
        data['description'] = description
    for key in CRITERIA_KEYS:
        data[key] = criteria[key]
    tmp = config_path(folder, name) + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    os.replace(tmp, config_path(folder, name))


def delete_config(folder, name):
    path = config_path(folder, name)
    if os.path.isfile(path):
        os.remove(path)


def get_file_list(bk):
    ''' Text files selected in Book Browser, or all text files if none selected.
    Returns (list of ids, True if selection was used). '''
    selected = []
    for (typ, ident) in bk.selected_iter():
        if bk.id_to_mime(ident) == 'application/xhtml+xml':
            selected.append(ident)
    if selected:
        return selected, True
    return [ident for (ident, href) in bk.text_iter()], False


def process_files(bk, file_ids, criteria, report):
    ''' Run the parser over the files; write changed ones back.
    report(kind, href, count) is called with kind 'error', 'changed' or 'notfound'.
    Returns the total number of occurrences changed. '''
    totals = 0
    for ident in file_ids:
        href = bk.id_to_href(ident)
        crit = dict(criteria)
        crit['html'] = bk.readfile(ident)
        if not isinstance(crit['html'], str):
            crit['html'] = str(crit['html'], 'utf-8')
        parser = MarkupParser(crit)
        try:
            html, occurrences = parser.processml()
        except Exception:
            report('error', href, 0)
            continue
        totals += occurrences
        if occurrences:
            bk.writefile(ident, html)
            report('changed', href, int(occurrences))
        else:
            report('notfound', href, 0)
    return totals


def run_headless(bk, name):
    ''' Automate List run: SetPluginParameter <name> followed by the plugin. '''
    folder = configs_dir(bk)
    criteria, description, error = load_config(folder, name)
    if error is not None:
        print('{}: {} ({})'.format(ERRORS_EN.get(error, error), name, config_path(folder, name)))
        return -1
    print('Configuration: {}{}'.format(name, ' - ' + description if description else ''))
    file_ids, used_selection = get_file_list(bk)
    print('Processing selected files...' if used_selection else 'Processing all files...')

    def report(kind, href, count):
        if kind == 'error':
            print('Error parsing {}! File skipped.'.format(href))
        elif kind == 'changed':
            print('Occurrences found/changed in {}:   {}'.format(href, count))
        else:
            print('Criteria not found in {}'.format(href))

    totals = process_files(bk, file_ids, criteria, report)
    if totals:
        print('Total occurrences found/changed: {}'.format(int(totals)))
    else:
        print('No changes made to book')
    return 0

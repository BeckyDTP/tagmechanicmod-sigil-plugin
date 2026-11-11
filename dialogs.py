#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab

from __future__ import unicode_literals, division, absolute_import, print_function

import os
import sys
import math

from utilities import UpdateChecker, taglist, combobox_defaults, remove_dupes
from configs import (configs_dir, list_configs, save_config, delete_config,
                     valid_name, get_file_list, process_files)

from plugin_utils import Qt, QtCore, QtGui, QtWidgets, QAction
from plugin_utils import PluginApplication, iswindows, _t  # , Signal, Slot, loadUi


DEBUG = 1
if DEBUG:
    if 'PySide6' in sys.modules:
        print('Plugin using PySide6')
    else:
        print('Plugin using PyQt5')

BAIL_OUT = False
PROCESSED = False


def launch_gui(bk, prefs):
    # Becky START
    global file_list
    global selectedallmessage
    global selectedallmessagekolor

    # Selected text files, or all text files if none selected
    file_list, used_selection = get_file_list(bk)
    # Becky END

    icon = os.path.join(bk._w.plugin_dir, bk._w.plugin_name, 'plugin.svg')
    mdp = True if iswindows else False
    app = PluginApplication(sys.argv, bk, app_icon=icon, match_dark_palette=mdp,
                            dont_use_native_menubars=True)

    # Becky START
    if used_selection:
        selectedallmessage = _t('guiMain', 'Processing selected files...')
        selectedallmessagekolor = 'QLabel {color: #2ECC72;}'
    else:
        selectedallmessage = _t('guiMain', 'Processing all files...')
        selectedallmessagekolor = 'QLabel {color: #BE1055;}'
    # Becky END

    # Becky 0.7.0: quick window with saved configurations
    initial_config = None
    if prefs['miscellaneous_settings']['quick_start']:
        entries = list_configs(configs_dir(bk))
        if entries:
            dlg = QuickRunDialog(bk, prefs, entries)
            dlg.exec()
            if dlg.outcome != 'open_full':
                return dlg.outcome != 'commit'
            initial_config = dlg.selected_name()

    win = guiMain(bk, prefs, initial_config)
    # Use exec() and not exec_() for PyQt5/PySide6 compliance
    app.exec()
    return win.getAbort()


# Becky 0.7.0 START - helpers for saved configurations
def criteria_error_message(key):
    messages = {
        'bad_tag': _t('guiMain', 'No tag name given'),
        'bad_action': _t('guiMain', 'Action must be "delete" or "modify"'),
        'bad_method': _t('guiMain', 'Search method must be "normal" or "regex"'),
        'bad_value': _t('guiMain', 'Wrong value type in configuration'),
        'no_value': _t('guiMain', 'Must enter a value for the attribute selected'),
        'bad_regex': _t('guiMain', 'Invalid regular expression'),
        'pointless': _t('guiMain', 'What--exactly--would that achieve?'),
        'not_found': _t('guiMain', 'Configuration file not found'),
        'bad_json': _t('guiMain', 'Configuration file is not valid JSON'),
        'bad_name': _t('guiMain', 'Invalid configuration name'),
        'bad_tag_list': _t('guiMain', 'This tag is not on the plugin\'s tag list'),
    }
    return messages.get(key, key)


def html_escape(text):
    return (text.replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def entry_text(entry):
    return entry['description'] or entry['name']


def fill_config_combo(combo, entries, placeholder=None):
    ''' Fill a QComboBox with saved configurations; the name is stored as item data. '''
    combo.clear()
    if placeholder is not None:
        combo.addItem(placeholder, None)
    for entry in entries:
        text = entry_text(entry)
        if entry['error'] is not None:
            text = '{}  [!]'.format(text)
        combo.addItem(text, entry['name'])
        tip = '{} {}.json'.format(_t('guiMain', 'File:'), html_escape(entry['name']))
        if entry['description']:
            tip = '<p><b>{}</b><br>{}'.format(html_escape(entry['description']), tip)
        else:
            tip = '<p>' + tip
        if entry['error'] is not None:
            tip += '<br><span style="color: #BE1055;">{}</span>'.format(
                html_escape(criteria_error_message(entry['error'])))
        combo.setItemData(combo.count() - 1, tip, Qt.ToolTipRole)


def describe_criteria(c):
    ''' Short HTML summary of a configuration (uses the main window's labels). '''
    rows = []
    action = _t('guiMain', 'Delete') if c['action'] == 'delete' else _t('guiMain', 'Modify')
    rows.append((_t('guiMain', 'Action type:'), html_escape(action)))
    rows.append((_t('guiMain', 'Tag name:'), '&lt;{}&gt;'.format(html_escape(c['tag']))))
    if c['attrib'] is None:
        attr = html_escape(_t('guiMain', 'No attributes (naked tag)'))
    else:
        attr = '{} = <code>{}</code>'.format(html_escape(c['attrib']), html_escape(c['srch_str'] or ''))
        if c['srch_method'] == 'regex':
            attr += ' ({})'.format(html_escape(_t('guiMain', 'Regex')))
    rows.append((_t('guiMain', 'Having the attribute:'), attr))
    if c['action'] == 'modify':
        new_tag = html_escape(_t('guiMain', 'No change')) if c['new_tag'] is None else '&lt;{}&gt;'.format(html_escape(c['new_tag']))
        rows.append((_t('guiMain', 'Change tag to:'), new_tag))
        if c['copy']:
            rows.append((_t('guiMain', 'New attribute string to insert (entire):'),
                         html_escape(_t('guiMain', 'Copy existing attribute string'))))
        else:
            rows.append((_t('guiMain', 'New attribute string to insert (entire):'),
                         '<code>{}</code>'.format(html_escape(c['new_str'])) if c['new_str'] else '&#8212;'))
    html = '<table cellspacing="2">'
    for label, value in rows:
        html += '<tr><td style="padding-right: 8px;">{}</td><td>{}</td></tr>'.format(html_escape(label), value)
    return html + '</table>'


def report_to_panel(panel):
    ''' Returns a report() callback for configs.process_files writing to a QTextEdit. '''
    def report(kind, href, count):
        if kind == 'error':
            panel.insertHtml('<p>{} {}! {}.<br></p>'.format(
                _t('guiMain', 'Error parsing'), href, _t('guiMain', 'File skipped')))
        elif kind == 'changed':
            panel.insertHtml('<p>{} {}:&#160;&#160;&#160;{}</p>\n'.format(
                _t('guiMain', 'Occurrences found/changed in'), href, count))
        else:
            panel.insertHtml('<p style="color: #BE1055;">{} {}</p>\n'.format(
                _t('guiMain', 'Criteria not found in'), href))
        panel.insertPlainText('\n')
    return report


class SaveConfigDialog(QtWidgets.QDialog):
    ''' Asks for the name (file name / Automate parameter) and the description. '''
    def __init__(self, parent, name, description, existing_names):
        super(SaveConfigDialog, self).__init__(parent)
        self.original_name = name or ''
        self.existing = {n.casefold(): n for n in existing_names}
        self.setWindowTitle(_t('SaveConfigDialog', 'Save configuration'))
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        form = QtWidgets.QFormLayout()
        layout.addLayout(form)
        self.desc_txt = QtWidgets.QLineEdit(description or '', self)
        self.desc_txt.setToolTip('<p>{}'.format(
            _t('SaveConfigDialog', 'Shown in the list of saved configurations.')))
        form.addRow(_t('SaveConfigDialog', 'Description:'), self.desc_txt)
        self.name_txt = QtWidgets.QLineEdit(self.original_name, self)
        self.name_txt.setToolTip('<p>{}'.format(
            _t('SaveConfigDialog', 'File name (without .json). No characters: \\ / : * ? &quot; &lt; &gt; |')))
        form.addRow(_t('SaveConfigDialog', 'Name:'), self.name_txt)

        self.hint = QtWidgets.QLabel(self)
        self.hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.name_txt.textChanged.connect(self.update_hint)
        self.update_hint()

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.check_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        self.setMinimumWidth(460)
        if self.desc_txt.text():
            self.name_txt.setFocus()

    def update_hint(self):
        name = self.name_txt.text().strip()
        self.hint.setText('{}<br><code>SetPluginParameter {}</code>'.format(
            html_escape(_t('SaveConfigDialog', 'Use in an Automate List:')), html_escape(name or '...')))

    def name(self):
        return self.name_txt.text().strip()

    def description(self):
        return self.desc_txt.text().strip()

    def check_and_accept(self):
        name = self.name()
        if not valid_name(name):
            msg = '<p>{}<p>{}'.format(
                _t('guiMain', 'Invalid configuration name'),
                _t('SaveConfigDialog', 'File name (without .json). No characters: \\ / : * ? &quot; &lt; &gt; |'))
            QtWidgets.QMessageBox.warning(self, _t('guiMain', 'Error'), msg, QtWidgets.QMessageBox.Ok)
            return
        existing = self.existing.get(name.casefold())
        if existing is not None and existing.casefold() != self.original_name.casefold():
            msg = '<p>{} <b>{}</b>. {}'.format(
                _t('SaveConfigDialog', 'A configuration with this name already exists:'), html_escape(existing),
                _t('SaveConfigDialog', 'Replace it?'))
            if QtWidgets.QMessageBox.question(self, _t('ConfigDialog', 'Are you sure?'), msg,
                                              QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel) != QtWidgets.QMessageBox.Yes:
                return
        self.accept()


class QuickRunDialog(QtWidgets.QDialog):
    ''' Shown at start (if enabled): pick a saved configuration and run it,
    as many times / configurations as needed, then commit or abort. '''
    def __init__(self, bk, prefs, entries):
        super(QuickRunDialog, self).__init__()
        self.bk = bk
        self.misc_prefs = prefs['miscellaneous_settings']
        self.entries = {e['name']: e for e in entries}
        self.outcome = 'abort'
        self.totals = 0
        self.setWindowTitle(_t('QuickRunDialog', 'Tag Mechanic - saved configurations') + ' MOD')
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        label = QtWidgets.QLabel(selectedallmessage, self)
        font = QtGui.QFont()
        font.setPointSize(14)
        label.setFont(font)
        label.setStyleSheet(selectedallmessagekolor)
        layout.addWidget(label)

        combo_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(combo_layout)
        combo_layout.addWidget(QtWidgets.QLabel(_t('guiMain', 'Saved configuration:'), self))
        self.config_combo = QtWidgets.QComboBox(self)
        self.config_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        combo_layout.addWidget(self.config_combo, 1)
        fill_config_combo(self.config_combo, entries)
        last = self.misc_prefs['last_config']
        if last is not None:
            idx = self.config_combo.findData(last)
            if idx >= 0:
                self.config_combo.setCurrentIndex(idx)
        self.config_combo.currentIndexChanged.connect(self.update_summary)

        self.summary = QtWidgets.QLabel(self)
        self.summary.setTextFormat(Qt.RichText)
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.summary.setMargin(6)
        layout.addWidget(self.summary)

        self.text_panel = QtWidgets.QTextEdit(self)
        self.text_panel.setReadOnly(True)
        layout.addWidget(self.text_panel, 1)

        button_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(button_layout)
        self.process_button = QtWidgets.QPushButton(_t('guiMain', 'Process'), self)
        self.process_button.setToolTip('<p>{}'.format(
            _t('QuickRunDialog', 'Run the selected configuration. You can run more configurations one after another.')))
        self.process_button.clicked.connect(self._process_clicked)
        button_layout.addWidget(self.process_button)
        self.full_button = QtWidgets.QPushButton(_t('QuickRunDialog', 'Open in main window'), self)
        self.full_button.setToolTip('<p>{}'.format(
            _t('QuickRunDialog', 'Open the full plugin window with the selected configuration loaded')))
        self.full_button.clicked.connect(self._full_clicked)
        button_layout.addWidget(self.full_button)
        self.abort_button = QtWidgets.QPushButton(_t('guiMain', 'Abort Changes'), self)
        self.abort_button.setToolTip('<p>{}'.format(_t('guiMain', 'Make no changes and exit')))
        self.abort_button.clicked.connect(self._abort_clicked)
        self.abort_button.setDisabled(True)
        button_layout.addWidget(self.abort_button)
        self.quit_button = QtWidgets.QPushButton(_t('guiMain', 'Quit'), self)
        self.quit_button.setToolTip('<p>{}'.format(_t('guiMain', 'Quit with no changes')))
        self.quit_button.clicked.connect(self._quit_clicked)
        button_layout.addWidget(self.quit_button)
        for b in (self.process_button, self.full_button, self.abort_button, self.quit_button):
            b.setAutoDefault(False)
            b.setDefault(False)

        geometry = self.misc_prefs.get('quickGeometry')
        restored = False
        if geometry:
            try:
                restored = self.restoreGeometry(QtCore.QByteArray.fromHex(geometry.encode('ascii')))
            except Exception:
                restored = False
        if not restored:
            self.resize(620, 520)
        self.update_summary()

    def selected_name(self):
        return self.config_combo.currentData()

    def update_summary(self):
        entry = self.entries.get(self.selected_name())
        if entry is None:
            self.summary.setText('')
        elif entry['error'] is not None:
            self.summary.setText('<span style="color: #BE1055;">{}</span>'.format(
                html_escape(criteria_error_message(entry['error']))))
        else:
            self.summary.setText(describe_criteria(entry['criteria']))
        self.process_button.setDisabled(entry is None or entry['error'] is not None)

    def _process_clicked(self):
        entry = self.entries.get(self.selected_name())
        if entry is None or entry['error'] is not None:
            return
        self.misc_prefs['last_config'] = entry['name']
        self.process_button.setDisabled(True)
        PluginApplication.setOverrideCursor(Qt.WaitCursor)
        totals = 0
        try:
            self.text_panel.moveCursor(QtGui.QTextCursor.End)
            self.text_panel.insertHtml('<h4>{}...&#160;&#160;{}</h4><br>'.format(
                _t('guiMain', 'Starting'), html_escape(entry_text(entry))))
            totals = process_files(self.bk, file_list, entry['criteria'], report_to_panel(self.text_panel))
            if totals:
                self.text_panel.insertHtml('<h4><br>{}:&#160;&#160;&#160;{}</h4>'.format(
                    _t('guiMain', 'Total occurrences found/changed'), int(totals)))
            else:
                self.text_panel.insertHtml('<br><h4>{}</h4>'.format(_t('guiMain', 'No changes made to book')))
            self.text_panel.insertHtml('<br><h4>{}</h4><hr><br>'.format(_t('guiMain', 'Finished')))
            self.text_panel.moveCursor(QtGui.QTextCursor.End)
            self.text_panel.ensureCursorVisible()
        finally:
            PluginApplication.restoreOverrideCursor()
            self.process_button.setDisabled(False)
        self.totals += totals
        if self.totals:
            self.full_button.setDisabled(True)
            self.abort_button.setDisabled(False)
            self.quit_button.setText(_t('guiMain', 'Commit and Exit'))
            self.quit_button.setToolTip('<p>{}'.format(_t('guiMain', 'Commit all changes and exit')))

    def _save_geometry(self):
        self.misc_prefs['quickGeometry'] = self.saveGeometry().toHex().data().decode('ascii')

    def _full_clicked(self):
        self.outcome = 'open_full'
        self._save_geometry()
        self.accept()

    def _quit_clicked(self):
        self.outcome = 'commit' if self.totals else 'abort'
        self._save_geometry()
        self.accept()

    def _abort_clicked(self):
        self.outcome = 'abort'
        self._save_geometry()
        self.accept()

    def reject(self):
        # Esc key or window close button: never lose changes without asking
        if self.totals:
            msg = '<p>{}'.format(_t('QuickRunDialog', 'Abort all changes made in this session?'))
            if QtWidgets.QMessageBox.question(self, _t('ConfigDialog', 'Are you sure?'), msg,
                                              QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel) != QtWidgets.QMessageBox.Yes:
                return
        self.outcome = 'abort'
        self._save_geometry()
        super(QuickRunDialog, self).reject()
# Becky 0.7.0 END


class ConfigDialog(QtWidgets.QDialog):
    def __init__(self, parent, combobox_values):
        super(ConfigDialog, self).__init__()
        self.gui = parent
        self.combobox_values = combobox_values
        self.qlinedit_widgets = {}
        self.setup_ui()
        self.setWindowTitle(_t('ConfigDialog', 'Customize Tag Mechanic') + ' MOD')

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)
        columns_frame = QtWidgets.QHBoxLayout()
        layout.addLayout(columns_frame)

        # How many columns of nine items each will it take to display
        # a text box for each tag in taglist?
        col_limit = 8
        num_cols = len(taglist)/col_limit
        num_cols = int(math.ceil(num_cols))

        # If the column limit and the number of columns produces a single
        # orphan text entry widget, reduce the column limit accordingly.
        if num_cols > 1 and (len(taglist) - ((num_cols - 1)*col_limit)) < 2:
            if num_cols >= 3:
                col_limit -= 1
        # Create an integer-indexed dictionary of QVBoxLayouts representing the number of
        # columns necessary. Added left to right in the parent QHBoxLayout.
        column = {}
        for i in range(1, num_cols+1):
            column[i] = QtWidgets.QVBoxLayout()
            column[i].setAlignment(Qt.AlignLeft)
            columns_frame.addLayout(column[i])

        # Create a dictionary of QLineEdit widgets (indexed by tag name) and stack them
        # (top to bottom) and their labels in as many columns as it takes.
        curr_col = 1
        curr_item = 1
        tooltip = _t('ConfigDialog', 'Comma separated list of html elements (no quotes, no angle "&lt;" brackets).')
        for tag in taglist:
            # Column item limit surpassed - switch to next column.
            if curr_item > col_limit:
                column[curr_col].addStretch()
                curr_col += 1
                curr_item = 1
            # Add lable and QLineEdit widget to current column.
            label = QtWidgets.QLabel('{} "{}" {}'.format(
                _t('ConfigDialog', 'Choices to change'), tag,
                _t('ConfigDialog', 'elements to:')), self)
            label.setAlignment(Qt.AlignCenter)
            self.qlinedit_widgets[tag] = QtWidgets.QLineEdit(', '.join(self.combobox_values['{}_changes'.format(tag)]), self)
            self.qlinedit_widgets[tag].setToolTip('<p>{}'.format(tooltip))
            column[curr_col].addWidget(label)
            column[curr_col].addWidget(self.qlinedit_widgets[tag])

            if not len(self.combobox_values['{}_changes'.format(tag)]):
                self.qlinedit_widgets[tag].setDisabled(True)
            curr_item += 1
        column[curr_col].addStretch()

        layout.addSpacing(10)
        attrs_layout = QtWidgets.QVBoxLayout()
        attrs_layout.setAlignment(Qt.AlignCenter)
        layout.addLayout(attrs_layout)
        label = QtWidgets.QLabel(_t('ConfigDialog', 'HTML attributes available to search for:'), self)
        label.setAlignment(Qt.AlignCenter)
        self.attrs_txtBox = QtWidgets.QLineEdit(', '.join(self.combobox_values['attrs']), self)
        self.attrs_txtBox.setToolTip('<p>{}'.format(
            _t('ConfigDialog', 'Comma separated list of html attribute names (no quotes).')))
        attrs_layout.addWidget(label)
        attrs_layout.addWidget(self.attrs_txtBox)

        layout.addSpacing(10)
        right_layout = QtWidgets.QHBoxLayout()
        right_layout.setAlignment(Qt.AlignRight)
        layout.addLayout(right_layout)

        # Becky 0.7.0
        self.quick_start = QtWidgets.QCheckBox(_t('ConfigDialog', 'At start, show the quick window with saved configurations'), self)
        self.quick_start.setToolTip('<p>{}'.format(
            _t('ConfigDialog', 'Choose a saved configuration and run it without the main window. Works when at least one configuration is saved.')))
        self.quick_start.setChecked(self.gui.misc_prefs['quick_start'])
        right_layout.addWidget(self.quick_start)
        right_layout.addSpacing(30)

        reset_button = QtWidgets.QPushButton(_t('ConfigDialog', 'Reset all defaults'), self)
        reset_button.setToolTip('<p>{}'.format(_t('ConfigDialog', 'Reset all settings to original defaults.')))
        reset_button.clicked.connect(self.reset_defaults)
        right_layout.addWidget(reset_button)

        layout.addSpacing(10)
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def save_settings(self):
        # Save current dialog sttings back to JSON config file
        for tag in taglist:
            tmp_list = str(self.qlinedit_widgets[tag].displayText()).split(',')
            tmp_list = remove_dupes([x.strip(' ') for x in tmp_list])
            self.combobox_values['{}_changes'.format(tag)] = list(filter(None, tmp_list))

        tmp_list = str(self.attrs_txtBox.displayText()).split(',')
        tmp_list = remove_dupes([x.strip(' ') for x in tmp_list])
        self.combobox_values['attrs'] = list(filter(None, tmp_list))
        self.gui.misc_prefs['quick_start'] = self.quick_start.isChecked()
        self.accept()

    def reset_defaults(self):
        caption= _t('ConfigDialog', 'Are you sure?')
        msg = '<p>{}'.format(_t('ConfigDialog', 'Reset all customizable options to their original defaults?'))
        if QtWidgets.QMessageBox.question(self, caption, msg, QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel) == QtWidgets.QMessageBox.Yes:
            for tag in taglist:
                self.combobox_values['{}_changes'.format(tag)] = combobox_defaults['{}_changes'.format(tag)]
            self.combobox_values['attrs'] = combobox_defaults['attrs']
            self.gui.misc_prefs['quick_start'] = False
            self.accept()


class guiMain(QtWidgets.QMainWindow):
    def __init__(self, bk, prefs, initial_config=None):
        super(guiMain, self).__init__()
        self.taglist = taglist
        # Edit Plugin container object
        self.bk = bk

        # Handy prefs groupings
        self.gui_prefs = prefs['gui_selections']
        self.misc_prefs = prefs['miscellaneous_settings']
        self.update_prefs = prefs['update_settings']
        self.combobox_values = prefs['combobox_values']

        self._ok_to_close = False
        # Becky 0.7.0: saved configurations
        self.config_folder = configs_dir(bk)
        self.config_entries = []
        self.extra_attrs = []
        # Check online github files for newer version
        self.update, self.newversion = self.check_for_update()
        self.setup_ui()
        if initial_config is not None:
            idx = self.config_combo.findData(initial_config)
            if idx > 0:
                self.config_combo.setCurrentIndex(idx)
                self.config_selected(idx)

    def setup_ui(self):
        app = PluginApplication.instance()
        p = app.palette()
        link_color = p.color(QtGui.QPalette.Active, QtGui.QPalette.Link).name()

        DELETE_STR = _t('guiMain', 'Delete')
        MODIFY_STR = _t('guiMain', 'Modify')
        self.NO_ATTRIB_STR = _t('guiMain', 'No attributes (naked tag)')
        self.NO_CHANGE_STR = _t('guiMain', 'No change')
        # Becky START
        self.setWindowTitle(_t('guiMain', 'Tag Mechanic') + ' MOD')
        # Becky END

        configAct = QAction(_t('guiMain', 'Config'), self)
        configAct.setShortcut('Ctrl+Alt+C')
        tooltip = _t('guiMain','Configure')
        configAct.setToolTip(tooltip + ' ' + self.bk._w.plugin_name)
        icon = os.path.join(self.bk._w.plugin_dir, self.bk._w.plugin_name, 'config.svg')
        configAct.setIcon(QtGui.QIcon(icon))
        configAct.triggered.connect(self.showConfig)

        editToolBar = self.addToolBar(_t('guiMain', 'Edit'))
        editToolBar.setMovable(False)
        editToolBar.setFloatable(False)
        editToolBar.setContextMenuPolicy(Qt.PreventContextMenu)
        editToolBar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        editToolBar.addAction(configAct)

        layout = QtWidgets.QVBoxLayout()

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        # Becky START
        if self.update:
            update_layout = QtWidgets.QHBoxLayout()
            layout.addLayout(update_layout)
            self.label = QtWidgets.QLabel()
            self.label.setText(_t('guiMain', 'Plugin Update Available') + ' ' + str(self.newversion))
            self.label.setStyleSheet('QLabel {{color: {};}}'.format(link_color))
            update_layout.addWidget(self.label)

        file_list_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(file_list_layout)
        self.label = QtWidgets.QLabel()
        font = QtGui.QFont()
        font.setPointSize(14)
        self.label.setFont(font)
        self.label.setText(selectedallmessage)
        self.label.setStyleSheet(selectedallmessagekolor)
        file_list_layout.addWidget(self.label)
        # Becky END

        # Becky 0.7.0 START
        config_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(config_layout)
        label = QtWidgets.QLabel(_t('guiMain', 'Saved configuration:'), self)
        config_layout.addWidget(label)
        self.config_combo = QtWidgets.QComboBox()
        self.config_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.config_combo.setToolTip('<p>{}'.format(
            _t('guiMain', 'Selecting a saved configuration fills in the fields below')))
        config_layout.addWidget(self.config_combo, 1)
        self.save_config_button = QtWidgets.QPushButton(_t('guiMain', 'Save...'), self)
        self.save_config_button.setToolTip('<p>{}'.format(
            _t('guiMain', 'Save the current settings as a configuration (also for Automate Lists)')))
        self.save_config_button.clicked.connect(self._save_config_clicked)
        config_layout.addWidget(self.save_config_button)
        self.delete_config_button = QtWidgets.QPushButton(_t('guiMain', 'Delete'), self)
        self.delete_config_button.setToolTip('<p>{}'.format(
            _t('guiMain', 'Delete the selected saved configuration')))
        self.delete_config_button.clicked.connect(self._delete_config_clicked)
        config_layout.addWidget(self.delete_config_button)
        self.refresh_configs()
        self.config_combo.activated.connect(self.config_selected)
        layout.addSpacing(6)
        # Becky 0.7.0 END

        action_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(action_layout)
        label = QtWidgets.QLabel(_t('guiMain', 'Action type:'), self)
        action_layout.addWidget(label)
        self.action_combo = QtWidgets.QComboBox()
        action_layout.addWidget(self.action_combo)
        self.action_combo.addItems([DELETE_STR, MODIFY_STR])
        self.action_combo.setCurrentIndex(self.gui_prefs['action'])
        self.action_combo.currentIndexChanged.connect(self.update_gui)

        tag_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(tag_layout)
        label = QtWidgets.QLabel(_t('guiMain', 'Tag name:'), self)
        tag_layout.addWidget(label)
        self.tag_combo = QtWidgets.QComboBox()
        tag_layout.addWidget(self.tag_combo)
        self.tag_combo.addItems(self.taglist)
        self.tag_combo.setCurrentIndex(self.gui_prefs['tag'])
        self.tag_combo.currentIndexChanged.connect(self.update_gui)

        attr_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(attr_layout)
        label = QtWidgets.QLabel(_t('guiMain', 'Having the attribute:'), self)
        attr_layout.addWidget(label)
        self.attr_combo = QtWidgets.QComboBox()
        attr_layout.addWidget(self.attr_combo)
        self.attr_combo.addItems(self.combobox_values['attrs'])
        self.attr_combo.addItem(self.NO_ATTRIB_STR)
        self.attr_combo.setCurrentIndex(self.gui_prefs['attrs'])
        self.attr_combo.currentIndexChanged.connect(self.update_gui)

        srch_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(srch_layout)
        label = QtWidgets.QLabel(_t('guiMain', 'Whose value is (no quotes):'), self)
        srch_layout.addWidget(label)
        self.srch_txt = QtWidgets.QLineEdit('', self)
        srch_layout.addWidget(self.srch_txt)
        self.srch_method = QtWidgets.QCheckBox(_t('guiMain', 'Regex'), self)
        srch_layout.addWidget(self.srch_method)

        newtag_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(newtag_layout)
        label = QtWidgets.QLabel(_t('guiMain', 'Change tag to:'), self)
        newtag_layout.addWidget(label)
        self.newtag_combo = QtWidgets.QComboBox()
        newtag_layout.addWidget(self.newtag_combo)

        self.newtag_combo.addItem(self.NO_CHANGE_STR)
        self.newtag_combo.addItems(self.combobox_values['{}_changes'.format(str(self.tag_combo.currentText()))])

        if self.action_combo.currentIndex() == 0:
            self.newtag_combo.setDisabled(True)

        newattr_layout = QtWidgets.QVBoxLayout()
        layout.addLayout(newattr_layout)
        label = QtWidgets.QLabel(_t('guiMain', 'New attribute string to insert (entire):'), self)
        newattr_layout.addWidget(label)
        self.newattr_txt = QtWidgets.QLineEdit('', self)
        newattr_layout.addWidget(self.newattr_txt)
        self.copy_attr = QtWidgets.QCheckBox(_t('guiMain', 'Copy existing attribute string'), self)
        self.copy_attr.stateChanged.connect(self.update_txt_box)
        newattr_layout.addWidget(self.copy_attr)
        if self.action_combo.currentIndex() == 0:
            self.copy_attr.setDisabled(True)
            self.newattr_txt.setDisabled(True)

        layout.addSpacing(10)
        self.text_panel = QtWidgets.QTextEdit()
        self.text_panel.setReadOnly(True)
        layout.addWidget(self.text_panel)

        layout.addSpacing(10)
        button_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(button_layout)
        self.process_button = QtWidgets.QPushButton(_t('guiMain', 'Process'), self)
        self.process_button.setToolTip('<p>{}'.format(_t('guiMain', 'Process selected files with current criteria')))
        self.process_button.clicked.connect(self._process_clicked)
        button_layout.addWidget(self.process_button)

        self.abort_button = QtWidgets.QPushButton(_t('guiMain', 'Abort Changes'), self)
        self.abort_button.setToolTip('<p>{}'.format(_t('guiMain', 'Make no changes and exit')))
        self.abort_button.clicked.connect(self._abort_clicked)
        self.abort_button.setDisabled(True)
        button_layout.addWidget(self.abort_button)

        self.quit_button = QtWidgets.QPushButton(_t('guiMain', 'Quit'), self)
        self.quit_button.setToolTip('<p>{}'.format(_t('guiMain', 'Quit with no changes')))
        self.quit_button.clicked.connect(self._quit_clicked)
        button_layout.addWidget(self.quit_button)

        if self.misc_prefs['windowGeometry'] is not None:
            try:
                self.restoreGeometry(QtCore.QByteArray.fromHex(self.misc_prefs['windowGeometry'].encode('ascii')))
            except Exception:
                pass
        self.show()

    def update_gui(self):
        if self.attr_combo.currentIndex() == self.attr_combo.count()-1:
            self.srch_txt.clear()
            self.srch_txt.setDisabled(True)
            self.srch_method.setChecked(False)
            self.srch_method.setDisabled(True)
        else:
            self.srch_txt.setDisabled(False)
            self.srch_method.setDisabled(False)

        self.newtag_combo.clear()
        self.newtag_combo.addItem(self.NO_CHANGE_STR)
        self.newtag_combo.addItems(self.combobox_values['{}_changes'.format(str(self.tag_combo.currentText()))])

        if self.action_combo.currentIndex() == 0:
            self.newtag_combo.setCurrentIndex(0)
            self.newtag_combo.setDisabled(True)
            self.newattr_txt.clear()
            self.newattr_txt.setDisabled(True)
            self.copy_attr.setChecked(False)
            self.copy_attr.setDisabled(True)
        else:
            self.newtag_combo.setDisabled(False)
            self.newattr_txt.setDisabled(False)
            self.copy_attr.setDisabled(False)

        self.update_txt_box()

    def update_txt_box(self):
        if self.copy_attr.isChecked() or not self.copy_attr.isEnabled():
            self.newattr_txt.clear()
            self.newattr_txt.setDisabled(True)
        else:
            self.newattr_txt.setDisabled(False)

    def refresh_attr_values(self):
        self.extra_attrs = []
        self.attr_combo.clear()
        self.attr_combo.addItems(self.combobox_values['attrs'])
        self.attr_combo.addItem(self.NO_ATTRIB_STR)

    def validate(self):
        ''' Criteria from the window's fields, or None (after showing the error). '''
        criteria = {}
        criteria['tag'] = str(self.tag_combo.currentText())
        if self.action_combo.currentIndex() == 0:
            criteria['action'] = 'delete'
        else:
            criteria['action'] = 'modify'
        if self.attr_combo.currentIndex() == self.attr_combo.count()-1:
            criteria['attrib'] = None
        else:
            criteria['attrib'] = str(self.attr_combo.currentText())
        srch_str = str(self.srch_txt.displayText())
        if not len(srch_str):
            srch_str = None
        if srch_str is None and criteria['attrib'] is not None:
            title = _t('guiMain', 'Error')
            msg = '<p>{0}'.format(
                _t('guiMain', 'Must enter a value for the attribute selected'))
            QtWidgets.QMessageBox.warning(self, title, msg, QtWidgets.QMessageBox.Ok)
            return None
        criteria['srch_str'] = srch_str

        criteria['srch_method'] = 'normal'
        if self.srch_method.isChecked():
            criteria['srch_method'] = 'regex'
        if self.newtag_combo.currentIndex() == 0:
            criteria['new_tag'] = None
        else:
            criteria['new_tag'] = str(self.newtag_combo.currentText())
        if criteria['action'] == 'modify' and criteria['new_tag'] is None and self.copy_attr.isChecked():
            title = _t('guiMain', 'Error')
            msg = '<p>{0}'.format(
                _t('guiMain', 'What--exactly--would that achieve?'))
            QtWidgets.QMessageBox.question(self, title, msg, QtWidgets.QMessageBox.Ok)
            return None

        criteria['new_str'] = str(self.newattr_txt.displayText())
        criteria['copy'] = False
        if self.copy_attr.isChecked():
            criteria['copy'] = True
        if not len(criteria['new_str']):
            criteria['new_str'] = ''
        return criteria

    def _process_clicked(self):
        criteria = self.validate()
        if criteria is None:
            return
        global PROCESSED

        # Disable the 'Process' button, disable the context customization menu
        self.process_button.setDisabled(True)
        PROCESSED = True

        self.text_panel.clear()
        self.text_panel.insertHtml('<h4>{}...</h4><br>'.format(_t('guiMain', 'Starting')))

        # Becky: selected files, or all files if none selected (see launch_gui)
        totals = process_files(self.bk, file_list, criteria, report_to_panel(self.text_panel))

        # report totals
        if totals:
            self.quit_button.setText(_t('guiMain', 'Commit and Exit'))
            self.quit_button.setToolTip('<p>{}'.format(_t('guiMain', 'Commit all changes and exit')))
            self.abort_button.setDisabled(False)
            self.text_panel.insertHtml('<h4><br>{}:&#160;&#160;&#160;{}</h4>'.format(
                _t('guiMain', 'Total occurrences found/changed'), int(totals)))
        else:
            self.text_panel.insertHtml('<br><h4>{}</h4>'.format(
                _t('guiMain', 'No changes made to book')))
        self.text_panel.insertHtml('<br><h4>{}</h4>'.format(_t('guiMain', 'Finished')))

    # Becky 0.7.0 START
    def refresh_configs(self, select_name=None):
        self.config_entries = list_configs(self.config_folder)
        fill_config_combo(self.config_combo, self.config_entries,
                          _t('guiMain', '(none - current settings)'))
        idx = self.config_combo.findData(select_name) if select_name is not None else 0
        self.config_combo.setCurrentIndex(max(idx, 0))
        self.delete_config_button.setDisabled(self.config_combo.currentIndex() <= 0)

    def current_entry(self):
        name = self.config_combo.currentData()
        for entry in self.config_entries:
            if entry['name'] == name:
                return entry
        return None

    def config_selected(self, index=None):
        entry = self.current_entry()
        self.delete_config_button.setDisabled(entry is None)
        if entry is None:
            return
        title = _t('guiMain', 'Error')
        if entry['error'] is not None:
            msg = '<p>{}<p>{}.json'.format(criteria_error_message(entry['error']), html_escape(entry['name']))
            QtWidgets.QMessageBox.warning(self, title, msg, QtWidgets.QMessageBox.Ok)
            return
        if entry['criteria']['tag'] not in self.taglist:
            msg = '<p>{}: &lt;{}&gt;'.format(criteria_error_message('bad_tag_list'),
                                             html_escape(entry['criteria']['tag']))
            QtWidgets.QMessageBox.warning(self, title, msg, QtWidgets.QMessageBox.Ok)
            return
        self.misc_prefs['last_config'] = entry['name']
        self.apply_criteria(entry['criteria'])

    def apply_criteria(self, c):
        ''' Fill in the fields. Order matters: update_gui() clears fields
        whenever the action, tag or attribute combobox changes. '''
        self.action_combo.setCurrentIndex(0 if c['action'] == 'delete' else 1)
        self.tag_combo.setCurrentIndex(self.taglist.index(c['tag']))
        if c['attrib'] is None:
            self.attr_combo.setCurrentIndex(self.attr_combo.count() - 1)
        else:
            idx = self.attr_combo.findText(c['attrib'], Qt.MatchExactly)
            if idx < 0 or idx == self.attr_combo.count() - 1:
                # Attribute not on the user's list: add it for this session only
                idx = self.attr_combo.count() - 1
                self.attr_combo.insertItem(idx, c['attrib'])
                self.extra_attrs.append(c['attrib'])
            self.attr_combo.setCurrentIndex(idx)
        self.update_gui()

        if c['new_tag'] is None:
            self.newtag_combo.setCurrentIndex(0)
        else:
            idx = self.newtag_combo.findText(c['new_tag'], Qt.MatchExactly)
            if idx <= 0:
                self.newtag_combo.addItem(c['new_tag'])
                idx = self.newtag_combo.count() - 1
            self.newtag_combo.setCurrentIndex(idx)
        self.srch_txt.setText(c['srch_str'] or '')
        self.srch_method.setChecked(c['srch_method'] == 'regex')
        self.copy_attr.setChecked(bool(c['copy']))
        self.update_txt_box()
        if not c['copy'] and c['action'] == 'modify':
            self.newattr_txt.setText(c['new_str'] or '')

    def _save_config_clicked(self):
        criteria = self.validate()
        if criteria is None:
            return
        entry = self.current_entry()
        name = entry['name'] if entry is not None else ''
        description = entry['description'] if entry is not None else ''
        dlg = SaveConfigDialog(self, name, description, [e['name'] for e in self.config_entries])
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        # On Windows "Abc" and "abc" are the same file: keep the existing spelling
        new_name = dlg.name()
        for e in self.config_entries:
            if e['name'].casefold() == new_name.casefold():
                if e['name'] != new_name:
                    delete_config(self.config_folder, e['name'])
                break
        try:
            save_config(self.config_folder, new_name, criteria, dlg.description())
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, _t('guiMain', 'Error'), '<p>{}<p>{}'.format(
                _t('guiMain', 'Could not save the configuration'), html_escape(str(e))), QtWidgets.QMessageBox.Ok)
            return
        self.misc_prefs['last_config'] = new_name
        self.refresh_configs(new_name)

    def _delete_config_clicked(self):
        entry = self.current_entry()
        if entry is None:
            return
        msg = '<p>{}<p><b>{}</b><br>{}.json'.format(
            _t('guiMain', 'Delete this saved configuration?'),
            html_escape(entry['description']), html_escape(entry['name']))
        if QtWidgets.QMessageBox.question(self, _t('ConfigDialog', 'Are you sure?'), msg,
                                          QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel) != QtWidgets.QMessageBox.Yes:
            return
        try:
            delete_config(self.config_folder, entry['name'])
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, _t('guiMain', 'Error'), html_escape(str(e)), QtWidgets.QMessageBox.Ok)
        if self.misc_prefs['last_config'] == entry['name']:
            self.misc_prefs['last_config'] = None
        self.refresh_configs()
    # Becky 0.7.0 END

    def _quit_clicked(self):
        self.misc_prefs['windowGeometry'] = self.saveGeometry().toHex().data().decode('ascii')
        if PROCESSED:
            self.gui_prefs['action'] = self.action_combo.currentIndex()
            self.gui_prefs['tag'] = self.tag_combo.currentIndex()
            if str(self.attr_combo.currentText()) not in self.extra_attrs:
                self.gui_prefs['attrs'] = self.attr_combo.currentIndex()
        self._ok_to_close = True
        self.close()

    def _abort_clicked(self):
        global BAIL_OUT
        BAIL_OUT = True
        self._ok_to_close = True
        self.close()

    def getAbort(self):
        return BAIL_OUT

    def showConfig(self):
        ''' Launch Customization Dialog '''
        dlg = ConfigDialog(self, self.combobox_values)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.refresh_attr_values()
            self.update_gui()

    def check_for_update(self):
        '''Use updatecheck.py to check for newer versions of the plugin'''
        last_time_checked = self.update_prefs['last_time_checked']
        last_online_version = self.update_prefs['last_online_version']
        chk = UpdateChecker(last_time_checked, last_online_version, self.bk._w)
        update_available, online_version, time = chk.update_info()
        # update preferences with latest date/time/version
        self.update_prefs['last_time_checked'] = time
        if online_version is not None:
            self.update_prefs['last_online_version'] = online_version
        if update_available:
            return (True, online_version)
        return (False, online_version)

    def closeEvent(self, event):
        if self._ok_to_close:
            event.accept()  # let the window close
        else:
            self._abort_clicked()


def main():
    return -1


if __name__ == "__main__":
    sys.exit(main())

from datetime import datetime
import webbrowser
from PySide2.QtCore import Qt, QSize
from PySide2.QtGui import QIcon, QPixmap, QColor
from PySide2.QtWidgets import QMainWindow, QHBoxLayout, QVBoxLayout, QPushButton, QGridLayout, QColorDialog, \
    QComboBox, QLabel, QDoubleSpinBox, QDialog, QCheckBox, QFrame, QApplication, QLineEdit, QFileDialog, QMenuBar, \
    QMenu, QAction, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QTabWidget, QWidget
from maya import OpenMayaUI, cmds
import shiboken2
from functools import partial
import json
import os
from maya.api.OpenMaya import MMatrix, MEventMessage

dpiF = QApplication.desktop().logicalDpiX() / 96.0


def killOtherInstances(self):
    for child in self.parent().children():
        if child == self:
            continue
        if child.__class__.__name__ != self.__class__.__name__:
            continue
        child.deleteLater()


def getMayaMainWindow():
    pointer = OpenMayaUI.MQtUtil.mainWindow()
    return shiboken2.wrapInstance(int(pointer), QMainWindow)


def createSeparator():
    separator = QFrame()
    separator.setFrameShape(QFrame.HLine)
    separator.setFrameShadow(QFrame.Sunken)
    return separator


def clamp(minimum, val, maximum):
    return max(minimum, min(val, maximum))


class SelectByNameLine(QLineEdit):

    def __init__(self, *args, **kwargs):
        super(SelectByNameLine, self).__init__(*args, **kwargs)

        self.history = list()
        self.index = -1

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            event.accept()
            try:
                txt = self.history[self.index + 1]
                self.index += 1
                self.setText(txt)
            except IndexError:
                pass

        elif event.key() == Qt.Key_Down:
            event.accept()
            newIndex = self.index - 1
            if newIndex >= 0:
                txt = self.history[newIndex]
                self.index = newIndex
            else:
                txt = ''
                self.index = -1
            self.setText(txt)

        elif event.key() == Qt.Key_Return:
            event.accept()
            self.index = -1
            self.history.insert(0, self.text())
            self.select()
            self.setText('')

        else:
            super(SelectByNameLine, self).keyPressEvent(event)

    def select(self):
        rawInput = self.text()

        name_filters = list()
        inverse_name_filters = list()

        type_filters = list()
        inverse_type_filters = list()

        for input_ in rawInput.split(','):
            flt = input_.strip()
            if '#' in flt:
                flt = flt.replace('#', '')
                if '!' in flt:
                    flt = flt.replace('!', '')
                    inverse_type_filters.append(flt)
                else:
                    type_filters.append(flt)

            else:
                if '!' in flt:
                    flt = flt.replace('!', '')
                    inverse_name_filters.append(flt)
                else:
                    name_filters.append(flt)
        # print name_filters, inverse_name_filters
        # print type_filters, inverse_type_filters

        name_filtered = cmds.ls(*name_filters) if name_filters else list()
        inverse_name_filtered = cmds.ls(*inverse_name_filters) if inverse_name_filters else list()
        name_set = set(name_filtered).difference(inverse_name_filtered)

        type_filtered = cmds.ls(type=type_filters) if type_filters else list()
        inverse_type_filtered = cmds.ls(type=inverse_type_filters) if inverse_type_filters else list()
        type_set = set(type_filtered).difference(inverse_type_filtered)

        if (name_filters + inverse_name_filters) and (type_filters + inverse_type_filters):
            final_set = name_set.intersection(type_set)
        elif (name_filters + inverse_name_filters) and not (type_filters + inverse_type_filters):
            final_set = name_set
        elif not (name_filters + inverse_name_filters) and (type_filters + inverse_type_filters):
            # print 'plop'
            final_set = type_set
        else:
            final_set = set()

        cmds.select(list(final_set), noExpand=True)


class SelectionEditor(QDialog):

    def __init__(self, parent=getMayaMainWindow()):
        super(SelectionEditor, self).__init__(parent=parent)
        killOtherInstances(self)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle('Selection Editor')
        self.setMinimumSize(QSize(250 * dpiF, 250 * dpiF))

        self.selection = None
        self.historySelection = None
        self.historyEnabled = True
        self.selectionEnabled = True

        # selection count
        self.selectionCount = QLabel()

        # select by name and type
        self.selectByNameTypeHistory = list()
        self.selectByNameTypeField = SelectByNameLine()
        # self.selectByNameTypeBtn = QPushButton('>')
        # self.selectByNameTypeBtn.clicked.connect(self.selectByNameType)

        selectByNameTypeLayout = QHBoxLayout()
        selectByNameTypeLayout.addWidget(self.selectByNameTypeField)
        # selectByNameTypeLayout.addWidget(self.selectByNameTypeBtn)

        # selection tree
        lockSelection = QPushButton()
        lockSelection.toggled.connect(self.lockToggled)
        lockSelection.setIcon(QIcon(':lock.png'))
        lockSelection.setCheckable(True)

        saveSelection = QPushButton()
        saveSelection.setIcon(QIcon(':addBookmark.png'))

        selectionOptionsLayout = QHBoxLayout()
        selectionOptionsLayout.addWidget(saveSelection)
        selectionOptionsLayout.addStretch()
        selectionOptionsLayout.addWidget(lockSelection)

        self.selectionTree = QTreeWidget()
        self.selectionTree.itemSelectionChanged.connect(self.selectSelectionItem)
        self.selectionTree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.selectionTree.setSortingEnabled(True)
        self.selectionTree.sortItems(0, Qt.AscendingOrder)
        self.selectionTree.setHeaderLabels(('index', 'name', 'type'))

        selectionLayout = QVBoxLayout()
        selectionLayout.addWidget(self.selectionTree)
        selectionLayout.addLayout(selectionOptionsLayout)

        selectionTab = QWidget()
        selectionTab.setLayout(selectionLayout)

        #

        self.historyTree = QTreeWidget()
        self.historyTree.itemSelectionChanged.connect(self.selectHistoryItem)
        self.historyTree.setHeaderLabels(('time', 'len', 'content',))

        self.savedTree = QTreeWidget()

        #
        tabWid = QTabWidget()
        tabWid.addTab(selectionTab, 'Selection')
        tabWid.addTab(self.historyTree, 'History')
        tabWid.addTab(self.savedTree, 'Saved')

        # main layout
        mainLayout = QVBoxLayout(self)
        mainLayout.addLayout(selectByNameTypeLayout)
        mainLayout.addWidget(self.selectionCount)
        mainLayout.addWidget(tabWid)

        # callback
        self.eventCallback = MEventMessage.addEventCallback('SelectionChanged', self.selectionChanged)
        self.selectionChanged()

    def lockToggled(self, state):
        self.selectionEnabled = not state

    def selectHistoryItem(self, *args, **kwargs):
        items = self.historyTree.selectedItems()

        if not items:
            return

        item = items[-1]

        selection = item.data(0, Qt.UserRole)

        self.historyEnabled = False
        cmds.select(selection, noExpand=True)
        self.historyEnabled = True

    def selectSelectionItem(self, *args, **kwargs):
        items = self.selectionTree.selectedItems()

        selection = [i.data(0, Qt.UserRole) for i in items]

        self.selectionEnabled = False
        cmds.select(selection, noExpand=True)
        self.selectionEnabled = True

    def removeCallBack(self):
        try:
            MEventMessage.removeCallback(self.eventCallback)
        except RuntimeError:
            pass
        except AttributeError:
            pass

    def deleteLater(self, *args, **kwargs):
        self.removeCallBack()
        super(SelectionEditor, self).deleteLater(*args, **kwargs)

    def closeEvent(self, *args, **kwargs):
        self.removeCallBack()
        super(SelectionEditor, self).closeEvent(*args, **kwargs)

    def selectionChanged(self, *args, **kwargs):
        print('SELECTION CHANGED')
        selection = cmds.ls(sl=True, long=True)

        print(selection, self.selection)
        if selection != self.selection and self.selectionEnabled:
            self.reloadSelectionTree(selection)
            self.selection = selection

        if selection and self.historyEnabled and selection != self.historySelection:
            self.addEntryToHistory(selection)
            self.historySelection = selection

    def addEntryToHistory(self, selection):
        self.historyTree.clearSelection()

        currentDateAndTime = datetime.now()
        selectionLabel = ', '.join([i.split('|')[-1] for i in selection])
        item = QTreeWidgetItem((currentDateAndTime.strftime("%H:%M:%S"), str(len(selection)), selectionLabel,))

        item.setData(0, Qt.UserRole, selection)
        self.historyTree.insertTopLevelItem(0, item)

        self.historyEnabled = False
        item.setSelected(True)
        self.historyEnabled = True

    def reloadSelectionTree(self, selection):
        lenSelection = len(selection)

        if lenSelection == 1:
            selectionText = '<b>1 object selected</b>'
        elif lenSelection:
            selectionText = '<b>{} objects selected</b>'.format(lenSelection)
        else:
            selectionText = '<b>Nothing selected</b>'

        self.selectionCount.setText(selectionText)

        self.selectionTree.clear()
        for index, longName in enumerate(selection):
            objType = cmds.objectType(longName)
            shortName = longName.split('|')[-1]
            item = QTreeWidgetItem(('{0:0=4d}'.format(index), shortName, objType))
            item.setData(0, Qt.UserRole, longName)
            item.setToolTip(1, '{} ({})'.format(longName, objType))
            item.setIcon(1, QIcon(':{}.svg'.format(objType)))

            self.selectionTree.addTopLevelItem(item)

import webbrowser
from PySide2.QtCore import Qt, QSize
from PySide2.QtGui import QIcon, QPixmap, QColor
from PySide2.QtWidgets import QMainWindow, QHBoxLayout, QVBoxLayout, QPushButton, QGridLayout, QColorDialog, \
    QComboBox, QLabel, QDoubleSpinBox, QDialog, QCheckBox, QFrame, QApplication, QLineEdit, QFileDialog, QMenuBar, \
    QMenu, QAction, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QTabWidget
from maya import OpenMayaUI, cmds
import shiboken2
from functools import partial
import json
import os
from maya.api.OpenMaya import MMatrix


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


class SelectionEditor(QDialog):

    def __init__(self, parent=getMayaMainWindow()):
        super(SelectionEditor, self).__init__(parent=parent)
        killOtherInstances(self)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle('Selection Editor')
        self.setMinimumSize(QSize(250 * dpiF, 250 * dpiF))

        # selection count
        self.selectionCount = QLabel()

        # select by name and type
        self.selectByNameTypeHistory = list()
        self.selectByNameTypeField = QLineEdit()
        self.selectByNameTypeBtn = QPushButton('>')
        self.selectByNameTypeBtn.clicked.connect(self.selectByNameType)

        selectByNameTypeLayout = QHBoxLayout()
        selectByNameTypeLayout.addWidget(self.selectByNameTypeField)
        selectByNameTypeLayout.addWidget(self.selectByNameTypeBtn)

        # selection tree
        self.selectionTree = QTreeWidget()
        self.selectionTree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.selectionTree.setSortingEnabled(True)
        self.selectionTree.sortItems(0, Qt.AscendingOrder)
        self.selectionTree.setHeaderLabels(('index', 'name', 'type'))

        self.historyTree = QTreeWidget()

        self.savedTree = QTreeWidget()

        # menuBar
        reloadAct = QAction('Reload', self)
        reloadAct.triggered.connect(self.reloadSelectionTree)

        menuBar = QMenuBar()
        menuBar.addAction(reloadAct)

        #
        tabWid = QTabWidget()
        tabWid.addTab(self.selectionTree, 'Selection')
        tabWid.addTab(self.historyTree, 'History')
        tabWid.addTab(self.savedTree, 'Saved')

        # main layout
        mainLayout = QVBoxLayout(self)
        mainLayout.setMenuBar(menuBar)
        mainLayout.addLayout(selectByNameTypeLayout)
        mainLayout.addWidget(self.selectionCount)
        mainLayout.addWidget(tabWid)

        self.reloadSelectionTree()

    def reloadSelectionTree(self):
        selection = cmds.ls(sl=True, long=True)
        self.selectionCount.setText('<b>{} selected</b>'.format(len(selection)))

        self.selectionTree.clear()
        for index, longName in enumerate(selection):
            objType = cmds.objectType(longName)
            shortName = longName.split('|')[-1]
            item = QTreeWidgetItem(('{0:0=4d}'.format(index), shortName, objType))
            item.setToolTip(1, '{} ({})'.format(longName, objType))
            item.setIcon(1, QIcon(':{}.svg'.format(objType)))

            self.selectionTree.addTopLevelItem(item)

    def selectByNameType(self):
        rawInput = self.selectByNameTypeField.text()

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
        print name_filters, inverse_name_filters
        print type_filters, inverse_type_filters

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
            print 'plop'
            final_set = type_set
        else:
            final_set = set()

        cmds.select(list(final_set))
        self.reloadSelectionTree()

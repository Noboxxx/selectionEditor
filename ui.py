import time
from datetime import datetime
import webbrowser

from PySide2.QtSvg import QSvgRenderer

from PySide2.QtCore import Qt, QSize, QRect
from PySide2.QtGui import QIcon, QPixmap, QColor, QPainter, QImage
from PySide2.QtWidgets import QMainWindow, QHBoxLayout, QVBoxLayout, QPushButton, QGridLayout, QColorDialog, \
    QComboBox, QLabel, QDoubleSpinBox, QDialog, QCheckBox, QFrame, QApplication, QLineEdit, QFileDialog, QMenuBar, \
    QMenu, QAction, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QTabWidget, QWidget
from maya import OpenMayaUI, cmds
import shiboken2
from functools import partial
import json
import os
from maya.api.OpenMaya import MMatrix, MEventMessage
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin


dpiF = QApplication.desktop().logicalDpiX() / 96.0


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
            final_set = type_set
        else:
            final_set = set()

        cmds.select(list(final_set), noExpand=True)


class IconWidget(QWidget):

    images = dict()

    def __init__(self, node, parent):
        super(IconWidget, self).__init__(parent)

        nodeType = cmds.objectType(node)
        shapes = cmds.listRelatives(node, shapes=True, fullPath=True) if nodeType != 'objectSet' else None
        shapType = cmds.objectType(shapes[0]) if shapes else None

        self.type = nodeType if not shapType else shapType
        self.isShape = cmds.objectType(node, isAType='shape')
        self.isReferenced = cmds.referenceQuery(node, isNodeReferenced=True)
        self.isController = cmds.controller(node, q=True, isController=True)

    def paintEvent(self, event):
        painter = QPainter(self)

        # type
        img = QImage(':{}.svg'.format(self.type))
        if img.isNull():
            img = QImage(':default.svg')
        img = img.smoothScaled(self.width(), self.height())
        painter.drawImage(0, 0, img)

        # ref
        if self.isReferenced:
            refImg = QImage(':reference.svg').smoothScaled(self.width() * .5, self.height() * .5)
            painter.drawImage(0, 0, refImg)

        # shape
        if self.isShape:
            shapeImg = QImage(':nurbsSurface.svg').smoothScaled(self.width() * .5, self.height() * .5)
            painter.drawImage(self.width() * .5, self.height() * .5, shapeImg)

        # ctrl
        if self.isController:
            ctrlImg = QImage(':character.svg').smoothScaled(self.width() * .5, self.height() * .5)
            painter.drawImage(self.width() * .5, 0, ctrlImg)

        # painter.drawRect(0, 0, self.width() - 1, self.height() - 1)


class SelectionEditor(MayaQWidgetDockableMixin, QDialog):

    def __init__(self, parent=getMayaMainWindow()):
        super(SelectionEditor, self).__init__(parent=parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle('Selection')

        self.selection = None
        self.historySelection = None
        self.historyEnabled = True
        self.selectionEnabled = True
        self.namespace = True

        # selection count
        self.selectionCount = QLabel()

        # select by name and type
        self.selectByNameTypeHistory = list()
        self.selectByNameTypeField = SelectByNameLine()
        pixmap = QPixmap(':quickSelect.png')

        selectByNameLabel = QLabel()
        selectByNameLabel.setPixmap(pixmap.scaled(40, 40))

        selectByNameTypeLayout = QHBoxLayout()
        selectByNameTypeLayout.addWidget(selectByNameLabel)
        selectByNameTypeLayout.addWidget(self.selectByNameTypeField)
        selectByNameTypeLayout.addWidget(self.selectionCount)

        # # selection tree
        # lockSelection = QPushButton()
        # lockSelection.toggled.connect(self.lockToggled)
        # lockSelection.setIcon(QIcon(':lock.png'))
        # lockSelection.setCheckable(True)
        #
        # saveSelection = QPushButton()
        # saveSelection.setIcon(QIcon(':addBookmark.png'))
        #
        # selectionOptionsLayout = QHBoxLayout()
        # selectionOptionsLayout.addWidget(saveSelection)
        # selectionOptionsLayout.addStretch()
        # selectionOptionsLayout.addWidget(lockSelection)

        self.selectionTree = QTreeWidget()
        self.selectionTree.itemSelectionChanged.connect(self.selectSelectionItem)
        self.selectionTree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.selectionTree.setSortingEnabled(True)
        self.selectionTree.sortItems(0, Qt.AscendingOrder)
        self.selectionTree.setHeaderHidden(True)
        # self.selectionTree.setHeaderLabels(('index', 'name', 'type'))

        refreshAct = QAction('Auto-Refresh', self)
        # refreshAct.setCheckable(True)

        displayMenu = QMenu('Display')
        displayMenu.addAction(refreshAct)

        menuBar = QMenuBar()
        menuBar.addMenu(displayMenu)

        selectionLayout = QVBoxLayout()
        selectionLayout.setMenuBar(menuBar)
        # selectionLayout.setMargin(0)
        selectionLayout.addWidget(self.selectionTree)
        # selectionLayout.addLayout(selectionOptionsLayout)

        selectionTab = QWidget()
        selectionTab.setLayout(selectionLayout)

        #

        self.historyTree = QTreeWidget()
        self.historyTree.itemSelectionChanged.connect(self.selectHistoryItem)
        self.historyTree.setHeaderLabels(('time', 'len', 'content'))

        self.savedTree = QTreeWidget()

        #
        tabWid = QTabWidget()
        tabWid.addTab(selectionTab, 'Selection')
        tabWid.addTab(self.historyTree, 'History')
        tabWid.addTab(self.savedTree, 'Saved')

        # plop
        menuBar = QMenuBar()
        menuBar.addMenu(QMenu('Display'))
        llay = QVBoxLayout()
        llay.setMenuBar(menuBar)
        llay.addWidget(QLabel('plopppp'))

        # main layout
        mainLayout = QVBoxLayout(self)
        # mainLayout.setMenuBar(menuBar)
        mainLayout.addLayout(llay)
        mainLayout.addLayout(selectByNameTypeLayout)
        mainLayout.addWidget(tabWid)

        #
        self.eventCallback = None

        self.resize(QSize(130 * dpiF, 260 * dpiF))

    def lockToggled(self, state):
        self.selectionEnabled = not state
        if not state:
            self.reload()

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

    def hideEvent(self, *args, **kwargs):
        self.removeCallBack()
        super(SelectionEditor, self).hideEvent(*args, **kwargs)

    def showEvent(self, *args, **kwargs):
        self.eventCallback = MEventMessage.addEventCallback('SelectionChanged', self.reload)
        self.reload()
        super(SelectionEditor, self).showEvent(*args, **kwargs)

    def reload(self, *args, **kwargs):
        # print('SELECTION CHANGED')
        start = time.time()
        selection = cmds.ls(sl=True, long=True)

        self.selectionCount.setText('<b>{}</b>'.format(len(selection)))

        if selection != self.selection and self.selectionEnabled:
            self.reloadSelectionTree(selection)
            self.selection = selection

        print('SELECTION CHANGED', time.time() - start)
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
        shortNames = list()
        names = list()
        nonUniqueNames = list()
        for longName in selection:
            name = longName.split('|')[-1]
            shortName = name.split(':')[-1]

            if shortName in shortNames:
                if shortName not in nonUniqueNames:
                    nonUniqueNames.append(shortName)

            names.append(name)
            shortNames.append(shortName)

        self.selectionTree.clear()
        for index, (longName, name, shortName) in enumerate(zip(selection, names, shortNames)):
            objType = cmds.objectType(longName)

            item = QTreeWidgetItem()
            item.setData(0, Qt.UserRole, longName)
            item.setToolTip(0, '{} ({})'.format(name, objType))

            icon = IconWidget(longName, self)
            icon.setFixedSize(QSize(40, 40))

            if self.namespace:
                nameLabel = QLabel(name)
            else:
                nameLabel = QLabel(shortName) if shortName not in nonUniqueNames else QLabel(name)

            lay = QHBoxLayout()
            lay.setMargin(2)
            lay.addWidget(icon)
            lay.addWidget(nameLabel)

            wid = QWidget()
            wid.setLayout(lay)

            self.selectionTree.addTopLevelItem(item)
            self.selectionTree.setItemWidget(item, 0, wid)
            item.setSizeHint(0, QSize(0, 40))

import time
from datetime import datetime
import webbrowser

from PySide2.QtSvg import QSvgRenderer

from PySide2.QtCore import Qt, QSize, QRect, QPoint
from PySide2.QtGui import QIcon, QPixmap, QColor, QPainter, QImage, QMouseEvent, QFont, QFontMetrics, QPen, QBrush
from PySide2.QtWidgets import QMainWindow, QHBoxLayout, QVBoxLayout, QPushButton, QGridLayout, QColorDialog, \
    QComboBox, QLabel, QDoubleSpinBox, QDialog, QCheckBox, QFrame, QApplication, QLineEdit, QFileDialog, QMenuBar, \
    QMenu, QAction, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QTabWidget, QWidget, QListWidget, \
    QListWidgetItem, QScrollBar
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

        name_filtered = cmds.ls(*name_filters, recursive=True) if name_filters else list()
        inverse_name_filtered = cmds.ls(*inverse_name_filters, recursive=True) if inverse_name_filters else list()
        name_set = set(name_filtered).difference(inverse_name_filtered)

        type_filtered = cmds.ls(type=type_filters, recursive=True) if type_filters else list()
        inverse_type_filtered = cmds.ls(type=inverse_type_filters, recursive=True) if inverse_type_filters else list()
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


class IconButton(QWidget):

    images = dict()

    def __init__(self, idleImageFile, checkedImageFile=None, checkable=False, parent=None, isChecked=False):
        super(IconButton, self).__init__(parent=parent)
        self.idleImageFile = idleImageFile
        self.checkedImageFile = checkedImageFile
        self.isCheckable = checkable

        self.clicked = list()
        self.checked = list()

        self.isHovered = False
        self.isClicked = False
        self.isChecked = isChecked

        self.hoveredColor = 50
        self.clickedColor = 100

    def enterEvent(self, *args, **kwargs):
        super(IconButton, self).enterEvent(*args, **kwargs)
        # print('ENTER')

        self.isHovered = True
        self.update()

    def leaveEvent(self, *args, **kwargs):
        super(IconButton, self).leaveEvent(*args, **kwargs)
        # print('LEAVE')

        self.isHovered = False
        self.update()

    def mousePressEvent(self, event):  # type: (QMouseEvent) -> None
        if event.button() == Qt.LeftButton:
            self.isClicked = True
            event.accept()
            self.update()
        else:
            super(IconButton, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:

            self.isClicked = False

            if self.isCheckable:
                self.isChecked = not self.isChecked
                [func(self.isChecked) for func in self.checked]

            [func() for func in self.clicked]

            event.accept()
            self.update()
        else:
            super(IconButton, self).mouseReleaseEvent(event)

    def offsetImageColor(self, img, offsetColor):
        for x in range(img.width()):
            for y in range(img.height()):
                color = img.pixelColor(x, y)  # type: QColor

                r = min(color.red() + offsetColor, 255)
                g = min(color.green() + offsetColor, 255)
                b = min(color.blue() + offsetColor, 255)
                a = color.alpha()

                img.setPixelColor(x, y, QColor(r, g, b, a))

    def paintEvent(self, event):
        painter = QPainter(self)

        # img
        img = QImage(self.idleImageFile)
        if self.isCheckable and self.isChecked and self.checkedImageFile:
            img = QImage(self.checkedImageFile)

        if self.isClicked:
            self.offsetImageColor(img, self.clickedColor)
        elif self.isHovered:
            self.offsetImageColor(img, self.hoveredColor)

        img = img.smoothScaled(self.width(), self.height())
        painter.drawImage(0, 0, img)


class SelectionEditor(QDialog):   #  MayaQWidgetDockableMixin,

    def __init__(self, parent=getMayaMainWindow()):
        super(SelectionEditor, self).__init__(parent=parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle('Selection')

        self.selection = None
        self.historySelection = None
        self.historyEnabled = True
        self.selectionEnabled = True
        self.namespace = True

        #
        self.selectionTree = SelectionTree()
        self.selectionTree.itemSelectionChanged.connect(self.selectSelectionItem)

        # selection count
        self.selectionCount = QLabel()
        self.selectionCount.setToolTip('Number of Selected Objects')

        # select by name and type
        self.selectByNameTypeHistory = list()
        self.selectByNameTypeField = SelectByNameLine()
        pixmap = QPixmap(':quickSelect.png')

        selectByNameLabel = QLabel()
        selectByNameLabel.setToolTip('Select by Name and Type')
        selectByNameLabel.setPixmap(pixmap.scaled(40, 40))

        selectByNameTypeLayout = QHBoxLayout()
        selectByNameTypeLayout.addWidget(selectByNameLabel)
        selectByNameTypeLayout.addWidget(self.selectByNameTypeField)
        # selectByNameTypeLayout.addWidget(self.selectionCount)

        # selection tree
        lockSelection = IconButton(':unlockGeneric.png', ':lock.png', checkable=True)
        lockSelection.setToolTip('Lock/Unlock Auto-Reload')
        lockSelection.setMinimumSize(QSize(30, 30))
        lockSelection.checked.append(self.lockToggled)

        self.saveSelection = IconButton(':Bookmark.png')
        self.saveSelection.setToolTip('Save Current Selection')
        self.saveSelection.setMinimumSize(QSize(30, 30))
        self.saveSelection.clicked.append(self.test)

        self.saveWindow = QWidget(self.saveSelection)
        self.saveWindow.setFixedSize(QSize(100, 100))

        copySelectionTab = IconButton(':UVTkCopySet.png')
        copySelectionTab.setToolTip('Tear Off Selection in another Window')
        copySelectionTab.setMinimumSize(QSize(30, 30))
        copySelectionTab.clicked.append(self.tearOffSelectionCopy)

        displayNamespaces = IconButton(':switchOff.png', ':switchOn.png', checkable=True, isChecked=True)
        displayNamespaces.setToolTip('Show/Hide Namespaces')
        displayNamespaces.setMinimumSize(QSize(30, 30))
        displayNamespaces.checked.append(self.selectionTree.toggleNamespaces)

        selectionOptionsLayout = QHBoxLayout()
        selectionOptionsLayout.addWidget(lockSelection)
        selectionOptionsLayout.addWidget(self.saveSelection)
        selectionOptionsLayout.addWidget(copySelectionTab)
        selectionOptionsLayout.addWidget(displayNamespaces)
        # selectionOptionsLayout.addStretch()
        # for _ in range(5):
        #     icnBtn = IconButton(':Bookmark.png')
        #     icnBtn.setMinimumSize(QSize(30, 30))
        #     selectionOptionsLayout.addWidget(icnBtn)
        selectionOptionsLayout.addStretch()
        selectionOptionsLayout.addWidget(self.selectionCount)

        # self.selectionList.setSelectionMode(QListWidget.ExtendedSelection)

        refreshAct = QAction('Auto-Refresh', self)
        # refreshAct.setCheckable(True)

        displayMenu = QMenu('Display')
        displayMenu.addAction(refreshAct)

        menuBar = QMenuBar()
        menuBar.addMenu(displayMenu)

        # selectionLayout = QVBoxLayout()
        # selectionLayout.setSpacing(0)
        # selectionLayout.addLayout(selectionOptionsLayout)
        # selectionLayout.addWidget(self.selectionTree)

        #

        self.historyTree = QTreeWidget()
        self.historyTree.itemSelectionChanged.connect(self.selectHistoryItem)
        self.historyTree.setHeaderLabels(('time', 'len', 'content'))

        self.savedTree = QTreeWidget()

        # main layout
        mainLayout = QVBoxLayout(self)
        # mainLayout.setMargin(0)
        mainLayout.addLayout(selectByNameTypeLayout)
        mainLayout.addLayout(selectionOptionsLayout)
        mainLayout.addWidget(self.selectionTree)
        # mainLayout.addLayout(selectionLayout)

        #
        self.eventCallback = None

        self.resize(QSize(130 * dpiF, 260 * dpiF))

    def test(self):
        if self.saveWindow.isVisible():
            self.saveWindow.hide()
            return

        self.saveWindow.show()

        # x = self.saveSelection.x()
        # y = self.saveSelection.y() + self.saveSelection.height()
        #
        # self.saveWindow.move(self.mapToGlobal(QPoint(x, y)))
        # self.saveWindow.resize(QSize(500, 500))

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
        self.selectionEnabled = False
        cmds.select(self.selectionTree.selectedNodes(), noExpand=True)
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
        self.saveWindow.deleteLater()
        super(SelectionEditor, self).deleteLater(*args, **kwargs)

    def closeEvent(self, *args, **kwargs):
        self.removeCallBack()
        self.saveWindow.close()
        super(SelectionEditor, self).closeEvent(*args, **kwargs)

    def hideEvent(self, *args, **kwargs):
        print('hide')
        self.removeCallBack()
        self.saveWindow.hide()
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
            self.selectionTree.load(selection)
            self.selection = selection

        # print('SELECTION CHANGED', time.time() - start)
        if selection and self.historyEnabled and selection != self.historySelection:
            self.addEntryToHistory(selection)
            self.historySelection = selection

    def addEntryToHistory(self, selection):
        pass
        # self.historyTree.clearSelection()
        #
        # currentDateAndTime = datetime.now()
        # selectionLabel = ', '.join([i.split('|')[-1] for i in selection])
        # item = QTreeWidgetItem((currentDateAndTime.strftime("%H:%M:%S"), str(len(selection)), selectionLabel,))
        #
        # item.setData(0, Qt.UserRole, selection)
        # self.historyTree.insertTopLevelItem(0, item)
        #
        # self.historyEnabled = False
        # item.setSelected(True)
        # self.historyEnabled = True

    def tearOffSelectionCopy(self):
        ui = TearOffSelectionWindow(self.selectionTree.nodes, parent=self)
        ui.show()


# class ObjectNameWidget(QWidget):
#
#     def __init__(self, longName, parent=None):
#         super(ObjectNameWidget, self).__init__(parent)
#
#         name = longName.split('|')[-1]
#         nameSplit = name.split(':')
#         namespace = ':'.join(nameSplit[:-1])
#         shortName = nameSplit[-1]
#
#         objType = cmds.objectType(longName)
#
#         item = QListWidgetItem()
#         item.setData(Qt.UserRole, longName)
#         item.setToolTip('{} ({})'.format(name, objType))
#
#         icon = IconWidget(longName, self)
#         icon.setFixedSize(QSize(35, 35))
#
#         shortNameLabel = QLabel(shortName)
#         # shortNameLabel.setFixedWidth(shortNameLabel.width())
#
#         nameLayout = QHBoxLayout()
#         nameLayout.setAlignment(Qt.AlignLeft)
#         nameLayout.setSpacing(0)
#         if namespace:
#             namespaceLabel = QLabel('{}:'.format(namespace))
#             namespaceLabel.setStyleSheet("QLabel {color: rgb(150, 150, 150);}")
#             nameLayout.addWidget(namespaceLabel)
#         nameLayout.addWidget(shortNameLabel)
#
#         lay = QHBoxLayout(self)
#         lay.setMargin(2)
#         lay.setAlignment(Qt.AlignLeft)
#         lay.addWidget(icon)
#         lay.addLayout(nameLayout)


class SelectionTree(QListWidget):
    def __init__(self, *args, **kwargs):
        super(SelectionTree, self).__init__(*args, **kwargs)
        # self.setStyleSheet('QListWidget {background: rgb(50, 50, 50);} QListWidget::item:selected {background: rgb(100, 100, 100);}')
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.nodes = list()
        self.itemSelectionChanged.connect(self.selectItems)

        self.displayNamespaces = True

    def selectItems(self):
        selectedItems = self.selectedItems()

        items = [self.item(x) for x in range(self.count())]

        for item in items:
            wid = self.itemWidget(item)
            if not wid:
                continue
            wid.isSelected = item in selectedItems

    def toggleNamespaces(self, state):
        self.displayNamespaces = state
        items = [self.item(x) for x in range(self.count())]

        for item in items:
            wid = self.itemWidget(item)
            wid.displayNamespace = state

    def selectedNodes(self):
        return [i.data(Qt.UserRole) for i in self.selectedItems()]

    def load(self, nodes):
        self.clear()
        self.nodes = nodes

        for index, longName in enumerate(nodes):
            objType = cmds.objectType(longName)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, longName)

            nodeType = cmds.objectType(longName)
            shapes = cmds.listRelatives(longName, shapes=True, fullPath=True) if nodeType != 'objectSet' else None
            shapType = cmds.objectType(shapes[0]) if shapes else None

            finalType = nodeType if not shapType else shapType
            isReferenced = cmds.referenceQuery(longName, isNodeReferenced=True)

            name = longName.split('|')[-1]
            item.setToolTip('{} ({})'.format(name, objType))
            wid = NodeWidget(name, objectType=finalType, isReferenced=isReferenced, parent=self)
            wid.displayNamespace = self.displayNamespaces
            # wid.secondaryColor = QColor(175, 125, 125)
            wid.setFixedHeight(35)

            self.addItem(item)
            self.setItemWidget(item, wid)
            item.setSizeHint(QSize(0, 40))


class NodeWidget(QWidget):

    def __init__(self, longName, objectType=None, isReferenced=False, parent=None):
        super(NodeWidget, self).__init__(parent)

        longNameSplit = longName.split(':')
        namespace = ':'.join(longNameSplit[:-1])
        self.namespace = '{}:'.format(namespace) if namespace else namespace
        self.name = longNameSplit[-1]
        self.objectType = objectType
        self.isReferenced = isReferenced

        self.mainColor = QColor(200, 200, 200)
        self.secondaryColor = QColor(125, 125, 125)
        self.selectedColor = QColor(255, 255, 255)

        self.setMinimumHeight(35)

        self._displayNamespace = True
        self.isSelected = False

    @property
    def displayNamespace(self):
        return self._displayNamespace

    @displayNamespace.setter
    def displayNamespace(self, value):
        self._displayNamespace = value
        self.update()

    def paintEvent(self, *args, **kwargs):
        painter = QPainter(self)
        font = QFont()
        font.setPixelSize(self.height() * .66)
        fontMetrics = QFontMetrics(font)
        fontHeight = fontMetrics.height()

        typeImage = QImage(':{}.svg'.format(self.objectType))
        if typeImage.isNull():
            typeImage = QImage(':default.svg')
        typeImage = typeImage.smoothScaled(self.height(), self.height())

        namespacePen = QPen()
        namespacePen.setColor(self.secondaryColor if not self.isSelected else self.selectedColor)

        namePen = QPen()
        namePen.setColor(self.mainColor if not self.isSelected else self.selectedColor)

        namespaceWidth = fontMetrics.horizontalAdvance(self.namespace) if self.displayNamespace else 0
        nameWidth = fontMetrics.horizontalAdvance(self.name)

        typeRect = QRect(0, 0, self.height(), self.height())

        namespaceRect = QRect(typeRect.x() + typeRect.width(), 0, namespaceWidth, fontHeight)
        nameRect = QRect(namespaceRect.x() + namespaceRect.width(), 0, nameWidth, fontHeight)

        # draw
        painter.drawImage(typeRect, typeImage)
        if self.isReferenced:
            refRect = QRect(0, 0, self.height() * .5, self.height() * .5)
            refImage = QImage(':reference.svg').smoothScaled(self.height() * .5, self.height() * .5)
            painter.drawImage(refRect, refImage)

        painter.setFont(font)
        painter.setPen(namespacePen)
        if self.displayNamespace:
            painter.drawText(namespaceRect, self.namespace)

        painter.setPen(namePen)
        painter.drawText(nameRect, self.name)


class TearOffSelectionWindow(QDialog):

    def __init__(self, nodes, parent=None):
        super(TearOffSelectionWindow, self).__init__(parent)
        self.setWindowTitle('Tear Off Selection')

        self.selectionTree = SelectionTree()
        self.selectionTree.load(nodes)
        self.selectionTree.itemSelectionChanged.connect(self.selectSelectionItem)

        layout = QVBoxLayout(self)
        layout.addWidget(self.selectionTree)

    def selectSelectionItem(self, *args, **kwargs):
        cmds.select(self.selectionTree.selectedNodes(), noExpand=True)

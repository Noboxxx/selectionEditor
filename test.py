from PySide2.QtCore import QRect, QSize

from PySide2.QtGui import QPainter, QFont, QFontMetrics, QPen, QColor, QImage, Qt

import shiboken2
from PySide2.QtWidgets import QDialog, QVBoxLayout, QWidget, QMainWindow, QCheckBox
from maya import OpenMayaUI, cmds


def getMayaMainWindow():
    pointer = OpenMayaUI.MQtUtil.mainWindow()
    return shiboken2.wrapInstance(int(pointer), QMainWindow)


class NodeWidget(QWidget):

    def __init__(self, longName, objectType=None, isReferenced=False):
        super(NodeWidget, self).__init__()

        longNameSplit = longName.split(':')
        namespace = ':'.join(longNameSplit[:-1])
        self.namespace = '{}:'.format(namespace) if namespace else namespace
        self.name = longNameSplit[-1]
        self.objectType = objectType
        self.isReferenced = isReferenced

        self.mainColor = QColor(200, 200, 200)
        self.secondaryColor = QColor(125, 125, 125)

        self.setMinimumHeight(35)

        self._displayNamespace = True
        self.isHovered = False

    @property
    def displayNamespace(self):
        return self._displayNamespace

    @displayNamespace.setter
    def displayNamespace(self, value):
        self._displayNamespace = value
        self.update()

    def enterEvent(self, *args, **kwargs):
        self.isHovered = True
        self.update()

    def leaveEvent(self, *args, **kwargs):
        self.isHovered = False
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
        namespacePen.setColor(self.secondaryColor if not self.isHovered else self.mainColor)

        namePen = QPen()
        namePen.setColor(self.mainColor)

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


class TestWindow(QDialog):

    def __init__(self, *args, **kwargs):
        super(TestWindow, self).__init__(getMayaMainWindow())
        self.resize(QSize(500, 500))

        self.wids = list()

        check = QCheckBox()
        check.toggled.connect(self.toggleNamespace)

        mainLayout = QVBoxLayout(self)
        mainLayout.setAlignment(Qt.AlignTop)
        mainLayout.addWidget(check)
        for node in cmds.ls(sl=True):
            wid = NodeWidget(node, cmds.objectType(node), isReferenced=cmds.referenceQuery(node, isNodeReferenced=True))
            wid.displayNamespace = False
            self.wids.append(wid)
            mainLayout.addWidget(wid)
        # mainLayout.addStretch()

    def toggleNamespace(self, state):
        print('toggleNamespace')
        for wid in self.wids:
            wid.displayNamespace = state


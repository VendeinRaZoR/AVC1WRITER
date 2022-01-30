# This Python file uses the following encoding: utf-8
import sys
import os
import subprocess
import re
import threading
import time

from PySide2.QtWidgets import QApplication, QWidget, QMenu, QMenuBar, QVBoxLayout, QAction, QFileDialog, QComboBox, QStatusBar, QProgressBar, QMessageBox, QRadioButton, QLabel, QDialogButtonBox, QPushButton, QTextEdit, QLineEdit
from PySide2.QtCore import SIGNAL, SLOT, Signal, Slot, QObject, QFile, Qt, QRect, Signal, QMetaObject
from PySide2.QtUiTools import QUiLoader


WINDOW_WIDTH = 1120
WINDOW_HEIGHT = 1050

MAX_COMBO = 105
MAX_AVC_SIGNALS = 32
MAX_AVC_FAST = 32
MAX_AVC_SLOW = 128
MAX_AVC_SLOWTS = 64
MAX_AVC_FREQ_FAST = 143
MAX_AVC_FREQ_SLOW = 71

MAX_VECTORS = 7200000

#CONFIGURATION FORMAT: <DRAM0OUT(16 bit)>_<DRAM1OUT(16 bit)>
#FAST<num> - fast output or input signals
#SLOWTS<num> - slow 3-state signals
#SLOW<num> - slow output or input signals
class ConfigurationType:
    FAST16_FAST16 = 0 #<MAX_FREQUENCY>_<MAX_FREQUENCY>
    FAST16_SLOWTS16 = 1 #<MAX_FREQUENCY>_<MAX_FREQUENCY/2>
    FAST16_SLOWTS32 = 2 #<MAX_FREQUENCY>_<MAX_FREQUENCY/4>
    FAST16_SLOW32 = 3 #<MAX_FREQUENCY>_<MAX_FREQUENCY/2>
    FAST16_SLOW64 = 4 #<MAX_FREQUENCY>_<MAX_FREQUENCY/4>
    SLOWTS16_SLOWTS16 = 5 #<MAX_FREQUENCY/2>_<MAX_FREQUENCY/2>
    SLOWTS32_SLOWTS32 = 6 #<MAX_FREQUENCY/4>_<MAX_FREQUENCY/4>
    SLOWTS16_SLOW32 = 7 #<MAX_FREQUENCY/2>_<MAX_FREQUENCY/2>
    SLOWTS16_SLOW64 = 8 #<MAX_FREQUENCY/2>_<MAX_FREQUENCY/4>
    SLOWTS32_SLOW32 = 9 #<MAX_FREQUENCY/4>_<MAX_FREQUENCY/2>
    SLOWTS32_SLOW64 = 10 #<MAX_FREQUENCY/4>_<MAX_FREQUENCY/4>
    SLOW32_SLOW32 = 11 #<MAX_FREQUENCY/2>_<MAX_FREQUENCY/2>
    SLOW64_SLOW64 = 12 #<MAX_FREQUENCY/4>_<MAX_FREQUENCY/4>

class UpdateProgress(QObject): #update progress bar through the thread

    updateProgress = Signal(int)
    setRange = Signal(int,int)

    def __init__(self):
        super(UpdateProgress, self).__init__()

    def Update(self,value):
        self.updateProgress.emit(value)

    def setRangeProgressBar(self,min,max):
        self.setRange.emit(min,max)

class UpdateStatus(QObject): #update status bar through the thread

    updateStatus = Signal(str)

    def __init__(self):
        super(UpdateStatus, self).__init__()

    def Update(self,message):
        self.updateStatus.emit(message)

class UpdateMenu(QObject): #update menu bar through the thread

    updateMenu = Signal(bool)

    def __init__(self):
        super(UpdateMenu, self).__init__()

    def SetEnabled(self,enabled):
        self.updateMenu.emit(enabled)

class ErrorMessageBox(QObject): #error box appear while reading through the thread

    errorShow = Signal(str)

    def __init__(self):
        super(ErrorMessageBox, self).__init__()

    def Show(self,message):
        self.errorShow.emit(message)

class AVC1WRITER(QWidget): #AVC1READER entry point
    comboBox = []
    statusBar = None
    progressBar = None
    menuBar = None
    avcheaderindex = None
    savcheader = None
    sdDialog = None
    pinsDialog = None
    propDialog = None
    configDialog = None
    formatMessageBox = None
    errorMessageBox = None
    errorAVC = None
    dialogCombo = None
    dialogButton = None
    dialogUmountButton = None   
    avcsgnlbuffer = [[]]
    progressValue = 0
    diskfound = 0
    updateProgress = None
    updateStatus = None
    updateMenu = None
    openFileName = None
    openFileSize = None
    numVectors = 0
    numSignals = 0
    opensdmessage = None
    openQSFButton = None
    menuSaveAVCFile = None
    menuAboutAVCFile = None
    menuWriteAVCFile = None
    menuClose = None
    menuArria10 = None
    fileOpened = False
    pinstext = ""
    configType = ConfigurationType.FAST16_SLOWTS16

    def __init__(self):
        super(AVC1WRITER, self).__init__()
        self.sdDialog = QWidget()
        self.pinsDialog = QWidget()
        self.load_ui()
        self.statusBar = QStatusBar()
        self.progressBar = QProgressBar()
        self.comboBox = []

    def load_ui(self):
        loader = QUiLoader()
        path = os.path.join(os.path.dirname(__file__), "form.ui")
        ui_file = QFile(path)
        ui_file.open(QFile.ReadOnly)
        loader.load(ui_file, self)
        ui_file.close()

        path_dialog = os.path.join(os.path.dirname(__file__), "dialog.ui")
        ui_file_dialog = QFile(path_dialog)
        ui_file_dialog.open(QFile.ReadOnly)
        self.sdDialog = loader.load(ui_file_dialog, self)
        ui_file_dialog.close()

        path_dialog_pins = os.path.join(os.path.dirname(__file__), "dialogpins.ui")
        ui_file_dialog_pins = QFile(path_dialog_pins)
        ui_file_dialog_pins.open(QFile.ReadOnly)
        self.pinsDialog = loader.load(ui_file_dialog_pins, self)
        ui_file_dialog_pins.close()

        path_dialog_prop = os.path.join(os.path.dirname(__file__), "dialogprop.ui")
        ui_file_dialog_prop = QFile(path_dialog_prop)
        ui_file_dialog_prop.open(QFile.ReadOnly)
        self.propDialog = loader.load(ui_file_dialog_prop, self)
        ui_file_dialog_prop.close()

        path_dialog_config = os.path.join(os.path.dirname(__file__), "dialogconfig.ui")
        ui_file_dialog_config = QFile(path_dialog_config)
        ui_file_dialog_config.open(QFile.ReadOnly)
        self.configDialog = loader.load(ui_file_dialog_config, self)
        ui_file_dialog_config.close()

    def OnOpenAVCFile(self,fileName):

        #open AVC file
        avcfile = open(fileName, 'r')
        avcheader = avcfile.readline()
        self.savcheader = avcheader.split()
        self.avcheaderindex = list()
        noAssignedSignals = True
        self.updateMenu.SetEnabled(False)
        self.fileOpened = False

        if(os.path.getsize(fileName) == 0):
            self.errorAVC.Show("Файл пуст")
            self.updateProgress.Update(0)
            self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
            self.updateMenu.SetEnabled(True)
            return

        if(len(self.savcheader) == 0):
            self.errorAVC.Show("Отсутствует заголовок в первой строке")
            self.updateProgress.Update(0)
            self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
            self.updateMenu.SetEnabled(True)
            return

        if(self.savcheader[0] != "FORMAT"):
            self.errorAVC.Show("Неправильный заголовок")
            self.updateProgress.Update(0)
            self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
            self.updateMenu.SetEnabled(True)
            return

        self.updateProgress.setRangeProgressBar(1, MAX_COMBO)
        progressNum = 1
        self.updateStatus.Update("Открытие файла " + self.openFileName + ": Обновление меню")
        #initialize or remove items from comboboxes
        for x in range(1, MAX_COMBO):
            progressNum += 1
            self.updateProgress.Update(progressNum)
            if self.comboBox[x-1].count() > 1:
                for i in range(self.comboBox[x-1].count(),0,-1):
                    self.comboBox[x-1].removeItem(i)

        for x in range(1, MAX_COMBO):
            self.comboBox[x-1].setCurrentIndex(0)

        #delete last ';'
        l0 = list(self.savcheader[len(self.savcheader)-1])
        if(l0[len(l0)-1] == ';'):
            del(l0[len(l0)-1])
        else:
            self.errorAVC.Show("Не найдена ';' в заголовке")
            self.updateProgress.Update(1)
            self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
            self.updateMenu.SetEnabled(True)
            return

        self.savcheader[len(self.savcheader)-1] = ''.join(l0)

        numSignals = len(self.savcheader)
        if(numSignals == 1 or numSignals == 0):
            self.errorAVC.Show("Сигналы не найдены")
            self.updateProgress.Update(1)
            self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
            self.updateMenu.SetEnabled(True)
            return

        self.updateProgress.setRangeProgressBar(1, len(self.savcheader))
        progressNum = 1
        self.updateStatus.Update("Открытие файла " + self.openFileName + ": Разделение шин на сигналы")
        #transform buses to particular signals
        for avcsgnlnm, avcsgnl in enumerate(self.savcheader):
            progressNum += 1
            self.updateProgress.Update(progressNum)
            if(avcsgnl.find('<') != -1 or avcsgnl.find('>') != -1 or avcsgnl.find(':') != -1):
                if(avcsgnl.find('<') == -1 or avcsgnl.find('>') == -1 or avcsgnl.find(':') == -1):
                    self.errorAVC.Show("Неправильный формат шины в заголовке")
                    self.updateProgress.Update(0)
                    self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
                    self.updateMenu.SetEnabled(True)
                    return
                for y in range(1,int(avcsgnl[avcsgnl.find('<') + 1 : avcsgnl.find(':')]) + 2):
                    self.savcheader.insert(avcsgnl.find('<') + y,avcsgnl[0:avcsgnl.find('<')] + '_' + str(y-1))
                self.savcheader.pop(y+avcsgnlnm)

        self.numSignals = len(self.savcheader)

        self.updateProgress.setRangeProgressBar(1, MAX_COMBO)
        progressNum = 1
        self.updateStatus.Update("Открытие файла " + self.openFileName + ": Разделение шин на сигналы")
        #write signals into combo boxes
        for x in range(1, MAX_COMBO):
            progressNum += 1
            self.updateProgress.Update(progressNum)
            for avcsgnl in self.savcheader:
                if(avcsgnl != "FORMAT" and avcsgnl != "NOP"):
                    noAssignedSignals = False
                    self.comboBox[x-1].addItem(avcsgnl)

        if(noAssignedSignals):
            self.errorAVC.Show("Нет назначенных сигналов в файле")
            self.updateProgress.Update(1)
            self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
            self.updateMenu.SetEnabled(True)
            return

        for avcsgnl in self.savcheader:
            if(avcsgnl != "NOP"):
                self.avcheaderindex.append(avcsgnl)

        #set indices from AVC file
        sindex = 1
        self.updateProgress.setRangeProgressBar(1, len(self.savcheader))
        progressNum = 1
        self.updateStatus.Update("Открытие файла " + self.openFileName + ": Обновление меню")
        for x in range(1, len(self.savcheader)):
            progressNum += 1
            self.updateProgress.Update(progressNum)
            if(self.savcheader[x] == "NOP"):
                self.comboBox[x-1].setCurrentIndex(0)
            else:
                self.comboBox[x-1].setCurrentIndex(sindex)
                sindex += 1

        self.numVectors = sum(1 for line in avcfile)

        self.updateProgress.setRangeProgressBar(1, self.numVectors)
        avcfile.seek(0,0)
        progressNum = 1
        numLine = 2
        self.updateStatus.Update("Открытие файла " + self.openFileName + ": Построение матрицы сигналов")
        #make AVC signals matrix
        self.avcsgnlbuffer.clear()
        for x in avcfile:
            progressNum += 1
            self.updateProgress.Update(progressNum)
            avcsgnline = x.split()
            if(avcsgnline):
                if(avcsgnline[0] != 'Xx' and avcsgnline[0] != 'FORMAT'):
                    if(avcsgnline[0] == 'R1' and avcsgnline[1] == 'cyc'):
                        avcsgnline.remove('R1')
                        avcsgnline.remove('cyc')
                    else:
                        self.errorAVC.Show("Неправильный формат вектора в строке " + str(numLine))
                        self.updateProgress.Update(1)
                        self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
                        self.updateMenu.SetEnabled(True)
                        return
                    if(len(avcsgnline) != 0):
                        l = list(avcsgnline[len(avcsgnline)-1])
                        if(len(l) > 1):
                            del(l[len(l)-1])
                        else:
                            self.errorAVC.Show("Пропущена ';' в конце вектора в строке " + str(numLine))
                            self.updateProgress.Update(1)
                            self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
                            self.updateMenu.SetEnabled(True)
                            return
                    else:
                        self.errorAVC.Show("Отсутствуют сигналы в векторе в строке " + str(numLine))
                        self.updateProgress.Update(1)
                        self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
                        self.updateMenu.SetEnabled(True)
                        return
                    avcsgnline[len(avcsgnline)-1] = "".join(l)
                    numSignals = 0
                    for y in avcsgnline:
                        z = list(y)
                        for sgnl in z:
                            numSignals += 1
                            if(sgnl != "x" and sgnl != "H" and sgnl != "L" and sgnl != "1" and sgnl != "0"):
                                self.errorAVC.Show("Недопустимый символ в строке " + str(numLine))
                                self.updateProgress.Update(1)
                                self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
                                self.updateMenu.SetEnabled(True)
                                return
                    if(numSignals != self.numSignals-1):
                        self.errorAVC.Show("Вектор не соответствует заголовку в строке " + str(numLine))
                        self.updateProgress.Update(1)
                        self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
                        self.updateMenu.SetEnabled(True)
                        return
                    self.avcsgnlbuffer.append(avcsgnline)
                    numLine += 1
                    if(numLine > MAX_VECTORS-1):
                        self.errorAVC.Show("Число векторов в AVC файле превышает максимальное (7 200 000)")
                        self.updateProgress.Update(1)
                        self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
                        self.updateMenu.SetEnabled(True)
                        return
        if(numLine == 2):
            self.errorAVC.Show("Отсутствуют AVC вектора")
            self.updateProgress.Update(1)
            self.updateStatus.Update("Ошибка при открытии " + self.openFileName)
            self.updateMenu.SetEnabled(True)
            return
        self.updateProgress.setRangeProgressBar(1, len(self.avcsgnlbuffer))
        progressNum = 1
        self.updateStatus.Update("Открытие файла " + self.openFileName + ": Разделение шин на сигналы")
        #split buses signals
        for row0 in self.avcsgnlbuffer:
            buses = False
            progressNum += 1
            self.updateProgress.Update(progressNum)
            for i,elem in enumerate(row0):
                if(len(elem) > 1):
                    buses = True
                    l1 = list(elem)
                    row0.pop(i)
                    for j in range(0,len(l1)):
                        row0.insert(i+j,elem[j])
            if(not buses):
                break

        self.updateProgress.Update(len(self.avcsgnlbuffer))
        self.updateStatus.Update("Файл " + self.openFileName + " открыт")
        self.updateMenu.SetEnabled(True)
        #close AVC file
        avcfile.close()
        self.fileOpened = True

    def OnMenuOpenAVCFile(self):

        #open AVC file dialog
        fileName = QFileDialog.getOpenFileName(self,"Open Image", "/home/dk_work/", "AVC File (*.avc)")
        if(fileName[0] != ''):
            sfileName = fileName[0].split('/')
            self.openFileName = sfileName.pop()
            self.openFileSize = os.path.getsize(fileName[0])
            self.statusBar.showMessage("Выбран файл: " + self.openFileName)
            self.progressBar.setRange(0,100)
            self.progressBar.setVisible(True)
            thread1 = threading.Thread(target=self.OnOpenAVCFile, args=(fileName[0],))
            thread1.start()

    def OnWriteAVCSDFile(self,fileName):

        if(fileName.find('.') == -1):
            f = open(fileName + ".avc", 'w')
        else:
            f = open(fileName, 'w')

        sfileName = fileName.split('/')
        sbfileName = sfileName.pop()
        self.updateStatus.Update("Сохранение файла: " + sbfileName + ", ждите...")
        avcnewheader = list()

        self.updateMenu.SetEnabled(False)

        #write AVC SD file header
        f.write("FORMAT ")
        for i,x in enumerate(self.comboBox):
            if(i < MAX_AVC_SIGNALS):
                if(x.currentIndex() == 0):
                    f.write("NOP ")
                    avcnewheader.append("NOP")
                else:
                    f.write(self.avcheaderindex[x.currentIndex()] + " ")
                    avcnewheader.append(self.avcheaderindex[x.currentIndex()])
        f.seek(f.tell()-1,0)
        f.write(";")
        #write AVC SD file data
        load = 0
        index = 1
        for i,row in enumerate(self.avcsgnlbuffer):
            load += 1
            self.updateProgress.Update(load)
            f.write("\nR1 cyc ")
            if(self.configType == ConfigurationType.FAST16_SLOWTS16):
                for j,x in enumerate(self.comboBox):
                    if(j < MAX_AVC_SIGNALS):
                        if(x.currentIndex() == 0):
                            f.write("0 ") #f.write("x ") - for 3-state than 0
                        elif(j < 16):
                            for cindex,y in enumerate(self.savcheader):
                                if(y == x.currentText()):
                                    index = cindex
                                    break
                            f.write(row[index-1] + " ")
                        else:
                            for cindex,y in enumerate(self.savcheader):
                                if(y == x.currentText()):
                                    index = cindex
                                    break
                            if(i < (self.numVectors/2)-1):
                                if(self.avcsgnlbuffer[2*i+1][(index)-1] == 'H'):
                                    f.write("H ")
                                elif(self.avcsgnlbuffer[2*i+1][(index)-1] == 'L'):
                                    f.write("L ")
                                else:
                                    f.write(self.avcsgnlbuffer[2*i][(index)-1] + " ")
                            else:
                                f.write("0 ")
            f.seek(f.tell()-1,0)
            f.write(";")

        #finalyze AVC SD file
        f.write("\n")
        f.write("Xx XXX ")
        for x in self.comboBox:
            f.write("x ")
        f.seek(f.tell()-1,0)
        f.write(";")
        self.updateStatus.Update("Файл: " + sbfileName + " сохранен")
        #close AVC SD file
        f.close()
        self.updateMenu.SetEnabled(True)

    def OnMenuSaveAVCFile(self):

        fileName = QFileDialog.getSaveFileName(self,"Open AVC file", "/home/dk_work/", "AVC File (AVC1READER Format) (*.avc)")
        if(fileName[0] != ''):
            self.progressBar.setRange(0,len(self.avcsgnlbuffer))
            self.progressBar.setVisible(True)
            thread0 = threading.Thread(target=self.OnWriteAVCSDFile, args=(fileName[0],))
            thread0.start()

    def OnUpdateSDDevice(self):
        for x in range(0,self.dialogCombo.count()):
            self.dialogCombo.removeItem(x)
        fdiskldev = subprocess.check_output(["fdisk","-l"], universal_newlines=True)
        fdiskldevl = fdiskldev.split()
        self.diskfound = 0
        for i,x in enumerate(fdiskldevl):
            if x.find("FAT32",0,5) != -1:
                self.diskfound = 1
                self.dialogCombo.addItem(fdiskldevl[i-6])
        if not self.diskfound:
                self.dialogCombo.addItem("<отсутствует>")
        self.dialogButton.button(QDialogButtonBox.Ok).setEnabled(self.diskfound)
        self.dialogUmountButton.setEnabled(self.diskfound)

    def OnMenuWriteAVCFile(self):
        self.progressBar.setValue(0)
        for x in range(0,self.dialogCombo.count()):
            self.dialogCombo.removeItem(x)
        radio_2 = self.sdDialog.findChild(QRadioButton, "radioButton_2")
        radio_1 = self.sdDialog.findChild(QRadioButton, "radioButton")
        radio_1.setEnabled(False)
        if radio_2.isChecked():
            fdiskldev = subprocess.check_output(["fdisk","-l"], universal_newlines=True)
            fdiskldevl = fdiskldev.split()
            self.diskfound = 0
            for i,x in enumerate(fdiskldevl):
                if x.find("FAT32",0,5) != -1:
                    self.diskfound = 1
                    self.dialogCombo.addItem(fdiskldevl[i-6])
            if not self.diskfound:
                self.dialogCombo.addItem("<отсутствует>")
        self.dialogButton.button(QDialogButtonBox.Ok).setEnabled(self.diskfound)
        self.dialogUmountButton.setEnabled(self.diskfound)
        self.sdDialog.setWindowTitle("Выберите SD устройство")
        self.sdDialog.setFixedSize(600,300)
        self.sdDialog.show()

    def OnMenuAboutAVCFile(self):
        self.propDialog.setWindowTitle("Свойства текущего AVC файла")
        self.propDialog.show()
        propEdit_1 = self.propDialog.findChild(QLineEdit, "lineEdit")
        propEdit_2 = self.propDialog.findChild(QLineEdit, "lineEdit_2")
        propEdit_3 = self.propDialog.findChild(QLineEdit, "lineEdit_3")
        propEdit_4 = self.propDialog.findChild(QLineEdit, "lineEdit_4")
        propEdit_5 = self.propDialog.findChild(QLineEdit, "lineEdit_5")
        propEdit_6 = self.propDialog.findChild(QLineEdit, "lineEdit_6")
        propEdit_7 = self.propDialog.findChild(QLineEdit, "lineEdit_7")
        propEdit_8 = self.propDialog.findChild(QLineEdit, "lineEdit_8")
        propEdit_1.setText(str(self.openFileSize))
        propEdit_2.setText(str(self.numVectors))
        propEdit_3.setText(str(self.numSignals-1))
        numFast = 0
        numSlowTS = 0
        numSlow = 0
        numSignalsMax = 0
        if(self.configType == ConfigurationType.FAST16_SLOWTS16):
            for x in range(0,16):
                if(self.comboBox[x].currentIndex() != 0):
                    numFast += 1
            for y in range(16,32):
                if(self.comboBox[y].currentIndex() != 0):
                    numSlowTS += 1
            numSignalsMax = 32
        numSignalsCurrent = numFast + numSlowTS + numSlow
        propEdit_4.setText(str(numFast))
        propEdit_5.setText(str(numSlowTS))
        propEdit_8.setText(str(numSlow))
        propEdit_6.setText(str(numSignalsMax))
        propEdit_7.setText(str(numSignalsCurrent) + " (" + '{:.5}'.format(str((numSignalsCurrent*100)/numSignalsMax)) + "%)")

    def OnMenuArria10Pins(self):
        self.pinsDialog.setWindowTitle("Назначенные вывода для ПЛИС")
        self.pinsDialog.setFixedSize(589,311)
        self.pinsDialog.show()
        pinsEdit = self.pinsDialog.findChild(QTextEdit, "textEdit")
        pinscount = 0
        self.pinstext = ""
        for i,x in enumerate(self.comboBox):
            if(x.currentIndex() != 0):
                pinscount += 1
                self.pinstext += "set_location_assignment " + self.assignPinsArria10(i) + " -to " + x.itemText(x.currentIndex()) + "_pad -comment " + x.itemText(x.currentIndex()) + "\n"

        if(not pinscount):
            self.openQSFButton.setEnabled(0)
            pinsEdit.setText("Сигналы для назначения отсутствуют, установите сигналы\n")
        else:
            self.openQSFButton.setEnabled(1)
            pinsEdit.setText(self.pinstext)

    def OnQSFFileOpen(self):
         fileName = QFileDialog.getOpenFileName(self,"Open QSF File", "/home/dk_work/", "Quartus II project (*.qsf)")
         if(fileName[0] != ''):
            qsfmessage = QMessageBox(QMessageBox.Warning,"Предупреждение","Удалите ранее назначенные сигналы проекта, во избежании конфликта",QMessageBox.Ok,self)
            qsfmessage.show()
            qsfmessage.exec_()
            qsffile = open(fileName[0], 'a')
            qsffile.write("\n")
            qsffile.write(self.pinstext)
            qsffile.close()
            self.pinsDialog.close()

    def OnMenuConfig(self):
        self.configDialog.setFixedSize(881,721)
        self.configDialog.setWindowTitle("Конфигурация тестера AVC1READER")
        self.configDialog.show()

    def OnMenu(self):
        if(self.comboBox[0].count() > 1 and self.fileOpened):
            self.menuSaveAVCFile.setEnabled(True)
            self.menuAboutAVCFile.setEnabled(True)
            self.menuWriteAVCFile.setEnabled(True)
            self.menuClose.setEnabled(True)
            self.menuArria10.setEnabled(True)
        else:
            self.menuSaveAVCFile.setEnabled(False)
            self.menuAboutAVCFile.setEnabled(False)
            self.menuWriteAVCFile.setEnabled(False)
            self.menuClose.setEnabled(False)
            self.menuArria10.setEnabled(False)

    def OnMenuClose(self):
        for x in range(1, MAX_COMBO):
            if self.comboBox[x-1].count() > 1:
                for i in range(self.comboBox[x-1].count(),0,-1):
                    self.comboBox[x-1].removeItem(i)

        for x in range(1, MAX_COMBO):
            self.comboBox[x-1].setCurrentIndex(0)

        self.fileOpened = False
        self.menuSaveAVCFile.setEnabled(False)
        self.menuAboutAVCFile.setEnabled(False)
        self.menuWriteAVCFile.setEnabled(False)
        self.menuClose.setEnabled(False)
        self.menuArria10.setEnabled(False)

        self.progressBar.setVisible(False)
        self.statusBar.showMessage("Откройте AVC файл")

    def OnMenuExit(self):
        sys.exit(0)

    def OnMenuHelp(self):
        menuhelp = QMessageBox(QMessageBox.Information,"Пользуйтесь как понимаете","А здесь должна быть помощь",QMessageBox.Ok,self)
        menuhelp.show()
        menuhelp.exec_()

    def OnMenuAbout(self):
        menuabout = QMessageBox(QMessageBox.Information,"О программе AVC1WRITER","Эта GUI программа формирует AVC файл для тестера AVC1READER на базе платы DE2-115",QMessageBox.Ok,self)
        menuabout.show()
        menuabout.exec_()

    def updateProgressBar(self,value):
        self.progressBar.setValue(value)

    def setRangeProgressBar(self,min,max):
        self.progressBar.setRange(min,max)

    def updateStatusBar(self,message):
        self.statusBar.showMessage(message)

    def errorMessage(self,message):
        self.errorMessageBox.setText(message)
        self.errorMessageBox.show()
        self.errorMessageBox.exec_()

    def setMenuEnabled(self,enabled):
        self.menuBar.setEnabled(enabled)

    def createErrorMessage(self):
        self.errorAVC = ErrorMessageBox()
        self.errorAVC.errorShow.connect(self.errorMessage)
        self.errorMessageBox = QMessageBox(QMessageBox.Critical,"Ошибка в AVC файле","",QMessageBox.Ok,self)

    def createCombo(self):
        for x in range(1, MAX_COMBO):
            self.comboBox.append(self.findChild(QComboBox, "comboBox_" + str(x)))
            self.comboBox[x-1].setEnabled(False)
        #connect callbacks to combo boxes
        self.connectCombo()
        for x in range(1, MAX_AVC_SIGNALS+1):
            self.comboBox[x-1].setEnabled(True)
        resetButton = self.findChild(QPushButton, "pushButton")
        resetButton.clicked.connect(self.OnSignalsReset)

    def createDialogControls(self):
        self.dialogCombo = self.sdDialog.findChild(QComboBox, "comboBox")
        self.dialogButton = self.sdDialog.findChild(QDialogButtonBox, "buttonBox")
        self.dialogUmountButton = self.sdDialog.findChild(QPushButton, "pushButton_2")
        self.dialogPushButton = self.sdDialog.findChild(QPushButton, "pushButton")
        self.formatMessageBox = QMessageBox(QMessageBox.Warning,"","",QMessageBox.Cancel | QMessageBox.Ok,self.sdDialog)
        self.dialogCombo.currentIndexChanged.connect(self.OnIndexChangedDialogCombo)
        self.dialogCombo.currentIndexChanged.connect(self.OnIndexChangedDialogCombo)
        self.dialogButton.button(QDialogButtonBox.Ok).setEnabled(False)
        self.dialogUmountButton.setEnabled(False)
        self.dialogButton.button(QDialogButtonBox.Ok).clicked.connect(self.formatButtonClicked)
        self.dialogButton.button(QDialogButtonBox.Cancel).clicked.connect(self.formatCancelButtonClicked)
        self.dialogPushButton.clicked.connect(self.OnUpdateSDDevice)
        self.dialogUmountButton.clicked.connect(self.umountButtonClicked)
        self.formatMessageBox.button(QMessageBox.Ok).clicked.connect(self.formatOkButtonClicked)
        self.opensdmessage = QMessageBox(QMessageBox.Warning,"Копирование на SD карту","Откройте папку SD карты для продолжения",QMessageBox.Ok | QMessageBox.Cancel,self)
        self.opensdmessage.button(QMessageBox.Ok).clicked.connect(self.checkOpenedSDOk)
        self.opensdmessage.button(QMessageBox.Cancel).clicked.connect(self.checkOpenedSDExit)

    def createQSFDialogControls(self):
        self.openQSFButton = self.pinsDialog.findChild(QPushButton, "pushButton")
        self.openQSFButton.clicked.connect(self.OnQSFFileOpen)

    def createMenuBar(self):
        boxlayout = QVBoxLayout(self)
        self.menuBar = QMenuBar()
        filemenu = QMenu("Файл")
        pinsmenu = QMenu("Назначение выводов")
        configmenu = QMenu("Конфигурация тестера")
        helpmenu = QMenu("Помощь")
        self.menuBar.addMenu(filemenu)
        self.menuBar.addMenu(pinsmenu)
        self.menuBar.addMenu(configmenu)
        self.menuBar.addMenu(helpmenu)
        menuOpenAVCFile = QAction("Открыть AVC",self.menuBar)
        self.menuSaveAVCFile = QAction("Сохранить AVC",self.menuBar)
        self.menuWriteAVCFile = QAction("Записать AVC на SD",self.menuBar)
        self.menuAboutAVCFile = QAction("Свойства AVC",self.menuBar)
        self.menuClose = QAction("Закрыть AVC",self.menuBar)
        menuExit = QAction("Выход",self.menuBar)
        self.menuArria10 = QAction("Arria 10 GX FPGA Development Kit",self.menuBar)
        menuHelp = QAction("Помощь",self.menuBar)
        menuCalc = QAction("Расчет конфигурации",self.menuBar)
        menuAbout = QAction("О программе",self.menuBar)
        self.menuBar.hovered.connect(self.OnMenu)
        menuCalc.triggered.connect(self.OnMenuConfig)
        QObject.connect(menuOpenAVCFile, SIGNAL('triggered()'), self.OnMenuOpenAVCFile)
        QObject.connect(self.menuSaveAVCFile, SIGNAL('triggered()'), self.OnMenuSaveAVCFile)
        QObject.connect(self.menuWriteAVCFile, SIGNAL('triggered()'), self.OnMenuWriteAVCFile)
        QObject.connect(self.menuAboutAVCFile, SIGNAL('triggered()'), self.OnMenuAboutAVCFile)
        QObject.connect(self.menuArria10, SIGNAL('triggered()'), self.OnMenuArria10Pins)
        QObject.connect(self.menuClose, SIGNAL('triggered()'), self.OnMenuClose)
        QObject.connect(menuExit, SIGNAL('triggered()'), self.OnMenuExit)
        QObject.connect(menuHelp, SIGNAL('triggered()'), self.OnMenuHelp)
        QObject.connect(menuAbout, SIGNAL('triggered()'), self.OnMenuAbout)
        filemenu.addAction(menuOpenAVCFile)
        filemenu.addAction(self.menuSaveAVCFile)
        filemenu.addAction(self.menuWriteAVCFile)
        filemenu.addAction(self.menuAboutAVCFile)
        filemenu.addAction(self.menuClose)
        filemenu.addAction(menuExit)
        pinsmenu.addAction(self.menuArria10)
        helpmenu.addAction(menuHelp)
        configmenu.addAction(menuCalc)
        helpmenu.addAction(menuAbout)
        self.menuSaveAVCFile.setEnabled(False)
        self.menuAboutAVCFile.setEnabled(False)
        self.menuWriteAVCFile.setEnabled(False)
        self.menuClose.setEnabled(False)
        self.menuArria10.setEnabled(False)
        self.layout().setMenuBar(self.menuBar)
        self.updateMenu = UpdateMenu()
        self.updateMenu.updateMenu.connect(self.setMenuEnabled)

    def createStatusBar(self):
        self.layout().addWidget(self.statusBar)
        self.statusBar.showMessage("Откройте AVC файл")
        self.statusBar.addPermanentWidget(self.progressBar)
        self.layout().setAlignment(self.statusBar,Qt.AlignBottom)
        self.progressBar.setFixedWidth(WINDOW_WIDTH/4)
        self.progressBar.setValue(False)
        self.progressBar.setTextVisible(True)
        self.progressBar.setVisible(False)
        self.updateProgress = UpdateProgress()
        self.updateStatus = UpdateStatus()
        self.updateProgress.updateProgress.connect(self.updateProgressBar)
        self.updateProgress.setRange.connect(self.setRangeProgressBar)
        self.updateStatus.updateStatus.connect(self.updateStatusBar)
        QMetaObject.connectSlotsByName(self)

    def formatButtonClicked(self):
        self.formatMessageBox.setWindowTitle("Запись AVC файла")
        self.formatMessageBox.setText("ВНИМАНИЕ !\nБудет выполнено форматирование: " + self.dialogCombo.itemText(self.dialogCombo.currentIndex()) + "\nВСЕ ДАННЫЕ БУДУТ УТЕРЯНЫ !!!\nТочно продолжить ???")
        self.formatMessageBox.show()
        self.formatMessageBox.exec_()

    def formatCancelButtonClicked(self):
        self.sdDialog.close()

    def umountButtonClicked(self):
        try:
            subprocess.check_output(["umount",self.dialogCombo.itemText(self.dialogCombo.currentIndex())], universal_newlines=True)

        except subprocess.CalledProcessError as e:
            umountmessage = QMessageBox(QMessageBox.Warning,"Ошибка: " + e.cmd[0],"Не удалось размонтировать " + self.dialogCombo.itemText(self.dialogCombo.currentIndex()),QMessageBox.Ok,self)
            umountmessage.show()
            umountmessage.exec_()

    def checkOpenedSDOk(self):
        mount = subprocess.check_output(["mount"], universal_newlines=True)
        mountlines = mount.splitlines()
        self.opensdmessage.close()
        for mountline in mountlines:
            mountwords = mountline.split()
            for x in mountwords:
                if(x == self.dialogCombo.itemText(self.dialogCombo.currentIndex())):
                    fileName = mountwords[2]
                    thread2 = threading.Thread(target=self.OnWriteAVCSDFile, args=(fileName  + "/" + self.openFileName,))
                    thread2.start()
                    return
        self.opensdmessage.show()

    def checkOpenedSDExit(self):
        self.opensdmessage.close()

    def formatOkButtonClicked(self):
        try:
            self.sdDialog.close()
            subprocess.check_output(["mkfs.vfat",self.dialogCombo.itemText(self.dialogCombo.currentIndex())], universal_newlines=True)
            self.opensdmessage.show()
            self.opensdmessage.exec_()
        except subprocess.CalledProcessError as e:
            checkoutputmessage = QMessageBox(QMessageBox.Warning,"Ошибка: " + e.cmd[0],"Команда " + e.cmd[0] + " не выполнена\nЗакройте директорию и файлы на SD карте, либо подключите SD карту или кардридер заново (размонтируйте), либо проверьте права администратора",QMessageBox.Ok,self)
            checkoutputmessage.show()
            checkoutputmessage.exec_()

    def OnSignalsReset(self):
        for x in range(1, MAX_COMBO):
            self.comboBox[x-1].setCurrentIndex(0)

    def assignPinsArria10(self,index):
        return {
            0: "PIN_AT14",
            1: "PIN_AR14",
            2: "PIN_AR9",
            3: "PIN_AT9",
            4: "PIN_AW13",
            5: "PIN_AV13",
            6: "PIN_AY11",
            7: "PIN_AY10",
            8: "PIN_AU12",
            9: "PIN_AU11",
            10: "PIN_AW19",
            11: "PIN_AV19",
            12: "PIN_AP17",
            13: "PIN_AR17",
            14: "PIN_AU18",
            15: "PIN_AT18",
            16: "PIN_AT17",
            17: "PIN_AU17",
            18: "PIN_AN20",
            19: "PIN_AP19",
            20: "PIN_AR22",
            21: "PIN_AT22",
            22: "PIN_AV11",
            23: "PIN_AW11",
            24: "PIN_BB15",
            25: "PIN_BC15",
            26: "PIN_AT19",
            27: "PIN_AT20",
            28: "PIN_AY16",
            29: "PIN_AW16",
            30: "PIN_BC18",
            31: "PIN_BD18",
        }[index]

    def connectCombo(self):
        self.comboBox[0].currentIndexChanged.connect(self.OnIndexChangedCombo0)
        self.comboBox[1].currentIndexChanged.connect(self.OnIndexChangedCombo1)
        self.comboBox[2].currentIndexChanged.connect(self.OnIndexChangedCombo2)
        self.comboBox[3].currentIndexChanged.connect(self.OnIndexChangedCombo3)
        self.comboBox[4].currentIndexChanged.connect(self.OnIndexChangedCombo4)
        self.comboBox[5].currentIndexChanged.connect(self.OnIndexChangedCombo5)
        self.comboBox[6].currentIndexChanged.connect(self.OnIndexChangedCombo6)
        self.comboBox[7].currentIndexChanged.connect(self.OnIndexChangedCombo7)
        self.comboBox[8].currentIndexChanged.connect(self.OnIndexChangedCombo8)
        self.comboBox[9].currentIndexChanged.connect(self.OnIndexChangedCombo9)
        self.comboBox[10].currentIndexChanged.connect(self.OnIndexChangedCombo10)
        self.comboBox[11].currentIndexChanged.connect(self.OnIndexChangedCombo11)
        self.comboBox[12].currentIndexChanged.connect(self.OnIndexChangedCombo12)
        self.comboBox[13].currentIndexChanged.connect(self.OnIndexChangedCombo13)
        self.comboBox[14].currentIndexChanged.connect(self.OnIndexChangedCombo14)
        self.comboBox[15].currentIndexChanged.connect(self.OnIndexChangedCombo15)
        self.comboBox[16].currentIndexChanged.connect(self.OnIndexChangedCombo16)
        self.comboBox[17].currentIndexChanged.connect(self.OnIndexChangedCombo17)
        self.comboBox[18].currentIndexChanged.connect(self.OnIndexChangedCombo18)
        self.comboBox[19].currentIndexChanged.connect(self.OnIndexChangedCombo19)
        self.comboBox[20].currentIndexChanged.connect(self.OnIndexChangedCombo20)
        self.comboBox[21].currentIndexChanged.connect(self.OnIndexChangedCombo21)
        self.comboBox[22].currentIndexChanged.connect(self.OnIndexChangedCombo22)
        self.comboBox[23].currentIndexChanged.connect(self.OnIndexChangedCombo23)
        self.comboBox[24].currentIndexChanged.connect(self.OnIndexChangedCombo24)
        self.comboBox[25].currentIndexChanged.connect(self.OnIndexChangedCombo25)
        self.comboBox[26].currentIndexChanged.connect(self.OnIndexChangedCombo26)
        self.comboBox[27].currentIndexChanged.connect(self.OnIndexChangedCombo27)
        self.comboBox[28].currentIndexChanged.connect(self.OnIndexChangedCombo28)
        self.comboBox[29].currentIndexChanged.connect(self.OnIndexChangedCombo29)
        self.comboBox[30].currentIndexChanged.connect(self.OnIndexChangedCombo30)
        self.comboBox[31].currentIndexChanged.connect(self.OnIndexChangedCombo31)
        self.comboBox[32].currentIndexChanged.connect(self.OnIndexChangedCombo32)
        self.comboBox[33].currentIndexChanged.connect(self.OnIndexChangedCombo33)
        self.comboBox[34].currentIndexChanged.connect(self.OnIndexChangedCombo34)
        self.comboBox[35].currentIndexChanged.connect(self.OnIndexChangedCombo35)
        self.comboBox[36].currentIndexChanged.connect(self.OnIndexChangedCombo36)
        self.comboBox[37].currentIndexChanged.connect(self.OnIndexChangedCombo37)
        self.comboBox[38].currentIndexChanged.connect(self.OnIndexChangedCombo38)
        self.comboBox[39].currentIndexChanged.connect(self.OnIndexChangedCombo39)
        self.comboBox[40].currentIndexChanged.connect(self.OnIndexChangedCombo40)
        self.comboBox[41].currentIndexChanged.connect(self.OnIndexChangedCombo41)
        self.comboBox[42].currentIndexChanged.connect(self.OnIndexChangedCombo42)
        self.comboBox[43].currentIndexChanged.connect(self.OnIndexChangedCombo43)
        self.comboBox[44].currentIndexChanged.connect(self.OnIndexChangedCombo44)
        self.comboBox[45].currentIndexChanged.connect(self.OnIndexChangedCombo45)
        self.comboBox[46].currentIndexChanged.connect(self.OnIndexChangedCombo46)
        self.comboBox[47].currentIndexChanged.connect(self.OnIndexChangedCombo47)
        self.comboBox[48].currentIndexChanged.connect(self.OnIndexChangedCombo48)
        self.comboBox[49].currentIndexChanged.connect(self.OnIndexChangedCombo49)
        self.comboBox[50].currentIndexChanged.connect(self.OnIndexChangedCombo50)
        self.comboBox[51].currentIndexChanged.connect(self.OnIndexChangedCombo51)
        self.comboBox[52].currentIndexChanged.connect(self.OnIndexChangedCombo52)
        self.comboBox[53].currentIndexChanged.connect(self.OnIndexChangedCombo53)
        self.comboBox[54].currentIndexChanged.connect(self.OnIndexChangedCombo54)
        self.comboBox[55].currentIndexChanged.connect(self.OnIndexChangedCombo55)
        self.comboBox[56].currentIndexChanged.connect(self.OnIndexChangedCombo56)
        self.comboBox[57].currentIndexChanged.connect(self.OnIndexChangedCombo57)
        self.comboBox[58].currentIndexChanged.connect(self.OnIndexChangedCombo58)
        self.comboBox[59].currentIndexChanged.connect(self.OnIndexChangedCombo59)
        self.comboBox[60].currentIndexChanged.connect(self.OnIndexChangedCombo60)
        self.comboBox[61].currentIndexChanged.connect(self.OnIndexChangedCombo61)
        self.comboBox[62].currentIndexChanged.connect(self.OnIndexChangedCombo62)
        self.comboBox[63].currentIndexChanged.connect(self.OnIndexChangedCombo63)
        self.comboBox[64].currentIndexChanged.connect(self.OnIndexChangedCombo64)
        self.comboBox[65].currentIndexChanged.connect(self.OnIndexChangedCombo65)
        self.comboBox[66].currentIndexChanged.connect(self.OnIndexChangedCombo66)
        self.comboBox[67].currentIndexChanged.connect(self.OnIndexChangedCombo67)
        self.comboBox[68].currentIndexChanged.connect(self.OnIndexChangedCombo68)
        self.comboBox[69].currentIndexChanged.connect(self.OnIndexChangedCombo69)
        self.comboBox[70].currentIndexChanged.connect(self.OnIndexChangedCombo70)
        self.comboBox[71].currentIndexChanged.connect(self.OnIndexChangedCombo71)
        self.comboBox[72].currentIndexChanged.connect(self.OnIndexChangedCombo72)
        self.comboBox[73].currentIndexChanged.connect(self.OnIndexChangedCombo73)
        self.comboBox[74].currentIndexChanged.connect(self.OnIndexChangedCombo74)
        self.comboBox[75].currentIndexChanged.connect(self.OnIndexChangedCombo75)
        self.comboBox[76].currentIndexChanged.connect(self.OnIndexChangedCombo76)
        self.comboBox[77].currentIndexChanged.connect(self.OnIndexChangedCombo77)
        self.comboBox[78].currentIndexChanged.connect(self.OnIndexChangedCombo78)
        self.comboBox[79].currentIndexChanged.connect(self.OnIndexChangedCombo79)
        self.comboBox[80].currentIndexChanged.connect(self.OnIndexChangedCombo80)
        self.comboBox[81].currentIndexChanged.connect(self.OnIndexChangedCombo81)
        self.comboBox[82].currentIndexChanged.connect(self.OnIndexChangedCombo82)
        self.comboBox[83].currentIndexChanged.connect(self.OnIndexChangedCombo83)
        self.comboBox[84].currentIndexChanged.connect(self.OnIndexChangedCombo84)
        self.comboBox[85].currentIndexChanged.connect(self.OnIndexChangedCombo85)
        self.comboBox[86].currentIndexChanged.connect(self.OnIndexChangedCombo86)
        self.comboBox[87].currentIndexChanged.connect(self.OnIndexChangedCombo87)
        self.comboBox[88].currentIndexChanged.connect(self.OnIndexChangedCombo88)
        self.comboBox[89].currentIndexChanged.connect(self.OnIndexChangedCombo89)
        self.comboBox[90].currentIndexChanged.connect(self.OnIndexChangedCombo90)
        self.comboBox[91].currentIndexChanged.connect(self.OnIndexChangedCombo91)
        self.comboBox[92].currentIndexChanged.connect(self.OnIndexChangedCombo92)
        self.comboBox[93].currentIndexChanged.connect(self.OnIndexChangedCombo93)
        self.comboBox[94].currentIndexChanged.connect(self.OnIndexChangedCombo94)
        self.comboBox[95].currentIndexChanged.connect(self.OnIndexChangedCombo95)
        self.comboBox[96].currentIndexChanged.connect(self.OnIndexChangedCombo96)
        self.comboBox[97].currentIndexChanged.connect(self.OnIndexChangedCombo97)
        self.comboBox[98].currentIndexChanged.connect(self.OnIndexChangedCombo98)
        self.comboBox[99].currentIndexChanged.connect(self.OnIndexChangedCombo99)
        self.comboBox[100].currentIndexChanged.connect(self.OnIndexChangedCombo100)
        self.comboBox[101].currentIndexChanged.connect(self.OnIndexChangedCombo101)
        self.comboBox[102].currentIndexChanged.connect(self.OnIndexChangedCombo102)
        self.comboBox[103].currentIndexChanged.connect(self.OnIndexChangedCombo103)

    def OnIndexChangedDialogCombo(self,index):
        label_2 = self.sdDialog.findChild(QLabel, "label_2")
        if(self.diskfound):
            if(self.dialogCombo.itemText(self.dialogCombo.currentIndex()) != ''):
                fdiskldev = subprocess.check_output(["fdisk","-l","".join(re.findall('\D', self.dialogCombo.itemText(self.dialogCombo.currentIndex())))], universal_newlines=True)
                label_2.setText(fdiskldev)
        else:
            label_2.setText("SD устройство не найдено\nПодключите SD устройство")

    def OnIndexChangedCombo0(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[0]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo1(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[1]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo2(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[2]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo3(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[3]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo4(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[4]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo5(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[5]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo6(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[6]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo7(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[7]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo8(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[8]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo9(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[9]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo10(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[10]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo11(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[11]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo12(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[12]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo13(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[13]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo14(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[14]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo15(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[15]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo16(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[16]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo17(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[17]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo18(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[18]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo19(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[19]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo20(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[20]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo21(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[21]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo22(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[22]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo23(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[23]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo24(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[24]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo25(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[25]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo26(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[26]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo27(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[27]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo28(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[28]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo29(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[29]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo30(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[30]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo31(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[31]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo32(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[32]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo33(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[33]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo34(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[34]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo35(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[35]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo36(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[36]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo37(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[37]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo38(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[38]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo39(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[39]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo40(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[40]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo41(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[41]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo42(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[42]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo43(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[43]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo44(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[44]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo45(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[45]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo46(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[46]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo47(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[47]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo48(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[48]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo49(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[49]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo50(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[50]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo51(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[51]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo52(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[52]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo53(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[53]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo54(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[54]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo55(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[55]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo56(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[56]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo57(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[57]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo58(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[58]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo59(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[59]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo60(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[60]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo61(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[61]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo62(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[62]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo63(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[63]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo64(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[64]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo65(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[65]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo66(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[66]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo67(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[67]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo68(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[68]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo69(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[69]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo70(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[70]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo71(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[71]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo72(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[72]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo73(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[73]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo74(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[74]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo75(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[75]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo76(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[76]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo77(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[77]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo78(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[78]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo79(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[79]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo80(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[80]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo81(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[81]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo82(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[82]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo83(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[83]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo84(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[84]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo85(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[85]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo86(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[86]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo87(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[87]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo88(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[88]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo89(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[89]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo90(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[90]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo91(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[91]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo92(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[92]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo93(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[93]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo94(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[94]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo95(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[95]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo96(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[96]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo97(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[97]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo98(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[98]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo99(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[99]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo100(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[100]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo101(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[101]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo102(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[102]):
                x.setCurrentIndex(0)

    def OnIndexChangedCombo103(self,index):
        for x in self.comboBox:
            if(x.currentIndex() == index and x != self.comboBox[103]):
                x.setCurrentIndex(0)

if __name__ == "__main__":
    app = QApplication([])
    widget = AVC1WRITER()
    widget.createCombo()
    widget.createDialogControls()
    widget.createMenuBar()
    widget.createStatusBar()
    widget.createErrorMessage()
    widget.createQSFDialogControls()
    widget.setFixedSize(WINDOW_WIDTH,WINDOW_HEIGHT)
    widget.setWindowTitle("AVC1WRITER")
    widget.show()
    sys.exit(app.exec_())

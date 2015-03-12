#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Copyright © 2014, W. van Ham, Radboud University Nijmegen
This file is part of Sleelab.

Sleelab is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Sleelab is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Sleelab.  If not, see <http://www.gnu.org/licenses/>.
'''

from __future__ import print_function
import logging, signal, argparse, csv, numpy as np
import OpenGL
OpenGL.ERROR_ON_COPY = True   # make sure we send numpy arrays
# PyQt (package python-qt4-gl on Ubuntu)
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtOpenGL import * 

# project files
from field import *

class Main(QMainWindow):
	def __init__(self, args):
		super(Main, self).__init__()
		self.initUI()
		self.args = args
		QTimer.singleShot(0, self.processCommandLine)
		
	def quit(self, signum=None, frame=None):
		logging.info("quitting")
		self.field.quit()
		qApp.quit()

	def initUI(self):
		#contents
		self.field = Field(self)


		# alternative content
		self.text = QLabel("Paused")
		self.text.setStyleSheet('text-align: right; color:#a00000; background-color:#000000; font-size: 100pt; font-family: Sans-Serif;')
		self.text.setMinimumSize(1400, 525)
		self.setCentralWidget(self.text)
		#self.setCentralWidget(self.field)		

		# dialogs
		self.errorMessageDialog = QErrorMessage(self)
		
		## menuBar
		loadAction = QAction(QIcon('icon/load.png'), '&Load', self)
		loadAction.setShortcut('Ctrl+L')
		loadAction.setStatusTip('Load experiment file')
		loadAction.triggered.connect(self.load)

		self.startIcon = QIcon('icon/start.png') 
		self.stopIcon = QIcon('icon/pause.png') #replace with next trial 
		self.startAction = QAction(self.startIcon, '&Start/Stop', self)
		self.startAction.setShortcut('Ctrl+R')
		self.startAction.setStatusTip('Start/Stop')
		self.startAction.triggered.connect(self.startStop)


		
		exitAction = QAction(QIcon('icon/quit.png'), '&Exit', self)
		exitAction.setShortcut('Ctrl+Q')
		exitAction.setStatusTip('Quit application')
		exitAction.triggered.connect(self.quit)
		
		self.fullIcon = QIcon('icon/full.png')
		self.fullAction = QAction(self.fullIcon, '&Full Screen', self)
		self.fullAction.setShortcut('ctrl+F')
		self.fullAction.setStatusTip('Toggle Full Screen')
		self.fullAction.triggered.connect(self.toggleFullScreen)

		self.stereoIcon = QIcon('icon/stereo.png')
		self.stereoAction = QAction(self.stereoIcon, '&Stereoscopic', self)
		self.stereoAction.setShortcut('ctrl+S')
		self.stereoAction.setStatusTip('Toggle Stereoscopic')
		self.stereoAction.triggered.connect(self.field.toggleStereo)

		self.leftAction = QAction('Left intensity', self)
		self.leftAction.setShortcut("<")
		self.leftAction.setStatusTip('Increase left eye intensity')
		self.leftAction.triggered.connect(lambda: self.field.stereoIntensity(relative=-1))
		self.leftAction.setEnabled(False)

		self.rightAction = QAction('Right intensity', self)
		self.rightAction.setShortcut(">")
		self.rightAction.setStatusTip('Increase right eye intensity')
		self.rightAction.triggered.connect(lambda: self.field.stereoIntensity(relative=1))
		self.rightAction.setEnabled(False)


		#up and down array key to scroll through targets during response phase
		self.downAction = QAction('Next Ball', self)
		self.downAction.setShortcut(Qt.Key_Down) 
		self.downAction.setStatusTip('Move to Next Ball')
		self.downAction.triggered.connect(lambda: self.field.resColor(relative=-1)) 
		self.downAction.setEnabled(False)

		self.newAction = QAction('NextTrial' , self)
		self.newAction.setShortcut(' ')
		self.newAction.setStatusTip('Confirm Response')
		self.newAction.triggered.connect(lambda: self.field.addData(self.field.pCorrect))
		self.newAction.setEnabled(False)


		self.upAction = QAction('Previous Ball', self)
		self.upAction.setShortcut(Qt.Key_Up)
		self.upAction.setStatusTip('Move to Previous Ball')
		self.upAction.triggered.connect(lambda: self.field.resColor(relative=1))
		self.upAction.setEnabled(False)

		#right key confirms choice of target during response phase
		self.confirmAction = QAction('Confirm Ball', self)
		self.confirmAction.setShortcut(Qt.Key_Right) 
		self.confirmAction.setStatusTip('Confirm Ball Choice')
		self.confirmAction.triggered.connect(self.field.resBall) 
		self.confirmAction.setEnabled(False)

		nextIcon = QIcon('icon/next.png')
		self.nextAction = QAction(nextIcon, 'Next trial', self)
		self.nextAction.setShortcut(Qt.Key_Left)
		self.nextAction.setStatusTip('next trial')
		self.nextAction.triggered.connect(self.field.conditions.next)
		self.nextAction.setEnabled(False)

		# populate the menu bar
		menubar = self.menuBar()
		fileMenu = menubar.addMenu('&File')
		fileMenu.addAction(self.startAction)
		fileMenu.addAction(exitAction)
		fileMenu.addAction(loadAction)

		viewMenu = menubar.addMenu('&View')
		viewMenu.addAction(self.fullAction)
		viewMenu.addAction(self.stereoAction)

		
		# make it also work when the menubar is hidden
		experimentMenu = menubar.addMenu('&Experiment')
		experimentMenu.addAction(self.upAction)
		experimentMenu.addAction(self.downAction)
		experimentMenu.addAction(self.confirmAction)
		experimentMenu.addAction(self.nextAction)
		experimentMenu.addAction(self.newAction)

		self.addAction(self.nextAction)
		self.addAction(self.upAction) #add space action for next
		self.addAction(self.confirmAction)
		self.addAction(self.downAction)
		self.addAction(self.newAction)
		self.addAction(self.startAction) 
		self.addAction(self.fullAction)
		self.addAction(self.stereoAction)
		self.addAction(exitAction)
		self.addAction(loadAction)

		self.statusBar().showMessage('Ready')
		self.setWindowTitle('SledBalls')
		self.show()

	#def startStop(self, event=None):
	#	if self.field.running == True:
	#		logging.info("sleep")
	#		self.field.running = False
	#		self.startAction.setIcon(self.startIcon)
	#		self.field.changeState()
	#		self.statusBar().showMessage('Not Running')
	#	else:
	#		logging.info("end sleep")
	#		self.field.running = True
	#		self.field.tOld = time.time()
	#		self.startAction.setIcon(self.stopIcon)
	#		self.statusBar().showMessage('Running')
			
	def startStop(self, event=None):
		if self.field.state=="sleep":
			logging.info("request state: end sleep")
			self.toggleText(False)
			self.field.requestSleep = False
			self.field.changeState()
			self.startAction.setIcon(self.stopIcon)
		else:
			logging.info("request state: sleep")
			self.field.requestSleep = True
			self.startAction.setIcon(self.startIcon)


	def load(self, event=None, fileName=None):
		"""Load new list of trials."""
		if os.path.isdir('data'):
				directory = 'data/'
		self.field.filename= os.path.join(directory,"motSub"+str(self.field.subject)+'.txt ') #probably move this when condityion is added
		self.field.savefile= open(self.field.filename,'w')
		self.nextAction.setEnabled(False)
		if fileName==None:
			fileName = QFileDialog.getOpenFileName(self, "Open file", filter="Experiment file (.csv)(*.csv)")
		if fileName==None:
			QMessageBox.question(self, 'Error', "No filename given?", QtGui.QMessageBox.Ok)
			return
		#try:
		self.field.conditions.load(fileName)
		self.field.initializeObjects()
		#except Exception as e:
		#	self.errorMessageDialog.showMessage("Could not read file: {}\n{}".format(fileName, e))
		#	raise e
			
		logging.info("load file {} with {} conditions".format(fileName, len(self.field.conditions.conditions)))		


	def toggleFullScreen(self, event=None):
		if(self.isFullScreen()):
			self.showNormal()
			self.menuBar().setVisible(True)
			self.statusBar().setVisible(True)
			self.setCursor(QCursor(Qt.ArrowCursor))
		else:
			self.showFullScreen()
			self.menuBar().setVisible(False)
			self.statusBar().setVisible(False)
			self.setCursor(QCursor(Qt.BlankCursor))

	def toggleText(self, text=True):
		if text:
			self.centralWidget().setParent(None) # if you do not do this the field widget will be deleted in the next line
			self.setCentralWidget(self.text)
		else:
			self.centralWidget().setParent(None)
			self.setCentralWidget(self.field)
	def processCommandLine(self):
		# process command line arguments (to be called with running event loop)
		args = self.args
		if args.subject:
			self.field.subject = args.subject
		if args.fullscreen:
			self.toggleFullScreen()
		if args.running:
			self.startStop()
		if args.experiment:
			self.load(fileName=args.experiment)
		self.field.connectSledServer(args.sledServer)     # defaults to simulator
		self.field.connectPositionServer(args.positionServer) # defaults to sledserver
		if args.stereo:
			self.field.toggleStereo(True)
		if args.stereoSim:
			self.field.toggleStereo(True, sim=True)
		if args.stereoIntensity:
			self.field.stereoIntensity(int(args.stereoIntensity))

		

def main(): 
	logger = logging.getLogger()
	logger.setLevel(logging.DEBUG)

	# parse command line arguments
	parser = argparse.ArgumentParser()
	parser.add_argument("-geometry", help="X11 option")
	parser.add_argument("-display", help="X11 option")
	parser.add_argument("-e", "--experiment", help="experiment input file (.csv)")
	parser.add_argument("-f", "--fullscreen", help="start in full screen mode", action="store_true")
	parser.add_argument("-s", "--sledServer", help="sled server, default to sled server simulator")
	parser.add_argument("-p", "--positionServer", help="position server, defaults to the sled server, but must be a first principles server when explicitly given, use 'mouse' for mouse")
	parser.add_argument("--stereo", help="Side by side stereoscopic view", action="store_true")
	parser.add_argument("--stereoSim", help="Simulating stereoscopic view", action="store_true")
	parser.add_argument("--stereoIntensity", help="Stereoscopic intensity balance -9 — 9")
	parser.add_argument("-r", "--running", help="start in running mode", action="store_true")
	parser.add_argument("--subject", help="Subject ID")
	args = parser.parse_args()	
	
	# make application and main window
	a = QApplication(sys.argv)
	a.setApplicationName("SledBalls")
	w = Main(args); 
	a.lastWindowClosed.connect(w.quit) # make upper right cross work
	signal.signal(signal.SIGINT, w.quit) # make ctrl-c work
	# main loop
	sys.exit(a.exec_())  # enter main loop (the underscore prevents using the keyword)

if __name__ == '__main__':
	main()   


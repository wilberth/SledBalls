#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Copyright © 2013, W. van Ham, Radboud University Nijmegen
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
import sys, math, time, numpy as np, random, serial, ctypes, re
import fpclient, sledclient, sledclientsimulator, transforms, objects, shader,conditions
import numpy.matlib

from rusocsci import buttonbox

#PyQt
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtOpenGL import *
#openGL
import OpenGL
OpenGL.ERROR_ON_COPY = True   # make sure we do not accidentally send other structures than numpy arrays
from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *
from OpenGL.arrays import vbo
from OpenGL.GL.shaders import *


 
 # Coordinate system:
 # The center of the screen is the origin of the model coordinate system.
 # Dimensions are in coherent international units (m, s, m/s, ...).
 # The viewer sits at pViewer. pViewer[2] (the distance to the screen)
 # must not change during the experiment. It is always positive.
 # The x-direction is to the right of the viewer, the y-direction is up.
 # Hence the coordinate system  is right handed.
 # dScreen is the dimension of the screen in m. If the height-width 
 # ratio of the screen is different from the height-width ratio (in 
 # pixels) of the window, then this program will assume that the pixels 
 # are not square.
 # Objects are only drawn if they are between zNear and zFar.
 # Stars are always between zNearStar and zFarStar, 
 # these are the experiment parameters zNear and zFar.

	

# field widget
class Field(QGLWidget):
	# space
	pViewer   = np.array([0, 0, 1.2])       # m, x,y,z-position of the viewer
	zNear     = 0.5*pViewer[2]              # m  viewable point nearest to viewer, now exp. var
	zFocal    = 0                           # m, position of physical screen, do not change this
	zFar      = -0.5*pViewer[2]             # m, viewable point furthest from viewer, now exp. var
	dEyes     = 0.063                       # m, distance between the eyes, now exp. var
	dScreen   = np.array([2.728, 1.02])     # m, size of the screen
	tMovement = 1.5                         # s, Movement time of sled
	#balls
	rBalls      = .04                        # m
	ballCollide = False
	#wall        = ((-dScreen[0]/4+rBalls, dScreen[0]/4-rBalls), (-dScreen[1]/4+rBalls, dScreen[1]/4-rBalls), (zFar/2+rBalls, zNear/2-rBalls))
	wall= ((-0.32, 0.32), (-0.32, 0.32), (-0.32, 0.32))
	wallCollide = True
	moveType="virtualSpring"
	
	def __init__(self, parent):
		super(Field, self).__init__(parent)
		

		self.setMinimumSize(1400, 525)
		self.state="sleep"
		

		# GL settings
		fmt = self.format()
		fmt.setDoubleBuffer(True)    # always double buffers anyway (watch nVidia setting, do not do it there also in 120 Hz mode)
		fmt.setSampleBuffers(True)
		fmt.setSwapInterval(1)       # 0: no sync to v-refresh, number of syncs to wait for
		self.setFormat(fmt)          # PyQt
		if self.format().swapInterval()==-1:
			logging.warning("Setting swapinterval not possible, expect synching problems")
		if not self.format().doubleBuffer():
			logging.warning("Could not get double buffer; results will be suboptimal")
			
		self.tOld         = -1

		self.fadeFactor = 1.0         # no fade, fully exposed
		self.running = False
		self.conditions = conditions.Conditions(dataKeys=['subject','pCorrect','response','trajectFile'])
		
		try:
			self.shutter = buttonbox.Buttonbox() # optionally add port="COM17"
			self.openShutter(False, False)
		except Exception as e:
			print(e)

	def __del__(self):
		self.quit()

	def quit(self):
		if hasattr(self, "sledClient") and hasattr(self.sledClient, "stopStream"):
			print("closing sled client") # logger may not exist anymore
			self.sledClient.stopStream()
		if hasattr(self, "positionClient") and hasattr(self.positionClient, "stopStream"):
			print("closing FP client") # logger may not exist anymore
			self.positionClient.stopStream()

	def changeState(self):
		if self.state=="home" and self.requestSleep==True:
			self.state = "sleep"
			self.requestSleep = False
			self.parent().toggleText(True)
			self.sledClient.sendCommand("Lights On")
		elif self.state=="sleep" or self.state=="home": # and space bar is not pressed, needs changing
			self.sledClient.sendCommand("Lights Off")
			self.state = "wait"
			# intial sleep state for lights and additional things.
			QTimer.singleShot(3000,self.changeState) #length of wait
		elif self.state == "wait":
			self.state = "start"
			self.motionTrigger=0
	
			QTimer.singleShot(4000,self.changeState) #length of viewing targets
		elif self.state == "start":
			self.state = "running"
			self.startime=time.time()
			self.sledClient.sendCommand("Sinusoid Start" +str(self.conditions.trial['amplitude']) +str(self.conditions.trial['period']))
			print('{"TrialData'+'": [ ',file=self.savefile)
			print("[{:.6f},{:s}],".format(time.time()-self.startime, ",".join(map(str,self.pBalls.ravel().tolist()))),file=self.savefile)
			self.motionTrigger=1 #run in start state
			#change colours fade in (need to determine targets)
			#fade in eg display objects
			QTimer.singleShot(self.lTrial*1000,self.changeState) #length of run
		elif self.state =="running":
			self.state = "response"
			self.sledClient.sendCommand("Sinusoid Stop") 
			print("]}",file=self.savefile)
			self.motionTrigger=0
			self.resColor(relative=0)
			self.parent().downAction.setEnabled(True)
			self.parent().upAction.setEnabled(True)
			self.parent().confirmAction.setEnabled(True)
			self.parent().newAction.setEnabled(True)
			#move sled 
		elif self.state == "response":
			self.state='home'
			self.initializeObjects()
			self.parent().downAction.setEnabled(False)
			self.parent().upAction.setEnabled(False)
			self.parent().confirmAction.setEnabled(False)
			self.parent().newAction.setEnabled(False)
			self.changeState()
		else:
			logging.warning("state unknown: {}".format(self.state))
	
	def addData(self, data):
		self.conditions.trial['pCorrect']= data  #str(self.pCorrect) try getting rid of data key
		self.conditions.trial['subject'] = self.subject # not very useful to store for each trial, but it has to go somewere
		self.responses[self.selected.astype(int)]=1
		self.responses=self.responses.astype(int).tolist()
		self.conditions.trial['response']=self.responses
		self.conditions.trial['trajectFile']=self.filename
		logging.info("received while waiting: {}".format(data))
		
		if self.conditions.iTrial < self.conditions.nTrial-1:
			if self.conditions.nextTrial(data = data):
				self.parent().startStop()
		else:
			# last data
			self.conditions.addData(data)
			self.requestSleep = True
		self.changeState()
		#else:
			#	logging.info("ignoring input: {}".format(data))
	
	views = ('ALL',)
	def toggleStereo(self, on):
		if on or len(self.views)==1:
			fmt = self.format()
			fmt.setStereo(True)
			self.setFormat(fmt)
			self.views = ('LEFT', 'RIGHT')
			self.parent().leftAction.setEnabled(True)
			self.parent().rightAction.setEnabled(True)
			if self.format().stereo():
				logging.info("stereo enabled, os type")
			else:
				logging.info("stereo enabled, side-by-side")
		else:
			fmt = self.format()
			fmt.setStereo(False) # does not turn off my glasses
			self.setFormat(fmt)
			self.views = ('ALL',)
			self.parent().leftAction.setEnabled(False)
			self.parent().rightAction.setEnabled(False)
			logging.info("stereo disabled")
		self.update()


	stereoIntensityLevel = 0 # integer -9 -- 9
	def stereoIntensity(self, level=None, relative=None):
		"""change the relative intensity of the left eye and right eye image"""
		if(level!=None):
			self.stereoIntensityLevel = level
		elif abs(self.stereoIntensityLevel + relative) < 10:
			self.stereoIntensityLevel += relative
		self.parent().statusBar().showMessage("Stereo intensity: {}".format(self.stereoIntensityLevel))
		self.update()
	
	def resColor(self, relative=None): #response ball color function
		self.currentTarget = (self.currentTarget + relative)%self.nBalls
		self.resBallColor=np.ones((self.nBalls,3), 'f') #needs to be redefined each ball change move it
		self.resBallColor[self.currentTarget,:]= [1,0,0] #set to red 
		self.update()

	def resBall(self):
		#if 
		#self.ballSelected < self.nTargets
		self.nCorrect=0
		self.selected[self.ballSelected]= self.currentTarget #need to store required number of responses
		self.ballSelected=(self.ballSelected+1)%self.nTargets
		self.pCorrect = np.mean(np.sort(self.selected) == np.sort(self.targets)).astype(np.float16)
		

		self.update
		#else :
			#self.state='sleep'
			#self.changeState()
			#self.initializeObjects()
			
			#print(self.ballSelected)
			#self.addData()
			#self.conditions.nextTrial()
			#print(self.conditions.iTrial)

	def viewerMove(self, x, y=None):
		""" Move the viewer's position """
		#print("viewermove: ({}, {})".format(x, y))
		self.pViewer[0] = x
		self.pViewer[1] = 0
		if y != None:
			self.pViewer[1] = y
		self.update()
	
	
	def mouseMoveEvent(self, event):
		""" 
		React to a moving mouse right button down in the same way we 
		would react to a moving target. 
		"""
		if event.buttons() & Qt.RightButton:
			self.viewerMove(
				self.dScreen[0]*(event.posF().x()/self.size().width()-.5), 
				self.dScreen[1]*(.5-event.posF().y()/self.size().height()) # mouse y-axis is inverted
				)

	def connectSledServer(self, server=None):
		logging.debug("requested sled server: " + str(server))
		self.sledClientSimulator = sledclientsimulator.SledClientSimulator() # for visual only mode
		if not server:
			self.sledClient = sledclientsimulator.SledClientSimulator()
		else:
			self.sledClient = sledclient.SledClient() # derived from FPClient
			self.sledClient.connect(server)
			self.sledClient.startStream()
			time.sleep(2)
		self.h = 0.0
		self.sledClient.goto(self.h) # homing sled at -reference
		self.sledClientSimulator.warpto(self.h) # homing sled at -reference
	
	def openShutter(self, left=False, right=False):
		"""open shutter glasses"""
		try:
			self.shutter.setLeds([left, right, False, False, False, False, False, False])
		except:
			pass


	def connectPositionServer(self, server=None):
		""" Connect to a First Principles server which returns the viewer position in the first marker position.
		Make sure this function is called after connectSledServer so that the fall back option is present. """
		logging.debug("requested position server: " + str(server))
		if not server:
			self.positionClient = self.sledClient
		elif server=="mouse":
			return
		else:
			self.positionClient = fpclient.FpClient()  # make a new NDI First Principles client
			self.positionClient.startStream()          # start the synchronization stream. 
			time.sleep(2)

	def initializeObjects(self):

	#velocity is sampled from a norm sphere and multipled to create equal speed for each object
		# see sampling_test.py for simulation of the sampling.
		# need to make sure we recall this at beginning of new trial
		self.sBalls=self.conditions.trial['sBalls']
		self.nBalls=self.conditions.trial['nBalls'] #required parameters go here.
		self.nTargets=self.conditions.trial['nTargets']
		self.lTrial=self.conditions.trial['lTrial']
		self.selected=np.zeros(self.conditions.trial['nTargets']).astype(np.float32)
		self.ballSelected=0
		self.nCorrect=0
		self.pCorrect=float('nan')
		self.responses=np.zeros(self.conditions.trial['nBalls']).astype(np.float32)

		Angles           = np.random.uniform(0, 1, (self.nBalls, 2)).astype(np.float32) 
		Theta            = 2*math.pi*Angles[:,0]
		Phi              = np.arccos(2*Angles[:,1]-1)
		self.motionTrigger = 0 #predefined
		if self.moveType == "ConstantVelocity":
			self.vBalls      = np.zeros((self.nBalls,3), dtype="float32")
			self.vBalls[:,0] =(np.cos(Theta)*np.sin(Phi))*self.sBalls  # m/s x
			self.vBalls[:,1] =(np.sin(Theta)*np.sin(Phi))*self.sBalls # m/s y 
			self.vBalls[:,2] =(np.cos(Phi)*self.sBalls)               # m/s z

		elif self.moveType == "virtualSpring":
			self.pBalls      = np.zeros((self.nBalls,3), dtype="float32")
			self.vBalls      = np.zeros((self.nBalls,3), dtype="float32")



		distance=np.zeros((self.nBalls*self.nBalls))
		distance[0]=1 
		while (sum(distance)>0):	# repeat until no balls overlap
			distance=np.zeros((self.nBalls*self.nBalls))
			self.pBalls=np.zeros((self.nBalls,3), dtype="float32")# m
			self.pBalls[:,0] = np.random.uniform(self.wall[0][0],self.wall[0][1], (self.nBalls)).astype(np.float32) #initialize balls to be between walls
			self.pBalls[:,1] = np.random.uniform(self.wall[1][0],self.wall[1][1], (self.nBalls)).astype(np.float32)
			self.pBalls[:,2] = np.random.uniform(self.wall[2][0],self.wall[2][1], (self.nBalls)).astype(np.float32)
			for i in range(0,self.nBalls-1):
				for j in range(i+1,self.nBalls):
					if np.sqrt(sum(np.square(self.pBalls[i,:] -self.pBalls[j,:]))) < self.rBalls*2: #check euclidean distance
						distance[i]=1
		#if self.moveType=="virtualSpring":
		self.targets=np.random.permutation(self.nBalls) #create randon permutation of balls
		self.targets=self.targets[0:self.nTargets] #define targets
		self.pBallStart=self.pBalls[self.targets,:] #randomise and find targets
		self.currentTarget=0 #start response from first balls
		self.ballColor=np.ones((self.nBalls,3), 'f') #everything grey
		self.ballColor[self.targets,:]=numpy.matlib.repmat([1,0,0],self.nTargets,1) #num targets cannot be less than num of balls
		self.resBallColor=np.ones((self.nBalls,3), 'f') #initiale response balls color
		# set uniform variables and set up VBO's for the attribute values
		# reference triangles, do not move in model coordinates
		# position of the center
		
		p, t, n, pTex = objects.sphere(1.0)

		# each vertex has:
		# 3 floats for position (x, y, z)
 		self.ballVertices = vbo.VBO(p, target=GL_ARRAY_BUFFER, usage=GL_STATIC_DRAW)
		self.ballIndices = vbo.VBO(t, target=GL_ELEMENT_ARRAY_BUFFER)
		
		# fixation cross
		xFixation = self.pViewer[0]

		p = np.hstack((
			np.array((xFixation-.1, 0, 0, 
			 xFixation+.1, 0, 0, 
			 xFixation, .1, 0), dtype='float32'), 
			np.array((0,0,1, 0,0,1, 0,0,1), dtype='float32')
		))

		# send the whole array to the video card
		self.fixationVertices = vbo.VBO(p, usage='GL_STATIC_DRAW')


	def initializeGL(self):
		glEnable(GL_DEPTH_TEST)          # painters algorithm without this
		glEnable(GL_MULTISAMPLE)         # anti aliasing
		glClearColor(0.0, 0.0, 0.0, 1.0) # blac k background
		
		# set up the shaders
		self.program = shader.initializeShaders(shader.vs, shader.fs)
		# constant uniforms
		glUniform1f(glGetUniformLocation(self.program, "rBalls"), self.rBalls)
		# dynamic uniforms
		self.MVPLocation = glGetUniformLocation(self.program, "MVP")
		self.nFrameLocation = glGetUniformLocation(self.program, "nFrame")
		self.fadeFactorLocation = glGetUniformLocation(self.program, "fadeFactor")
		self.colorLocation = glGetUniformLocation(self.program, "color")
		self.offsetLocation = glGetUniformLocation(self.program, "offset")
		# attributes
		self.positionLocation = glGetAttribLocation(self.program, 'position')
		#self.normalLocation = glGetAttribLocation(self.program, 'normal')
		
		glUniform3f(self.colorLocation, 1,0,1)
		glUniform1f(self.fadeFactorLocation, self.fadeFactor)
		
		self.initializeObjects()

	def resizeGL(self, width, height):
		logging.info("resize: {}, {}".format(width, height))
		self.width = width
		self.height = height
		
	def move(self):
		if self.moveType=="ConstantVelocity":
		#acceleration and time
			t = time.time()
			dt = t - self.tOld
			self.tOld = t
			dt = min(0.100, dt) # rather violate physics than make a huge timestep, needed after pause
			if self.motionTrigger==0: #don't move balls
				self.pBalls = self.pBalls


			elif self.motionTrigger==1: #move balls
				print("[{:.6f},{:s}],".format(time.time()-self.startime, ",".join(map(str,self.pBalls.ravel().tolist()))),file=self.savefile)
				# ball displacement (semi implicit Euler)
				self.pBalls = self.pBalls + self.vBalls * dt
				if self.wallCollide:
					for i in range(self.nBalls):
						for dim in range(3): # todo: vectorize
							if self.pBalls[i][dim] < self.wall[dim][0]:
								self.pBalls[i][dim] =  2*self.wall[dim][0] - self.pBalls[i][dim]
								self.vBalls[i][dim] =  -self.vBalls[i][dim]
							elif self.pBalls[i][dim] > self.wall[dim][1]:
								self.pBalls[i][dim] =  2*self.wall[dim][1] - self.pBalls[i][dim]
								self.vBalls[i][dim] =  -self.vBalls[i][dim]
				
		elif self.moveType=="virtualSpring":

			L= 0#dampening/ inertia
			K= 0.05#spring constant
			Sig=0.03
			t = time.time()
			#dt = t - self.tOld
			dt=0.1
			self.tOld = t
			dt = min(0.100, dt) # rather violate physics than make a huge timestep, needed after pause
			if self.motionTrigger==0: #don't move balls
				self.pBalls = self.pBalls


			elif self.motionTrigger==1: #move balls
				print("[{:.6f},{:s}],".format(time.time()-self.startime, ",".join(map(str,self.pBalls.ravel().tolist()))),file=self.savefile)
				# ball displacement (semi implicit Euler)
				self.vBalls = L*self.vBalls + K*(0-self.pBalls)*dt + np.sqrt(dt)*np.random.normal(0,Sig,(self.nBalls,3)).astype(np.float32)
				self.pBalls = self.pBalls + self.vBalls


	nFramePerSecond = 0 # number of frame in this Gregorian second
	nFrame = 0 # total number of frames
	nSeconds = int(time.time())
	def paintGL(self):
		"""
		if int(time.time()) > self.nSeconds:
			self.nSeconds = int(time.time())
			print("fps: {}".format(self.nFramePerSecond), end='\r')
			sys.stdout.flush()
			self.nFramePerSecond = 0
		self.nFramePerSecond += 1
		"""
		
		if hasattr(self, "positionClient"): # only false if mouse is used
			mode = "visual"
			if mode=='visual':
				pp = self.sledClientSimulator.getPosition()
			elif mode=='combined' or mode=='vestibular':
				pp = self.positionClient.getPosition(self.positionClient.time()+5./60) #store this variable, as it is sled position
			else:
				logging.error("mode not recognized: "+mode)
				
			p = np.array(pp).ravel().tolist()       # python has too many types
			self.viewerMove(p[0], p[1])         # use x- and y-coordinate of first marker
				
		## set uniform variables
		if self.nFrameLocation != -1:
			glUniform1i(self.nFrameLocation, self.nFrame)

		glDrawBuffer(GL_BACK_LEFT)
		glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
		for eye in self.views:
			if eye == 'LEFT':
				xEye = -self.dEyes/2
				intensityLevel = (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1)[self.stereoIntensityLevel-10]
				glUniform3f(self.colorLocation, 0.0, 0.0, 1.0)
				if not self.format().stereo():
					# self implemented side-by-side stereo, for instance in sled lab
					glViewport(0, 0, self.width/2, self.height)
			elif eye == 'RIGHT':
				xEye =  self.dEyes/2
				intensityLevel = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)[self.stereoIntensityLevel-10]
				glUniform3f(self.colorLocation, 1.0, 0.0, 0.0)
				if self.format().stereo():
					# os supported stereo, for instance nvidia 3d vision
					glDrawBuffer(GL_BACK_RIGHT)
					glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
				else:
					# self implemented side-by-side stereo, for instance in sled lab
					glViewport(self.width/2, 0, self.width/2, self.height)
			else:
				glViewport(0, 0, self.width, self.height)
				xEye =  0
				intensityLevel = 1.0
				
			# calculate MVP (VP really)
			z = self.pViewer[2]
			MVP = transforms.arjan(self.dScreen[0], self.dScreen[1], 
				z-self.zNear, z-self.zFocal, z-self.zFar,
				self.pViewer[0]+xEye, self.pViewer[1])
			glUniformMatrix4fv(self.MVPLocation, 1, GL_FALSE, MVP)

			# enable vertex attributes used in both balls and fixation cross
			glEnableVertexAttribArray(self.positionLocation)
			#glEnableVertexAttribArray(self.normalLocation)
			
			# draw balls as elements (with indices)
			self.ballVertices.bind()
			self.ballIndices.bind()
			glVertexAttribPointer(self.positionLocation, 3, GL_FLOAT, False, 3*4, self.ballVertices)
			#glVertexAttribPointer(self.normalLocation, 3, GL_FLOAT, True, 3*4, self.ballVertices)
				
			for i in range(self.nBalls): #change ball color depending on state, maybe put in function later
				if self.state == "wait" or self.state=='home' or self.state=='sleep':
					glUniform3fv(self.colorLocation, 1, intensityLevel*np.array([0,0,0],"f")) #arjan no f at end, np array is colour
				elif self.state == "start":
					glUniform3fv(self.colorLocation, 1, self.ballColor[i])
				elif self.state == "running":
					glUniform3fv(self.colorLocation, 1, intensityLevel*np.array([1,1,1],"f"))
				elif self.state == "response":
					glUniform3fv(self.colorLocation,1, self.resBallColor[i])
				glUniform3fv(self.offsetLocation, 1, self.pBalls[i])
				glDrawElements(GL_TRIANGLES, self.ballIndices.data.size, GL_UNSIGNED_INT, None)
			self.ballVertices.unbind()
			self.ballIndices.unbind()

			# draw fixation cross as arrays (without indices)
			self.fixationVertices.bind() # get data from vbo with vertices
			glVertexAttribPointer(self.positionLocation, 3, GL_FLOAT, False, 6*4, self.fixationVertices)
			#glVertexAttribPointer(self.normalLocation, 3, GL_FLOAT, False, 6*4, self.fixationVertices+3)
			glUniform3fv(self.colorLocation, 1, intensityLevel*np.array([1,1,1],"f"))
			# glUniform1f(self.moveFactorLocation, 1.0) #todo: put in MVP
			#xEye =  0
			glDrawArrays(GL_TRIANGLES, 0, 1)
			self.fixationVertices.unbind()
			

		## schedule next redraw

		#if self.running:
		self.nFrame += 1
		self.move()
		self.update()


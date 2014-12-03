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
import fpclient, sledclient, sledclientsimulator, transforms, objects, shader

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
	
	# balls
	rBalls      = .1                        # m
	nBalls      = 4
	ballCollide = False
	wall        = ((-dScreen[0]/2+rBalls, dScreen[0]/2-rBalls), (-dScreen[1]/2+rBalls, dScreen[1]/2-rBalls), (zFar+rBalls, zNear-rBalls))
	wallCollide = True
	
	def __init__(self, parent):
		#QGLWidget.__init__(self, parent)
		super(Field, self).__init__(parent)
		self.setMinimumSize(1400, 525)
		
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
			
		self.time = QTime()
		self.vBalls       = np.zeros((self.nBalls, 3), dtype="float32") # m/s
		self.vBalls[1]    = [-0.05, -0.01, 0.0]
		self.vBalls       = np.random.uniform(-.1, .1, (self.nBalls, 3)).astype(np.float32) # m/s
		self.pBalls       = np.zeros((self.nBalls, 3), dtype="float32") # m
			
		self.fadeFactor = 1.0         # no fade, fully exposed
		self.running = False

	def __del__(self):
		self.quit()

	def quit(self):
		if hasattr(self, "sledClient") and hasattr(self.sledClient, "stopStream"):
			print("closing sled client") # logger may not exist anymore
			self.sledClient.stopStream()
		if hasattr(self, "positionClient") and hasattr(self.positionClient, "stopStream"):
			print("closing FP client") # logger may not exist anymore
			self.positionClient.stopStream()
			
	
	views = ('ALL',)
	def toggleStereo(self, on, sim=False):
		if on or len(self.views)==1:
			if sim:
				self.views = ('LEFTSIM', 'RIGHTSIM')
			else:
				self.views = ('LEFT', 'RIGHT')
			self.parent().leftAction.setEnabled(True)
			self.parent().rightAction.setEnabled(True)
		else:
			self.views = ('ALL',)
			self.parent().leftAction.setEnabled(False)
			self.parent().rightAction.setEnabled(False)
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
		# set uniform variables and set up VBO's for the attribute values
		# reference triangles, do not move in model coordinates
		# position of the center
		
		nPast = 0
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
		logging.info("Resize: {}, {}".format(width, height))
		self.width = width
		self.height = height
		
	def move(self):
		#acceleration and time
		dt = 1e-3 * min(100, self.time.elapsed()); # rather violate physics than make a huge timestep
		
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
				
		
	nFramePerSecond = 0 # number of frame in this Gregorian second
	nFrame = 0 # total number of frames
	nSeconds = int(time.time())
	def paintGL(self):
		if int(time.time()) > self.nSeconds:
			self.nSeconds = int(time.time())
			#print("fps: {}, extrapolation time: {:.3f} s".format(self.nFramePerSecond, self.extrapolationTime), end='\r')
			#print("fps: {}".format(self.nFramePerSecond), end='\r')
			sys.stdout.flush()
			self.nFramePerSecond = 0
		self.nFramePerSecond += 1
		
		
		if hasattr(self, "positionClient"): # only false if mouse is used
			mode = "visual"
			if mode=='visual':
				pp = self.sledClientSimulator.getPosition()
			elif mode=='combined' or mode=='vestibular':
				pp = self.positionClient.getPosition(self.positionClient.time()+5./60)
			else:
				logging.error("mode not recognized: "+mode)
				
			p = np.array(pp).ravel().tolist()       # python has too many types
			self.viewerMove(p[0], p[1])         # use x- and y-coordinate of first marker
				
		## set uniform variables
		if self.nFrameLocation != -1:
			glUniform1i(self.nFrameLocation, self.nFrame)

		glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
		for eye in self.views:
			## setup view, change the next 5 lines for different type of stereo view
			if eye == 'LEFT':
				glViewport(0, 0, self.width/2, self.height)
				xEye = -self.dEyes/2
				intensityLevel = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1][self.stereoIntensityLevel-10]
			elif eye == 'LEFTSIM':
				glViewport(0, 0, self.width, self.height)
				xEye =  -self.dEyes/2
				intensityLevel = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1][self.stereoIntensityLevel-10]
			elif eye == 'RIGHT':
				glViewport(self.width/2, 0, self.width/2, self.height)
				xEye =  self.dEyes/2
				intensityLevel = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0][self.stereoIntensityLevel-10]
			elif eye == 'RIGHTSIM':
				glViewport(0, 0, self.width, self.height)
				xEye =  self.dEyes/2
				intensityLevel = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0][self.stereoIntensityLevel-10]
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
			glUniform3f(self.colorLocation, 1.0, 1.0, 0.0)
			for i in range(self.nBalls):
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
		if self.running:
			self.nFrame += 1
			self.move()
			self.update()


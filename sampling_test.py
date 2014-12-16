'''
Script to simulate possible sampling methods for object velocity in MOT tasks. 
Three sampling methods are simulated; X,Y,Z directly, sampling spherical coordinates,
and a corrected spherical coordinate method.
'''

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
import math

sBalls = 5 #speed of balls
n=10000    # number of samples

#sample from x,y,z directly
#sampling is not uniform, higher density at corners
XYZ= np.random.uniform(-1,1,(3,n)).astype(np.float32)  #sample X,Y,Z
Euc_distance=np.sqrt(np.square(XYZ).sum(axis=0)[np.newaxis,:]) 
XYZ_norm=XYZ/Euc_distance #normalise euclidean distance to 1
XYZ_scaled=XYZ_norm*sBalls #scale to desired speed

# sample spherical coordinates and convert to X,Y,Z
# sample spherical coordinates phi and theta
# sampling normally leads to higher density at the poles of the sphere
Phi   = np.random.uniform(-math.pi,math.pi,(1,n)).astype(np.float32) 
Theta = np.random.uniform(-math.pi,math.pi,(1,n)).astype(np.float32)
VBalls= np.zeros((3,n), dtype="float32")
VBalls[0,:] = (np.cos(Theta)*np.sin(Phi))*sBalls #convert to x,y,z
VBalls[1,:] = (np.sin(Theta)*np.sin(Phi))*sBalls
VBalls[2,:] = (np.cos(Phi)*sBalls)

#sample corrected spherical coordinates 
Angles  = np.random.uniform(0, 1, (n, 2)).astype(np.float32) 
Theta   = 2*math.pi*Angles[:,0] #correct point sampling from sphere
Phi     = np.arccos(2*Angles[:,1]-1)
VBalls_uni= np.zeros((3,n), dtype="float32")
VBalls_uni[0,:]=(np.cos(Theta)*np.sin(Phi))*sBalls
VBalls_uni[1,:]=(np.sin(Theta)*np.sin(Phi))*sBalls
VBalls_uni[2,:]=(np.cos(Phi)*sBalls)

##plotting
fig=plt.figure()
ax = fig.add_subplot(111, projection='3d')
ax.scatter(XYZ_scaled[0,:],XYZ_scaled[1,:],XYZ_scaled[2,:],s=2,marker='o')
ax.set_title('Sampling from X,Y,Z')
ax.set_xlabel('X Label')
ax.set_ylabel('Y Label')
ax.set_zlabel('Z Label')

fig2=plt.figure()
ax2 = fig2.add_subplot(111, projection='3d')
ax2.scatter(VBalls[0,:],VBalls[1,:],VBalls[2,:],s=2,marker='o')
ax2.set_title('Sampling from Spherical Coordinates')
ax2.set_xlabel('X Label')
ax2.set_ylabel('Y Label')
ax2.set_zlabel('Z Label')

fig3 = plt.figure()
ax3 = fig3.add_subplot(111, projection='3d')
ax3.scatter(VBalls_uni[0,:],VBalls_uni[1,:],VBalls_uni[2,:],s=2,marker='o')
ax3.set_title('Sampling uniformly from sphere')
ax3.set_xlabel('X Label')
ax3.set_ylabel('Y Label')
ax3.set_zlabel('Z Label')


plt.show()







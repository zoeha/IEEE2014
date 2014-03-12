#!/usr/bin/env python
import blockSpotter  #This does all of the block locating
import numpy as np
import string
import rospy
import cv2
import tf
import os
import sys
import traceback
from sensor_msgs.msg import Image
from cv_bridge import CvBridge, CvBridgeError
from ieee2014_vision.srv import *
from geometry_msgs.msg import Pose2D, PoseStamped
from dynamixel_msgs.msg import JointState
from ieee2014_vision.msg import BlockPositions
from std_msgs.msg import Float64, Bool
try:
	from IEEE2014Functions import image_publisher as impub
except:
	traceback.print_exc(file=sys.stdout)
	print "Image Publisher Import Failed"

## Sub :: sim_pose | pose ; camera pan/tilt ;
## Pub :: blockPositions ;
#TODO:
# - Enable blockSpotter to detect and use an attached camera
# - Enable blockSpotter to display an image if we're debugging

##CHECK:
# - I think I got the coordinate transform equation wrong - Replace with tf.transformations.*
# - Assumed positive right radians for pan
class blockHandler:
	def __init__(self):		
		##Immutable parameters
		rospy.init_node('block_publisher')
		self.course_length = (97 - 3/4 * 2) * 0.0254 #Courtesy of Lord Voight
		self.course_width = (49 - 3/4 * 2) * 0.0254
		self.cameraFwd = 5.25 * 0.0254 #Cam v2 (not precise)
		#self.cameraFwd = 5.25 I think this is the most accurate?
		self.cameraLeft = 0
		self.start_pos = (-self.course_length/2 + (6*0.0254), -self.course_width/2 + ((5+5.25+0.75)*0.0254))	
		#Variable initialized parameters
		self.pan = 0
		self.image = None
		self.bridge = CvBridge()
		##Begin publisher and subscribers
		
		self.sim = rospy.get_param('/block_publisher/sim', "N")
		self.publish_images = rospy.get_param('/block_publisher/debug', "N")
		self.enable = True #Default state
		self.enable_service = rospy.Service('Detect_Blocks',Detect_Blocks, self.detect_enable)

		self.image_sub = rospy.Subscriber('/Camera', Image, self.start_detection)
		
		
		
		if(self.publish_images == 'Y'):
			self.image_pub = impub.image_sender("Block_Vision")
			
			
		self.pub = rospy.Publisher('block_positions', BlockPositions)
		
		#Assume tilt is zerod when using blockSpotter.
		#figure out how to read servo status correctly
		self.pan_sub = rospy.Subscriber('/pan_controller/state', JointState, self.start_detection)
		self.pan_pub = rospy.Publisher('/pan_controller/command', Float64)
		self.pan_pub.publish(Float64(0.3))

			
	def __enter__(self):
		#print("Entering")
		#self.cam = cv2.VideoCapture(-1)
		
		#targetResolution = (640,360)
		
		#self.cam.set(3,targetResolution[0]) #Width
		#self.cam.set(4,targetResolution[1]) #Height
		print "Enabling Block Detection"
		return self
	
	def __exit__(self, *args):
		#print("Exiting")
		#self.cam.release()
		print "Disabling Block Detection"

	def detect_enable(self,data):
		self.enable = data.enable
		return Detect_BlocksResponse()
	def setPan(self,data):
		self.pan = data.current_pos
		return
		

	def start_detection(self, data):
		if self.enable == False:
			print "Vision Not Active"
			rospy.sleep(0.5)
			return
		print "Vision Active"
		
		image = None
		try:
			image = self.bridge.imgmsg_to_cv(data,"bgr8").getNumpy()
			print type(image)
			
		except:
			print "No image read"
			
		if(image != None):
			
			relPositions,imxy = blockSpotter.spotBlocks(image)
			#if self.publish_images == 'Y':
				#for k in range(len(imxy)):
				#	xy = imxy[k]
				#	cv2.circle(image, xy,5,(50,220,50),thickness=-1)
				#	pos = relPositions[k]
				#	cv2.putText(image, str(pos[0])+ ', ' +str(pos[1]), xy, cv2.FONT_HERSHEY_PLAIN, 0.8, (0,0,255), thickness=1)
				
				#self.image_pub.send_message(image)
		else:
			if len(sys.argv) > 1:
				if not '_' in sys.argv[1]:
					image_name = sys.argv[1]
				else:
					image_name = 'frame0000'	
			else:
				image_name = 'frame0000'
			path =  os.path.dirname(os.path.abspath(__file__))
			image = cv2.imread(path + '/Debug/' + image_name + '.jpg')
			relPositions, imxy = blockSpotter.spotBlocks(image)
			

			
				
		#RelPos <-> (Forward Displacement, Lateral Displacement Left Positive)
		if relPositions == None:

			rospy.loginfo("||| block_publisher: No Blocks Detected") #-dbg
			rospy.sleep(0.1) #-dbg
			return

		#robotPos = (data.pose.position.x,data.pose.position.y)
		robotPos = self.start_pos
		#quaternion = (
		#	data.pose.orientation.x,
		#	data.pose.orientation.y,
		#	data.pose.orientation.z,
		#	data.pose.orientation.w)

		#rpy = tf.transformations.euler_from_quaternion(quaternion) #Roll, Pitch, Yaw: Radians
		rpy = (0,0,0)
		#Assuming robotpos to be 0!
		
		yaw = rpy[2] + self.pan #CHECK: Assuming positive left for camera PAN
		#cameraPos = (robotPos[0] + (self.cameraFwd*np.cos(yaw)), robotPos[1] + (self.cameraFwd*np.sin(yaw)))
	
		#blockPos = np.add(robotPos,relPositions)

		msg = BlockPositions()
		msg.blocks = []
		doxy = []
		doabspos = []
		#rospy.loginfo(transformCoordinates((0,0),(1,1),0))

		for pos, xy in zip(relPositions, imxy):
		
			phi = np.arctan(pos[1]/(pos[0]+self.cameraFwd))
			L = np.linalg.norm(((pos[0]+self.cameraFwd),pos[1]))
			xOffset = L*np.cos(phi+yaw)
			yOffset = L*np.sin(phi+yaw)
			#absolutePos = (cameraPos[0] + xOffset, cameraPos[1] + yOffset)
			absolutePos = (robotPos[0] + xOffset, robotPos[1] + yOffset)

			if ((absolutePos[0] < 0.62 + self.course_length/2) and (np.abs(absolutePos[1]) < self.course_width/2)):
				absPos = Pose2D()
				absPos.x = absolutePos[0]
				absPos.y = absolutePos[1]
				absPos.theta = 0
				msg.blocks.append(absPos)
				doxy.append(xy)
				doabspos.append(absolutePos)
		
		if self.publish_images == 'Y' and image != None:
			for k in range(len(doxy)):
				xy = imxy[k]
				cv2.circle(image, xy,5,(50,220,50),thickness=-1)
				pos = relPositions[k]
				cv2.putText(image, str(pos[0])+ ', ' +str(pos[1]), xy, cv2.FONT_HERSHEY_PLAIN, 0.8, (0,0,255), thickness=1)
				cv2.putText(image, str(doabspos[k][0])+ ', ' +str(doabspos[k][1]), (xy[0] + 10, xy[1] + 10), cv2.FONT_HERSHEY_PLAIN, 0.8, (0,150,240), thickness=1)
			self.image_pub.send_message(image)

		self.pub.publish(msg)
		#rospy.sleep(0.2) #Is this necessary? Will it reduce stress on odroid?
		


if __name__=='__main__':
	try:
		blockhandlerObj = blockHandler()
		rospy.spin()
		
		#return Detect_BlocksResponse()
	except rospy.ROSInterruptException:
		#rospy.loginfo('failed')
		pass

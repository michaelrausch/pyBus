#!/usr/bin/python

import os, sys, time, signal, json, logging
import pyBus_core as core

# This module will read a packet, match it against the json object 'DIRECTIVES' below. 
# The packet is checked by matching the source value in packet (i.e. where the packet came from) to a key in the object if possible
# Then matching the Destination if possible
# The joining the 'data' component of the packet and matching that if possible.
# The resulting value will be the name of a function to pass the packet to for processing of sorts.

#####################################
# GLOBALS
#####################################
# directives list - maps function to src:dest:data
# first level of directives is filtering the src, so put in the integer representation of the src
# second level is destination
# third level is data : function name
DIRECTIVES = {
  '80' : {
    'BF' : {
      'ALL' : 'd_custom_IKE' # Use ALL to send all data to a particular function
    }
  },
  '68' : {
    '18' : {
      '01'     : 'd_cdPollResponse',
      '380000' : 'd_cdSendStatus',
      '380100' : 'd_cdStopPlaying',
      '380300' : 'd_cdStartPlaying',
      '380A00' : 'd_cdNext',
      '380A01' : 'd_cdPrev',
      '380700' : 'd_cdScanForward',
      '380701' : 'd_cdScanBackard',
      '380400' : 'd_cdScanForward',
      '380401' : 'd_cdScanBackard',
      '380800' : 'd_cdRandom',
      '380801' : 'd_cdRandom'
    }
  }
}

WRITER = None

#####################################
# FUNCTIONS
#####################################
# Set the WRITER object (the iBus interface class) to an instance passed in from the CORE module
def init(writer):
  global WRITER
  WRITER = writer

# Manage the packet, meaning traverse the JSON 'DIRECTIVES' object and attempt to determine a suitable function to pass the packet to.
def manage(packet):
  src = packet['src']
  dst = packet['dst']
  dataString = ''.join(packet['dat'])
  methodName = None

  try:
    if (src not in DIRECTIVES.keys()):
      return False
    srcDir = DIRECTIVES[src]
    if (dst not in srcDir.keys()):
      return False
    dstDir = srcDir[dst]
    if (dataString not in dstDir.keys()) and ('ALL' not in dstDir.keys()):
      return False
    if ('ALL'  in dstDir.keys()):
      methodName = dstDir['ALL']
    else:
      methodName = dstDir[dataString]
    
  except Exception, e:
    core.printOut(e, 2)
    
  if methodName != None:
    methodToCall = globals()[methodName]
    logging.debug("Directive found for following packet:")
    core.displayPacket(packet)
    result = methodToCall(packet)
    return result

  else:
    logging.debug("Directive not found for following packet:")
    core.displayPacket(packet)
    return None

  globalManage(packet)
  
#####################################
# All directives should have a d_ prefix as we are searching GLOABBLY for function names.. so best have unique enough names

# This method is used to keep registering the device if the radio hasn't responded yet with a poll
def globalManage(packet):
  if not REGISTERED:
    WRITER.writeBusPacket('18', 'FF', ['02', '01'])

# This packet is used to parse all messages from the IKE (instrument control electronics), as it contains speed/RPM info. But the data for speed/rpm will vary, so it must be parsed via a method linked to 'ALL' data in the JSON DIRECTIVES
def d_custom_IKE(packet):
  packet_data = packet['dat']
  if packet_data[0] == '18':
    speed = int(packet_data[1], 16) * 2
    revs = int(packet_data[2], 16)
    customState = {'speed' : speed, 'revs' : revs}
    core.writeDataToSocket(customState) # This data is written to a file for the web-interface to display
    speedTrigger(speed) # This is a silly little thing for changing track based on speed ;)

def _displayTrackInfo():
  displayQue = []
  status = getInfo()
  displayQue.append(status['track']['artist'])
  displayQue.append(status['track']['title'])
  core.pB_display.setQue(displayQue)

# NEXT command is invoked from the Radio. 
def d_cdNext(packet):
  core.pB_audio.next()
  trackID = '%02X' % int(core.pB_audio.getTrackID()) # Track ID used to be sent to the radio, but track number can exceed 99 causing problems (data is converted to INT at the radio for displaying)
  WRITER.writeBusPacket('18', '68', ['39', '02', '09', '00', '3F', '00', '01', '01'])
  _displayTrackInfo()

def d_cdPrev(packet):
  core.pB_audio.previous()
  trackID = '%02X' % int(core.pB_audio.getTrackID())
  WRITER.writeBusPacket('18', '68', ['39', '02', '09', '00', '3F', '00', '01', '01'])
  _displayTrackInfo()

def d_cdScanForward(packet):
  WRITER.writeBusPacket('18', '68', ['39', '03', '09', '00', '3F', '00', '01', '01'])
  core.pB_audio.seek(2)

def d_cdScanBackard(packet):
  WRITER.writeBusPacket('18', '68', ['39', '04', '09', '00', '3F', '00', '01', '01'])
  core.pB_audio.seek(-2)

def d_cdStopPlaying(packet):
  core.pB_audio.pause()
  WRITER.writeBusPacket('18', '68', ['39', '00', '02', '00', '3F', '00', '01', '00'])
  core.setDisplay(False)

def d_cdStartPlaying(packet):
  core.pB_audio.play()
  trackID = '%02X' % int(core.pB_audio.getTrackID())
  WRITER.writeBusPacket('18', '68', ['39', '00', '09', '00', '3F', '00', '01', '01'])
  core.setDisplay(True)
  
def d_cdSendStatus(packet):
  trackID = '%02X' % int(core.pB_audio.getTrackID())
  WRITER.writeBusPacket('18', '68', ['39', '00', '09', '00', '3F', '00', '01', '01'])

def d_cdPollResponse(packet):
  core.REGISTERED = True
  WRITER.writeBusPacket('18', 'FF', ['02','00'])
  
def d_cdRandom(packet):
  packet_data = packet['dat']
  random = core.pB_audio.random(0, True)
  if random:
    core.pB_display.immediateText('Random: ON')
  else:
    core.pB_display.immediateText('Random: OFF')
   
def speedTrigger(speed):
  if (speed > 120):
    fastSong = "Dethklok/Dethklok - The Gears.mp3"
    try:
      if (core.pB_audio.getInfoByPath(fastSong)['id'] != core.pB_audio.getTrackID()):
        core.pB_audio.addSong(fastSong)
        core.pB_audio.playSong(fastSong)
        core.pB_display.immediateText('HOLY SHIT')
    except:
      logging.warning("Exception changing track")

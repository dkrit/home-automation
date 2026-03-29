from datetime import datetime, timedelta
import json
import os

date_format = '%Y-%m-%d %H:%M:%S'

# We will accumulate multiple data points into multiple buckets. 1 minute, 5 minutes, 30 minutes, 12 hours.
# Here we have a function that can tell us the start time of a bucket given any time value inside that bucket.
def bucketStart(bucketDescriptor: str, dt: datetime, offset=0):
  if offset < 0:
    return bucketStart(bucketDescriptor, bucketStart(bucketDescriptor, dt) - timedelta(seconds=1), offset+1)

  if bucketDescriptor == 'm1':
    if (offset > 0):
      return bucketStart(bucketDescriptor, dt + timedelta(minutes=1), offset-1)
    return datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
  if bucketDescriptor == 'm5':
    if (offset > 0):
      return bucketStart(bucketDescriptor, dt + timedelta(minutes=5), offset-1)
    return datetime(dt.year, dt.month, dt.day, dt.hour, int(dt.minute / 5) * 5, 0)
  if bucketDescriptor == 'm30':
    if (offset > 0):
      return bucketStart(bucketDescriptor, dt + timedelta(minutes=30), offset-1)
    return datetime(dt.year, dt.month, dt.day, dt.hour, int(dt.minute / 30) * 30, 0)
  if bucketDescriptor == 'h12':
    if (offset > 0):
      return bucketStart(bucketDescriptor, dt + timedelta(hours=12), offset-1)
    return datetime(dt.year, dt.month, dt.day, int(dt.hour / 12) * 12, 0, 0)
  return None

# The container will be used at storage and transport layer, to hold multiple buckets.
def bucketContainerStart(bucketDescriptor: str, dt: datetime):
  if bucketDescriptor == 'm1':
    return datetime(dt.year, dt.month, dt.day, dt.hour, 0, 0)
  if bucketDescriptor == 'm5':
    return datetime(dt.year, dt.month, dt.day, int(dt.hour / 4) * 4, 0, 0)
  if bucketDescriptor == 'm30':
    return datetime(dt.year, dt.month, dt.day, 0, 0, 0)
  if bucketDescriptor == 'h12':
    return datetime(dt.year, dt.month, 1, 0, 0, 0)
  return None

def containerFile(baseFile: str, bucketDescriptor: str, dt):
  return baseFile + '.' + bucketDescriptor + '.' + datetime.strftime(dt, "%Y-%m-%d.%H") + '.json'

def readKey(dict, key, default):
  return dict[key] if key in dict else default

def accumulatePropValue(bucketContainers: dict, bucketDescriptor: str, dt: datetime, prop: str, value):
  containerKey = datetime.strftime(bucketContainerStart(bucketDescriptor, dt), date_format)
  bucketKey = datetime.strftime(bucketStart(bucketDescriptor, dt), date_format)

  if not containerKey in bucketContainers:
    bucketContainers[containerKey] = {}
  if not bucketKey in bucketContainers[containerKey]:
    bucketContainers[containerKey][bucketKey] = {}

  bucketContainers[containerKey][bucketKey][prop + '_count'] = readKey(bucketContainers[containerKey][bucketKey], prop + '_count', 0) + 1
  bucketContainers[containerKey][bucketKey][prop] = value # the last value received will be the closing value for this prop in the bucket
  if (type(value) == float or type(value) == int):
    bucketContainers[containerKey][bucketKey][prop + '_sum'] = readKey(bucketContainers[containerKey][bucketKey], prop + '_sum', 0.0) + value
    bucketContainers[containerKey][bucketKey][prop + '_avg'] = readKey(bucketContainers[containerKey][bucketKey], prop + '_sum', 0.0) / bucketContainers[containerKey][bucketKey][prop + '_count']
    max = readKey(bucketContainers[containerKey][bucketKey], prop + '_max', -float('inf'))
    bucketContainers[containerKey][bucketKey][prop + '_max'] = value if value > max else max
    min = readKey(bucketContainers[containerKey][bucketKey], prop + '_min', float('inf'))
    bucketContainers[containerKey][bucketKey][prop + '_min'] = value if value < min else min

def readContainerFile(bucketContainers: dict, baseFile: str, bucketDescriptor: str, dt: datetime) -> dict:
  containerStart = bucketContainerStart(bucketDescriptor, dt)
  containerKey = datetime.strftime(containerStart, date_format)
  filename = containerFile(baseFile, bucketDescriptor, containerStart)
  if not os.path.isfile(filename):
    return {}
  f = open(filename)
  bucketContainers[containerKey] = json.load(f)
  f.close()  

def writeContainerFile(bucketContainers: dict, baseFile: str, bucketDescriptor: str, dt: datetime):
  containerStart = bucketContainerStart(bucketDescriptor, dt)
  containerKey = datetime.strftime(containerStart, date_format)
  filename = containerFile(baseFile, bucketDescriptor, containerStart)
  f = open(filename + '.tmp', 'w')
  json.dump(bucketContainers[containerKey], f)
  f.close()
  if os.path.isfile(filename):
    os.remove(filename)
  os.rename(filename + '.tmp', filename)

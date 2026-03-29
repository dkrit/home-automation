import os
import sys
import binascii
import axpert

os.system('service invertercollector stop')    
dev = axpert.connect()
print('Type a command here. type "exit" to exit')
for line in sys.stdin:
    if 'exit' == line.rstrip():
        break

    if 'info' == line.rstrip():
        info = axpert.readGeneralInfo(dev)
        print("General Info:")
        print(info)
        continue

    if 'output' == line.rstrip():
        info = axpert.readOutputMode(dev)
        print("Output Mode:")
        print(info)
        continue

    if 'mode' == line.rstrip():
        info = axpert.readMode(dev)
        print("Mode:")
        print(info)
        continue

    axpert.sendCommand(dev, line.rstrip())
    res = axpert.readData(dev)
    print("Response:")
    print(res)
    print("Binary:")
    print(binascii.hexlify(res.encode()))

axpert.disconnect(dev)
os.system('service invertercollector start')

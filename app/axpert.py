import os
import usb.core, usb.util, usb.control
import crc16
import time
import datetime

vendorId = 0x0665
productId = 0x5161
interface = 0

def connect():
    dev = usb.core.find(idVendor=vendorId, idProduct=productId)
    if dev.is_kernel_driver_active(interface):
        dev.detach_kernel_driver(interface)
    dev.set_interface_altsetting(0,0)
    return dev

def disconnect(dev):
    usb.util.dispose_resources(dev)
    dev.attach_kernel_driver(interface)
    time.sleep(1)
    os.system('usbreset 0665:5161')
    time.sleep(1)

def sendCommand(dev, cmd):
    cmd1 = cmd.encode('utf-8')
    if cmd == "POP02": crc1 = b'\xe2\x0b'
    else: crc1 = crc16.crc16xmodem(cmd1).to_bytes(2,'big')
    cmd1 = cmd1+crc1
    cmd1 = cmd1+b'\r'
    while len(cmd1)<16:
        cmd1 = cmd1+b'\0'

    tries=5
    i=0
    while i<tries:
        try:
            dev.ctrl_transfer(0x21, 0x9, 0x200, 0, cmd1[0:8])
            if (len(cmd) > 5):
                dev.ctrl_transfer(0x21, 0x9, 0x200, 0, cmd1[8:16])
            return
        except usb.core.USBError as e:
            pass
        i+=1

def readData(dev, tries=5):
    res=""
    i=0
    while '\r' not in res and i<tries:
        try:
            res+="".join([chr(i) for i in dev.read(0x81, 8, 1000) if i!=0x00])
        except usb.core.USBError as e:
            i+=1
            if e.errno == 110:
                pass
            else:
                raise
    return res

def readMode(dev):
    res=""
    i=0
    while ('(' not in res or '(NAK' in res) and i<5:
        sendCommand(dev, 'QMOD')
        res = readData(dev)
        i+=1
    val = res.split('(')[1][:1]
    if val == "L" or val == "B":
        return val
    else:
        return res

def readOutputMode(dev):
    res=""
    i=0
    while ('(' not in res or '(NAK' in res) and i<5:
        sendCommand(dev, 'QOPM')
        res = readData(dev)
        i+=1
    return res.split('(')[1][:2]

def readGeneralInfo(dev, tries=5):
    values=[]
    res=""
    i=0
    while len(values) < 20 and i<tries:
        sendCommand(dev, 'QPIGS')
        res = readData(dev)
        i+=1
        if '(' in res:
            values = res.split('(')[1].split(' ')

    return {
        'Time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'GridVoltage': float(values[0]),
        'GridFrequency': float(values[1]),
        'OutputVoltage': float(values[2]),
        'OutputFrequency': float(values[3]),
        'OutputApparentPower': float(values[4]),
        'OutputActivePower': float(values[5]),
        'OutputLoadPercent': float(values[6]),
        'BusVoltage': float(values[7]),
        'BatteryVoltage': float(values[8]),
        'BatteryChargingCurrent': float(values[9]),
        'BatteryCapacity': float(values[10]),
        'InverterHeatSinkTemperature': float(values[11]),
        'PV-InputCurrentForBattery': float(values[12]),
        'PV-InputVoltage': float(values[13]),
        'BatteryVoltageFromSCC': float(values[14]),
        'BatteryDischargeCurrent': float(values[15]),
        'DeviceStatus7': int(values[16][0:1]),
        'DeviceStatus6': int(values[16][1:2]),
        'DeviceStatus5': int(values[16][2:3]),
        'DeviceStatus4': int(values[16][3:4]),
        'DeviceStatus3': int(values[16][4:5]),
        'DeviceStatus2': int(values[16][5:6]),
        'DeviceStatus1': int(values[16][6:7]),
        'DeviceStatus0': int(values[16][7:8]),
        'PV-InputWatts': float(values[19])
    }

# https://github.com/JosefKrieglstein/AxpertControl/blob/master/axpert.py

#Axpert Commands and examples
#Q1		# Undocumented command: LocalInverterStatus (seconds from absorb), ParaExistInfo (seconds from end of Float), SccOkFlag, AllowSccOnFlag, ChargeAverageCurrent, SCC PWM Temperature, Inverter Temperature, Battery Temperature, Transformer Temperature, GPDAT, FanLockStatus, FanPWMDuty, FanPWM, SCCChargePowerWatts, ParaWarning, SYNFreq, InverterChargeStatus
#QPI            # Device protocol ID inquiry
#QID            # The device serial number inquiry
#QVFW           # Main CPU Firmware version inquiry
#QVFW2          # Another CPU Firmware version inquiry
#QFLAG          # Device flag status inquiry
#QPIGS          # Device general status parameters inquiry
                # GridVoltage, GridFrequency, OutputVoltage, OutputFrequency, OutputApparentPower, OutputActivePower, OutputLoadPercent,
                # BusVoltage, BatteryVoltage, BatteryChargingCurrent, BatteryCapacity, InverterHeatSinkTemperature,
                # PV-InputCurrentForBattery, PV-InputVoltage, BatteryVoltageFromSCC, BatteryDischargeCurrent, DeviceStatus, ??, ??, PV-InputWatts
#QMOD           # Device mode inquiry P: PowerOnMode, S: StandbyMode, L: LineMode, B: BatteryMode, F: FaultMode, H: PowerSavingMode
#QPIWS          # Device warning status inquiry: Reserved, InverterFault, BusOver, BusUnder, BusSoftFail, LineFail, OPVShort, InverterVoltageTooLow, InverterVoltageTooHIGH, OverTemperature, FanLocked, BatteryVoltageHigh, BatteryLowAlarm, Reserved, ButteryUnderShutdown, Reserved, OverLoad, EEPROMFault, InverterSoftFail, SelfTestFail, OPDCVoltageOver, BatOpen, CurrentSensorFail, BatteryShort, PowerLimit, PVVoltageHigh, MPPTOverloadFault, MPPTOverloadWarning, BatteryTooLowToCharge, Reserved, Reserved
#QDI            # The default setting value information
#QMCHGCR        # Enquiry selectable value about max charging current
#QMUCHGCR       # Enquiry selectable value about max utility charging current
#QBOOT          # Enquiry DSP has bootstrap or not
#QOPM           # Enquiry output mode
#QPIRI          # Device rating information inquiry - nefunguje
#QPGS0          # Parallel information inquiry
                # TheParallelNumber, SerialNumber, WorkMode, FaultCode, GridVoltage, GridFrequency, OutputVoltage, OutputFrequency, OutputAparentPower, OutputActivePower, LoadPercentage, BatteryVoltage, BatteryChargingCurrent, BatteryCapacity, PV-InputVoltage, TotalChargingCurrent, Total-AC-OutputApparentPower, Total-AC-OutputActivePower, Total-AC-OutputPercentage, InverterStatus, OutputMode, ChargerSourcePriority, MaxChargeCurrent, MaxChargerRange, Max-AC-ChargerCurrent, PV-InputCurrentForBattery, BatteryDischargeCurrent
#QBV		# Compensated Voltage, SoC
#PEXXX          # Setting some status enable
#PDXXX          # Setting some status disable
#PF             # Setting control parameter to default value
#FXX            # Setting device output rating frequency
#POP02          # set to SBU
#POP01          # set to Solar First
#POP00          # Set to UTILITY
#PBCVXX_X       # Set battery re-charge voltage
#PBDVXX_X       # Set battery re-discharge voltage
#PCP00          # Setting device charger priority: Utility First
#PCP01          # Setting device charger priority: Solar First
#PCP02          # Setting device charger priority: Solar and Utility
#PCP03          # Setting device charger priority: Solar Only
#PGRXX          # Setting device grid working range
#PBTXX          # Setting battery type
#PSDVXX_X       # Setting battery cut-off voltage
#PCVVXX_X       # Setting battery C.V. charging voltage
#PBFTXX_X       # Setting battery float charging voltage
#PPVOCKCX       # Setting PV OK condition
#PSPBX          # Setting solar power balance
#MCHGC0XX       # Setting max charging Current          M XX
#MUCHGC002      # Setting utility max charging current  0 02
#MUCHGC010      # Setting utility max charging current  0 10
#MUCHGC020      # Setting utility max charging current  0 20
#MUCHGC030      # Setting utility max charging current  0 30
#POPMMX         # Set output mode       M 0:single, 1: parrallel, 2: PH1, 3: PH2, 4: PH3


import datetime
import axpert

# Working with other inverter. Goal is to carry maximum day-time solar into night time.
batteryTargetByHour = {
    0: 39,
    1: 38,
    2: 37,
    3: 36,
    4: 35,
    5: 34,
    6: 33,
    7: 32,
    8: 31,
    9: 30,
    10: 40,
    11: 50,
    12: 60, 
    13: 70,
    14: 80, 
    15: 90,
    16: 100,
    17: 93,
    18: 78, # Carry loads during peak hours, to maximize remaining reserve on other inverter
    19: 70, # Carry loads during peak hours, to maximize remaining reserve on other inverter
    20: 62, # Carry loads during peak hours, to maximize remaining reserve on other inverter
    21: 54, # Carry loads during peak hours, to maximize remaining reserve on other inverter
    22: 46,
    23: 40
}

def updateInverter(dev, stats, statsArray60):
    statsArray20 = list(filter(lambda x: datetime.datetime.strptime(x['Time'], '%Y-%m-%d %H:%M:%S') + datetime.timedelta(minutes=20) > datetime.datetime.now(), statsArray60))
    
    soc20 = 0
    for stat in statsArray20:
        soc20 += float(stat['SOC'])
    soc20 = round(soc20 / len(statsArray20), 2)

    soc60 = 0
    for stat in statsArray60:
        soc60 += float(stat['SOC'])
    soc60 = round(soc60 / len(statsArray60), 2)

    lxpOutputPower20 = 0
    for stat in statsArray20:
        if 'LXP_AC_Output_Power' in stat:
            lxpOutputPower20 += float(stat['LXP_AC_Output_Power'])
    lxpOutputPower20 = round(lxpOutputPower20 / len(statsArray20), 2)

    lxpSoc20 = 0
    for stat in statsArray20:
        if 'LXP_Battery_SOC' in stat:
            lxpSoc20 += float(stat['LXP_Battery_SOC'])
    lxpSoc20 = round(lxpSoc20 / len(statsArray20), 2)

    pv20 = 0
    for stat in statsArray20:
        pv20 += float(stat['PV'])
    pv20 = round(pv20 / len(statsArray20), 2)

    lxpBatteryCharge20 = 0
    for stat in statsArray20:
        if 'LXP_Battery_Charge' in stat:
            lxpBatteryCharge20 += float(stat['LXP_Battery_Charge'])
    lxpBatteryCharge20 = round(lxpBatteryCharge20 / len(statsArray20), 2)

    hour = datetime.datetime.now().hour
    minute = datetime.datetime.now().minute

    minGridVolts = float(statsArray60[0]['Grid Volts']) if len(statsArray60) > 0 else float(0)
    maxGridVolts = minGridVolts
    for stat in statsArray60:
        minGridVolts = min(minGridVolts, float(stat['Grid Volts']))
        maxGridVolts = max(maxGridVolts, float(stat['Grid Volts']))

    trgt = batteryTargetByHour[hour]

    if (len(statsArray20) <= 0):
        return {
            'utility_charge_current': 0,
            'charger_voltage': 0,
            'update_messages': ["Skipping update as there is not enough data points since service startup."]
        }

    utilizeAxpertBattery = lxpOutputPower20 >= 3000 or (lxpBatteryCharge20 < -40 and soc20 >= 95) or lxpSoc20 < 8
    utilizeAxpertSolar = soc20 >= 90 and lxpBatteryCharge20 < -40
    chargeAt2AmpMaximum = (pv20 < 68 and soc60 > 15) or lxpBatteryCharge20 < -40
    chargeAt10AmpMinimum = pv20 > 68 and soc60 < 85
    chargeAt2AmpMinimum = pv20 > 68 and soc60 >= 85 and soc60 < 95

    utilityChargeCurrent = 0
    if utilizeAxpertBattery:
        utilityChargeCurrent = -1 # battery mode
    elif utilizeAxpertSolar:
        utilityChargeCurrent = 0 # charge only from solar, LXP supplies AXP's load.
    elif soc60 <= trgt-20 and not chargeAt2AmpMaximum:
        utilityChargeCurrent = 30
    elif soc60 <= trgt-15 and not chargeAt2AmpMaximum:
        utilityChargeCurrent = 20
    elif (soc60 <= trgt-10 and not chargeAt2AmpMaximum) or chargeAt10AmpMinimum:
        utilityChargeCurrent = 10
    elif soc60 <= trgt-5 or chargeAt2AmpMinimum:
        utilityChargeCurrent = 2
    elif soc60 <= trgt:
        utilityChargeCurrent = 0 # charge only from solar, LXP supplies AXP's load.
    else:
        utilityChargeCurrent = -1 # battery mode

    # Collect update messages
    update_messages = []

    if utilityChargeCurrent >= 0:
        axpert.sendCommand(dev, "POP00")
        update_messages.append(f"AXP OUTPUT PRIORITY: USB, POP00 Response: {axpert.readData(dev)}")
    else:
        axpert.sendCommand(dev, "POP02")
        update_messages.append(f"AXP OUTPUT PRIORITY: SBU, POP02 Response: {axpert.readData(dev)}")

    if utilityChargeCurrent <= 0:
        axpert.sendCommand(dev, 'PCP03')
        update_messages.append(f"AXP CHARGE PRIORITY: Solar Only, PCP03 Response: {axpert.readData(dev)}")
    else:
        axpert.sendCommand(dev, 'PCP02')
        update_messages.append(f"AXP CHARGE PRIORITY: Solar + Utility, PCP02 Response: {axpert.readData(dev)}")

    if utilityChargeCurrent > 0:
        cmd = 'MUCHGC0' + str(utilityChargeCurrent).rjust(2, "0")
        axpert.sendCommand(dev, cmd)
        update_messages.append(f"AXP UTILITY MAX CHARGE CURRENT: {utilityChargeCurrent}amp, {cmd} Response: {axpert.readData(dev)}")

    if soc60 > 100:
        axpert.sendCommand(dev, "PBFT13_6")
        res = axpert.readData(dev)
        axpert.sendCommand(dev, "PCVV13_6")
        update_messages.append(f"AXP CHARGING VOLTS: 13.6, PBFT13_6 Response: {res}, PCVV13_6 Response: {axpert.readData(dev)}")
        # axpert.sendCommand(dev, "MCHGC010")
        # update_messages.append(f"AXP MAX CHARGE CURRENT: 10amp, MCHGC010 Response: {axpert.readData(dev)}")
    elif soc60 > 98:
        axpert.sendCommand(dev, "PBFT13_8")
        res1 = axpert.readData(dev)
        axpert.sendCommand(dev, "PCVV13_8")
        res2 = axpert.readData(dev)
        axpert.sendCommand(dev, "PBFT13_8")
        update_messages.append(f"AXP CHARGING VOLTS: 13.8, PBFT13_8 Response1: {res1}, PCVV13_8 Response: {res2}, PBFT13_8 Response2: {axpert.readData(dev)}")
        # axpert.sendCommand(dev, "MCHGC010")
        # update_messages.append(f"AXP MAX CHARGE CURRENT: 10amp, MCHGC010 Response: {axpert.readData(dev)}")
    elif soc60 > 92:
        axpert.sendCommand(dev, "PBFT14_0")
        res1 = axpert.readData(dev)
        axpert.sendCommand(dev, "PCVV14_0")
        res2 = axpert.readData(dev)
        axpert.sendCommand(dev, "PBFT14_0")
        update_messages.append(f"AXP CHARGING VOLTS: 14.0, PBFT14_0 Response1: {res1}, PCVV14_0 Response: {res2}, PBFT14_0 Response2: {axpert.readData(dev)}")
        # axpert.sendCommand(dev, "MCHGC020")
        # update_messages.append(f"AXP MAX CHARGE CURRENT: 20amp, MCHGC020 Response: {axpert.readData(dev)}")
    # elif soc60 > 84:
    #     axpert.sendCommand(dev, "MCHGC030")
    #     update_messages.append(f"AXP MAX CHARGE CURRENT: 30amp, MCHGC030 Response: {axpert.readData(dev)}")
    else:
        axpert.sendCommand(dev, "PCVV14_2")
        res = axpert.readData(dev)
        axpert.sendCommand(dev, "PBFT14_2")
        update_messages.append(f"AXP CHARGING VOLTS: 14.2, PCVV14_2 Response: {res}, PBFT14_2 Response: {axpert.readData(dev)}")
        # axpert.sendCommand(dev, "MCHGC040")
        # update_messages.append(f"AXP MAX CHARGE CURRENT: 40amp, MCHGC040 Response: {axpert.readData(dev)}")
    
    # Return charging parameters for transfer switch detection
    return {
        'utility_charge_current': utilityChargeCurrent,
        'utilize_axpert_battery': utilizeAxpertBattery,
        'utilize_axpert_solar': utilizeAxpertSolar,
        'charger_voltage': get_charger_voltage(soc60),
        'update_messages': update_messages,
        'trgt': trgt
    }

def get_charger_voltage(soc60):
    """Get the charger voltage based on SOC (same logic as in updateInverter)"""
    if soc60 > 100:
        return 13.6
    elif soc60 > 98:
        return 13.8
    elif soc60 > 90:
        return 14.0
    else:
        return 14.2
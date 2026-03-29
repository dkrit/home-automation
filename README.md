# home-automation
A totally custom built system, to automate an off-grid system with 2 inverters (a 1.5k and a 5k) and a solar water heating system.

## Installation #1

```
200L Geyser, with 2000W element
Solar water heater
Geyserwala controller. (Initially, a less primitive geyserwise max controller.)
Install date: 27 October 2022
```

One-way valve was added, to block overnight convection currents causing thermal syphoning. This reduced overnight losses from ~22 degrees to ~7 degrees celcius!

Element is connected as a non-essential load of installation #3.

## Installation #2

```
1x Inverter:
UPS-INV-1.5KVA-MEX
AC output: 1.5 kva (~1.2 kw)
Axpert equivalent
Install date: 20 April 2023

2x Batteries:
LinkQnet BAT-LI-12200E-TG
LiFePo4 12.8v 200ah 
Connected in parallel, to make 400ah total at 12v
Install date: 20 April 2023 and 23 August 2023

1x Solar panel:
Canadian Solar 555w Mono
Install date: 28 Jan 2025
```

This installation supplies power to essential loads and/or small and continuous loads via separately installed circuits and dedicated wall plugs, around 200w average load 24/7, 700w peak.

AC input of this inverter is currently connected as a load of installation #3, via a dedicated breaker unaffected by the manual transfer switch.

It was installed mainly as a backup for load shedding. Solar was later added to reduce utility consumption.

## Installation #3

```
1x Inverter:
Luxpower SNA 5000

1x Battery:
Hubble AM5 5.12 kwh

6x Solar Panels:
595W  Jenko

Install date: 14 August 2025
```

Manual transfer switch: Most non-essential loads can be powered either from this inverter, or from utility. Certain large appliances (like the oven) remain powered only via utility.

Inverter and battery has a communication cable, and battery type is set to "Li-Ion" and battery brand to "2 - Pylontech" on the inverter.

The AC input of this inverter is not connected to grid power, making this type of installation a off-grid system as opposed to a grid-tied or grid-tied hybrid. Off-grid systems need not be registered with eskom or with a municipality. (OHSA laws have been complied with, as that is a different story.) A special factory type 3-point plug was added by the installer, as an option to connect to grid power in the future.

## Installation #4

Rasberry PI: Extends WIFI and connects to installations. Runs python code:

* Talks to the geyserwala via rest api.
* Talks to luxpower inverter via modbus protocol, using the wifi dongle.
* Talks to the 1.5kva (axpert type) inverter via attached USB cable.
* Collects data from all 3 installations, on a 10 second interval.
* Calculates an estimated state of charge for the LinkQnet batteries, based on voltage and amps. (Being vaguely accurate is better than not knowing at all.)
* Hosts a basic read-only web page, with various graphs. Basic ability to scroll or zoom.
* Sends control commands to all three devices.
* Turns the geyser on when there's surplus solar power available to the luxpower.
* Sets the target temperature for the geyser based on various factors like the position of the transfer switch (don't want to heat water using grid power unnecessarily), the time of day, the solar quality and the fullness of the luxpower's battery.
* When the geyser is on, monitor the luxpower load on a 10 second interval, to see if another 1000W load other than the geyser is active. Turns the geyser off when total load exceeds 3000W.
* Decides whether the 1.5kva inverter should supply its loads from luxpower (connected AC), or from own battery.
* Decides if the 1.5kva inverter should charge its battery from its AC input (luxpower), and what this charging current should be. Possible values for "utility charging current" are: 2A, 10A, 20A, 30A, 40A
* Adjust charging voltages of the 1.5kva inverter. Gradually lowers the charging voltage from 14.2 to 13.8 as the SOC estimate approaches 100%.
* Adjust the luxpower end-of-discharge SOC, based on time of day. During bad weather patterns, or due to higher than usual night-time consumption we don't want alarms going off in the middle of the night. Rather just temporarily disconnect supply to non-essential loads.
* Reduce the charging current on the luxpower inverter as we approach 100%. This is still experimental, but the theory is that if we can postpone BMS high voltage cut-off the BMS will do passive top balancing on the cells. The BMS SOC reports a reduced value, if the current charge cycle started on an empty battery, thus allowing a longer charge period and higher voltage at the top end. A totally empty battery happens about twice a month, and is timed to occur between 7AM and 9AM so that we don't linger in this state for very long. Hence the need to temporarily disconnect non-essential loads during the night, if necessary.
* Handles a specific situation, where on a hot day we have the aircon running into the late afternoon. To maximize solar yield, we let the 1.5k inverter carry its own loads rather than also drawing from the luxpower. Otherwise, the 1.5k system's solar yield will have nowhere to go.

## Next steps

* Remove config from repo. Should rather be supplied by the user at install time, and stored in the runtime environment.
* With recent tweaks, modules are no longer well structured. Code architecture could be improved. I'm thinking of applying the pipe-and-filter software pattern, to apply enabled automations in a set priority order.
* Add graphs for hubble battery's min and max cell voltage, so that we can better monitor cell imbalance.
* Improve the top-balancing situation for both systems. It could be that we have to disconnect the luxpower to hubble communication and switch to lead-acid profile, that allows voltages to be manually configured.

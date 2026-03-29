import axpert
import accumulator
import datetime
import math
import ast
import logger
# ast.literal_eval('{1.0: 15, 2.0: 30}')

defaultPositiveAmpImpactMultiplier = {
    13.44: 1.0, 13.49: 1.02, 13.55: 1.05, 13.57: 1.06
}
defaultAmpImpact = {
    0.0: 0.0,
    1.0: 0.021, 2.0: 0.033, 3.0: 0.043, 4.0: 0.055, 5.0: 0.067,
    6.0: 0.070, 7.0: 0.082, 8.0: 0.088, 9.0: 0.098, 10.0: 0.110,
    11.0: 0.117, 12.0: 0.126, 13.0: 0.134, 14.0: 0.146, 15.0: 0.156,
    16.0: 0.168, 17.0: 0.178, 18.0: 0.190, 19.0: 0.202, 20.0: 0.215,
    21.0: 0.226, 22.0: 0.240, 23.0: 0.250, 24.0: 0.260, 25.0: 0.270,
    26.0: 0.279, 27.0: 0.288, 28.0: 0.297, 29.0: 0.306, 30.0: 0.315,
    31.0: 0.324, 32.0: 0.333, 33.0: 0.342, 34.0: 0.351, 35.0: 0.360,
    36.0: 0.369, 37.0: 0.378, 38.0: 0.387, 39.0: 0.396, 40.0: 0.405,
    41.0: 0.414, 42.0: 0.423, 43.0: 0.432, 44.0: 0.441, 45.0: 0.450,
    46.0: 0.459, 47.0: 0.468, 48.0: 0.477, 49.0: 0.486, 50.0: 0.495,
    51.0: 0.504, 52.0: 0.513, 53.0: 0.522, 54.0: 0.531, 55.0: 0.540,
    -1.0: -0.004, -2.0: -0.016, -3.0: -0.029, -4.0: -0.042, -5.0: -0.055,
    -6.0: -0.069, -7.0: -0.085, -8.0: -0.097, -9.0: -0.109, -10.0: -0.120,
    -11.0: -0.131, -12.0: -0.141, -13.0: -0.151, -14.0: -0.161, -15.0: -0.171,
    -16.0: -0.181, -17.0: -0.191, -18.0: -0.201, -19.0: -0.211, -20.0: -0.221,
    -21.0: -0.230, -22.0: -0.239, -23.0: -0.248, -24.0: -0.256, -25.0: -0.264,
    -26.0: -0.271, -27.0: -0.278, -28.0: -0.285, -29.0: -0.292, -30.0: -0.299,
    -31.0: -0.306, -32.0: -0.313, -33.0: -0.320, -34.0: -0.327, -35.0: -0.334,
    -36.0: -0.341, -37.0: -0.348, -38.0: -0.355, -39.0: -0.362, -40.0: -0.369,
    -41.0: -0.376, -42.0: -0.383, -43.0: -0.390, -44.0: -0.397, -45.0: -0.404,
    -46.0: -0.411, -47.0: -0.418, -48.0: -0.425, -49.0: -0.432, -50.0: -0.439,
    -51.0: -0.446, -52.0: -0.453, -53.0: -0.460, -54.0: -0.467, -55.0: -0.474,
}
defaultRestingVoltageToStateOfCharge = {
    13.6: 100,
    13.48: 99,
    13.43: 90,
    13.38: 78,
    13.34: 72,
    13.28: 60,
    13.23: 50,
    13.16: 40,
    13.10: 35,
    13.04: 27,
    12.96: 20,
    12.75: 15,
    12.5: 10,
    11.0: 0,
}
defaultAmp10MinuteAverageWeight = 0.26

def slideScaleLookup(slideScale: dict, key: float, roundingMultiplier: float = 1.0):
    if isinstance(key, float) and math.isnan(key):
        return slideScaleLookup(slideScale, 0.0, roundingMultiplier)
    
    if key in slideScale:
        return slideScale[key]
    
    floor = math.floor(key * roundingMultiplier) / roundingMultiplier
    ceil = math.ceil(key * roundingMultiplier) / roundingMultiplier
    if floor in slideScale and ceil in slideScale:
        return (key - floor) * (slideScale[ceil] - slideScale[floor]) / (ceil - floor) + slideScale[floor]

    keys = slideScale.keys()
    floors = sorted(filter(lambda x: x < key, keys), reverse=True)
    ceils = sorted(filter(lambda x: x > key, keys))
    if len(floors) > 0 and len(ceils) > 0:
        return (key - floors[0]) * (slideScale[ceils[0]] - slideScale[floors[0]]) / (ceils[0] - floors[0]) + slideScale[floors[0]]
    elif len(floors) > 0:
        return slideScale[floors[0]]
    elif len(ceils) > 0:
        return slideScale[ceils[0]]

    return 0

def ampToVoltageImpact(amp, voltage, ampImpact=defaultAmpImpact, positiveAmpImpactMultiplier=defaultPositiveAmpImpactMultiplier):
    if isinstance(amp, float) and math.isnan(amp):
        return 0
    
    amp_impact_multiplier = 1.0 if amp <= 0 else slideScaleLookup(positiveAmpImpactMultiplier, voltage, 100)
    amp_impact = slideScaleLookup(ampImpact, amp)
    
    return amp_impact * amp_impact_multiplier

def estimateSoc(voltage, amps_in):
    estimated_resting_voltage = voltage - ampToVoltageImpact(amps_in, voltage)
    return slideScaleLookup(defaultRestingVoltageToStateOfCharge, estimated_resting_voltage)

def readCurrentStats(dev, luxpower_client=None, geyserwala_client=None):
    """Read current stats without recording to data files (lightweight refresh)"""
    try:
        mode = axpert.readMode(dev)
        info = axpert.readGeneralInfo(dev)
        dt = datetime.datetime.now()
        battery_amps = info['BatteryChargingCurrent'] - info['BatteryDischargeCurrent']
        load = info['OutputActivePower']

        stats = {
            'Time': datetime.datetime.strftime(dt, '%Y-%m-%d %H:%M:%S'),
            'PV': round(info['PV-InputWatts'], 2),
            'SOC': round(estimateSoc(info['BatteryVoltage'], battery_amps), 2),
            'Battery Amps': round(battery_amps, 2),
            'Surplus PV': round(info['PV-InputWatts'] - load, 2),
            'Battery Volts': round(info['BatteryVoltage'], 3),
            'PV Volts': round(info['PV-InputVoltage'], 2),
            'Load': round(load, 2),
            'Grid Volts': round(info['GridVoltage'], 2),
            'Line Mode': 1 if mode == "L" else 0,
            'Battery Mode': 1 if mode == "B" else 0,
            'Charging from Solar': info['DeviceStatus1'],
            'Charging from Utility': info['DeviceStatus0'],
        }
        
        # Add Luxpower stats with LXP prefix
        if luxpower_client:
            try:
                # Use only first page (registers 0-40) since all needed data is there
                data = luxpower_client.read_input(0, 40)
                if data and 'data' in data:
                    parsed = data['data']
                    
                    # Extract key values with LXP prefix using correct structure
                    stats['LXP_PV1'] = parsed.get('pv_power', {}).get('string_1', 0)
                    stats['LXP_Battery_SOC'] = parsed.get('battery', {}).get('soc', 0)
                    stats['LXP_AC_Output_Power'] = parsed.get('grid_power', {}).get('current_output', 0)
                    stats['LXP_Battery_Volts'] = parsed.get('battery', {}).get('voltage', 0)
                    
                    # Extract battery power data - combine charge and discharge into single stat
                    battery_power = parsed.get('battery_power', {})
                    charge = battery_power.get('charge', 0)
                    discharge = battery_power.get('discharge', 0)
                    # Positive for charging, negative for discharging
                    stats['LXP_Battery_Charge'] = charge - discharge
            except Exception as e:
                logger.log_warning(f"⚠️ Luxpower stats refresh error: {e}")
        
        # Add Geyserwala stats with GEY prefix
        if geyserwala_client:
            try:
                data = geyserwala_client.read_all_status()
                if data:
                    # Extract key values with GEY prefix
                    stats['GEY_Tank_Temp'] = data.get('tank-temp', 0)
                    stats['GEY_Collector_Temp'] = data.get('collector-temp', 0)
                    stats['GEY_Element_On'] = data.get('element-demand', False)
                    stats['GEY_Pump_Status'] = data.get('pump-status', False)
                    stats['GEY_Mode'] = data.get('mode', 'unknown')
                    stats['GEY_Setpoint'] = data.get('setpoint', 0)
            except Exception as e:
                logger.log_warning(f"⚠️ Geyserwala stats refresh error: {e}")
        
        return stats
        
    except Exception as e:
        logger.log_error(f"❌ Current stats read error: {e}")
        return None

def gatherStats(dev, statsArray60, luxpower_client=None, geyserwala_client=None):
    """Gather stats and record to data files"""
    # Get current stats without recording
    stats = readCurrentStats(dev, luxpower_client, geyserwala_client)
    if not stats:
        return None
    
    # Apply 10-minute average for SOC calculation (only difference from readCurrentStats)
    statsArray10 = list(filter(lambda x: datetime.datetime.strptime(x['Time'], '%Y-%m-%d %H:%M:%S') + datetime.timedelta(minutes=10) > datetime.datetime.now(), statsArray60))
    
    if len(statsArray10) > 0:
        amp10 = 0
        for stat in statsArray10:
            amp10 += float(stat['Battery Amps'])
        amp10 = round(amp10 / len(statsArray10), 2)
        
        # Recalculate SOC with 10-minute average
        battery_amps = stats['Battery Amps']
        voltage = stats['Battery Volts']
        stats['SOC'] = round(estimateSoc(voltage, battery_amps * (1.0-defaultAmp10MinuteAverageWeight) + amp10 * defaultAmp10MinuteAverageWeight), 2)
    
    # Record to data files
    dt = datetime.datetime.now()
    for bucketDescriptor in ['m1', 'm5', 'm30', 'h12']:
        container = {}
        accumulator.readContainerFile(container, 'stats/data', bucketDescriptor, dt)
        for stat in stats.keys():
            accumulator.accumulatePropValue(container, bucketDescriptor, dt, stat, stats[stat])
        accumulator.writeContainerFile(container, 'stats/data', bucketDescriptor, dt)

    return stats

def get_solar_average_for_time(target_time):
    """
    Get the 20-minute average solar yield for a specific date and time.
    
    Args:
        target_time: datetime object for the target time
    
    Returns:
        float: average solar yield over 20 minutes, or 0 if no data
    """
    try:
        # Get historical data for the last 20 minutes from the target time
        recent_data = read_historical_data(target_time, 20)
        
        if recent_data:
            # Calculate average PV_avg from the data points
            avg_pv = sum(float(point.get('PV_avg', 0)) for point in recent_data) / len(recent_data)
            return avg_pv
        else:
            return 0.0
    except Exception as e:
        logger.log_error(f"Error getting solar average for {target_time}: {e}")
        return 0.0

def read_historical_data(target_time, minutes_back=20):
    """
    Read historical data for the specified time period using accumulator.
    Returns 4 relevant data points based on the date & time given.
    
    Args:
        target_time: datetime object for the target time
        minutes_back: number of minutes to look back (default 20)
    
    Returns:
        list of data points from the last 20 minutes
    """
    try:
        # Calculate the time range we need to cover
        start_time = target_time - datetime.timedelta(minutes=minutes_back)
        
        # Use accumulator functions to determine container boundaries
        current_container_start = accumulator.bucketContainerStart('m5', target_time)
        start_container_start = accumulator.bucketContainerStart('m5', start_time)
        
        # Read data from current 4-hour file
        current_container = {}
        accumulator.readContainerFile(current_container, 'stats/data', 'm5', target_time)
        
        # Read data from previous 4-hour file if needed (only if crossing 4-hour boundary)
        previous_container = {}
        if current_container_start != start_container_start:
            accumulator.readContainerFile(previous_container, 'stats/data', 'm5', start_time)
        
        # Combine data from both containers
        all_data = []
        
        # Process current container data
        current_container_key = datetime.datetime.strftime(current_container_start, '%Y-%m-%d %H:%M:%S')
        if current_container_key in current_container:
            for bucket_key, bucket_data in current_container[current_container_key].items():
                bucket_time = datetime.datetime.strptime(bucket_key, '%Y-%m-%d %H:%M:%S')
                if bucket_time >= start_time and bucket_time <= target_time:
                    data_point = _extract_data_point(bucket_key, bucket_data)
                    all_data.append(data_point)
        
        # Process previous container data if needed
        if previous_container:
            previous_container_key = datetime.datetime.strftime(start_container_start, '%Y-%m-%d %H:%M:%S')
            if previous_container_key in previous_container:
                for bucket_key, bucket_data in previous_container[previous_container_key].items():
                    bucket_time = datetime.datetime.strptime(bucket_key, '%Y-%m-%d %H:%M:%S')
                    if bucket_time >= start_time and bucket_time <= target_time:
                        data_point = _extract_data_point(bucket_key, bucket_data)
                        all_data.append(data_point)
        
        # Sort by time and return the last 4 data points (20 minutes worth)
        all_data.sort(key=lambda x: x['Time'])
        result = all_data[-4:] if len(all_data) >= 4 else all_data
        return result
        
    except Exception as e:
        logger.log_error(f"Error reading historical data: {e}")
        return []

def _extract_data_point(bucket_key, bucket_data):
    """Extract relevant data points from bucket data"""
    return {
        'Time': bucket_key,
        'PV': bucket_data.get('PV', 0),
        'PV_avg': bucket_data.get('PV_avg', 0),
        'LXP_PV1': bucket_data.get('LXP_PV1', 0),
        'SOC': bucket_data.get('SOC', 0),
        'Battery Amps': bucket_data.get('Battery Amps', 0),
        'Surplus PV': bucket_data.get('Surplus PV', 0)
    }

def calculate_solar_rating():
    """Calculate solar input rating from 0 to 1 (point 9)"""
    try:
        now = datetime.datetime.now()
        
        # Get current 20-minute average
        current_avg = get_solar_average_for_time(now)
        logger.log_info(f"📊 Solar rating inputs - Current 20min avg: {current_avg:.2f}W")
        
        if current_avg == 0:
            logger.log_info("No current solar output - rating: 0.0")
            return 0.0
        
        # Get historical averages for the last 10 days (excluding today)
        historical_averages = []
        for days_back in range(1, 11):  # 1 to 10 days back
            historical_time = now - datetime.timedelta(days=days_back)
            historical_avg = get_solar_average_for_time(historical_time)
            if historical_avg > 0:
                historical_averages.append(historical_avg)
        
        if not historical_averages:
            logger.log_info("No historical data available - rating: 0.5")
            return 0.5
        
        # Find the maximum historical average
        max_historical = max(historical_averages)
        logger.log_info(f"📊 Solar rating inputs - Max historical: {max_historical:.2f}W")
        
        # Calculate rating: current / max_historical
        if max_historical > 0:
            rating = min(current_avg / max_historical, 1.0)  # Cap at 1.0
            logger.log_info(f"📊 Solar rating calculation: {rating:.3f} = {current_avg:.2f}W / {max_historical:.2f}W")
            return rating
        else:
            logger.log_info("No valid historical data - rating: 0.5")
            return 0.5
            
    except Exception as e:
        logger.log_error(f"Solar rating calculation error: {e}")
        return 0.5

def calculate_expected_axpert_charging(stats=None):
    """Calculate expected axpert charging current based on current stats"""
    try:
        if not stats:
            return 0
        
        # Get current stats
        axp_pv = stats.get('PV', 0)  # Axpert PV input
        axp_battery_amps = stats.get('Battery Amps', 0)  # Current battery amps
        
        logger.log_info(f"🔌 Axpert stats - PV: {axp_pv}W, Battery Amps: {axp_battery_amps}A")
        
        # Calculate solar contribution to battery charging
        # Positive PV means solar is contributing to battery charging
        # Use fixed charging voltage of 14.2V (typical axpert charging voltage)
        charging_voltage = 14.2
        solar_contribution_amps = 0
        if axp_pv > 0:
            # Estimate solar contribution using fixed charging voltage
            solar_contribution_amps = axp_pv / charging_voltage
        
        # Remove solar contribution from total battery amps to get utility charging
        utility_charging_amps = axp_battery_amps - solar_contribution_amps
        
        logger.log_info(f"🔌 Solar contribution: {solar_contribution_amps:.2f}A (PV {axp_pv}W / {charging_voltage}V), Utility charging: {utility_charging_amps:.2f}A")
        
        # Round to nearest configurable value: 0, 2, 10, 20, 30, 40
        configurable_values = [0, 2, 10, 20, 30, 40]
        expected_utility_charging = min(configurable_values, key=lambda x: abs(x - utility_charging_amps))
        
        logger.log_info(f"🔌 Expected utility charging: {expected_utility_charging}A (rounded from {utility_charging_amps:.2f}A)")
        
        return expected_utility_charging
        
    except Exception as e:
        logger.log_error(f"Expected axpert charging calculation error: {e}")
        return 0

def detect_transfer_switch_status(stats=None, charging_params=None):
    """Detect transfer switch status (point 5) using stats-based calculation"""
    try:
        # Use provided stats or default to 0
        lxp_output = stats.get('LXP_AC_Output_Power', 0) if stats else 0
        logger.log_info(f"🔌 Transfer switch inputs - LXP AC Output: {lxp_output}W")
        
        # Point 5.a: If luxpower AC output < 30 watts, then it is "From utility"
        if lxp_output < 30:
            logger.log_info(f"🔌 Transfer switch decision - LXP output {lxp_output}W < 30W -> From utility")
            return "From utility"
        
        axp_battery_mode = stats.get('Battery Mode', 0) if stats else 0  # 1 = Battery Mode, 0 = Line Mode
        
        # Only subtract axpert load if it's in Line Mode (drawing from LXP)
        # In Battery Mode, axpert is not drawing current from LXP
        if axp_battery_mode == 1 and lxp_output >= 30:
            logger.log_info(f"🔌 Transfer switch decision, no AXP - LXP output {lxp_output}W >= 30W -> From inverter")
            return "From inverter"

        # Point 5.b: Calculate expected axpert behavior based on current stats
        axp_load = stats.get('Load', 0) if stats else 0
        # Calculate expected utility charging current from stats
        expected_utility_charging_amps = calculate_expected_axpert_charging(stats)
        
        # Calculate net power flow using expected charging current
        # Use fixed charging voltage of 14.2V (typical axpert charging voltage)
        charging_voltage = 14.2
        expected_charging_power = expected_utility_charging_amps * charging_voltage        
        net_power = lxp_output - expected_charging_power - axp_load
        
        logger.log_info(f"🔌 Transfer switch inputs - Expected utility charging: {expected_utility_charging_amps}A * {charging_voltage}V = {expected_charging_power:.1f}W")
        logger.log_info(f"🔌 Transfer switch inputs - Axpert load: {axp_load}W")
        logger.log_info(f"🔌 Transfer switch calculation - Net power: {lxp_output}W - {expected_charging_power:.1f}W - {axp_load}W = {net_power:.1f}W")
        
        if net_power < 20:
            logger.log_info(f"🔌 Transfer switch decision - Net power {net_power:.1f}W < 20W -> From utility")
            return "From utility"
        else:
            logger.log_info(f"🔌 Transfer switch decision - Net power {net_power:.1f}W >= 20W -> From inverter")
            return "From inverter"
        
    except Exception as e:
        logger.log_error(f"Transfer switch detection error: {e}")
        return "Unknown"

# Cache for geyser calculations to avoid redundant calls
_geyser_cache = {
    'transfer_status': None,
    'solar_rating': None,
    'target_temp': None,
    'transfer_status_time': None,
    'solar_rating_time': None,
    'target_temp_time': None
}

geyser_target_temp_by_hour = {
    0: 30,
    1: 30,
    2: 30,
    3: 30,
    4: 30,
    5: 30,
    6: 48,
    7: 48,
    8: 48,
    9: 48,
    10: 50,
    11: 55,
    12: 60,
    13: 65,
    14: 70,
    15: 75,
    16: 65,
    17: 55,
    18: 48,
    19: 30,
    20: 30,
    21: 30,
    22: 30,
    23: 30
}

def calculate_geyser_target_temp(stats=None, charging_params=None, luxpower_client=None, geyserwala_client=None, geyser_currently_on=False, use_cache=True):
    """Calculate geyser temperature target (point 10) with graceful degradation and caching"""
    try:
        # Check cache first (valid for 30 seconds)
        now = datetime.datetime.now()
        if (use_cache and _geyser_cache['target_temp_time'] is not None and 
            (now - _geyser_cache['target_temp_time']).total_seconds() < 30 and
            _geyser_cache['target_temp'] is not None):
            return _geyser_cache['target_temp']
        
        result = 30

        hour = datetime.datetime.now().hour
        # Point 13: Graceful degradation - if inverters unreachable but geyser reachable
        if not luxpower_client and geyserwala_client:
            # Minimal heating when inverters are unreachable
            logger.log_info(f"🔥 Geyser target temp inputs - Luxpower unreachable, hour: {hour}")
            if 16 <= hour < 18:  # 4pm to 6pm
                logger.log_info(f"🔥 Geyser target temp decision - Peak hours (16-18h) -> 48°C")
                result = 48
        else:
            # Get transfer status (with caching)
            transfer_status = _get_cached_transfer_status(stats, charging_params)
                                   
            # Point 10.a: Transfer switch = "From Utility"
            if transfer_status == "From utility":
                logger.log_info(f"🔥 Geyser target temp inputs - Transfer: {transfer_status}, hour: {hour}")
                if 16 <= hour < 18:  # 4pm to 6pm
                    logger.log_info(f"🔥 Geyser target temp - Peak hours (16-18h) -> 48°C")
                    result = 48
            else:
                # Use provided stats or default to 0
                axpert_pv = stats.get('PV', 0) if stats else 0
                axpert_soc = stats.get('SOC', 0) if stats else 0
                lxp_soc = stats.get('LXP_Battery_SOC', 0) if stats else 0
                # Get solar rating (with caching)
                solar_rating = _get_cached_solar_rating() if axpert_soc < 96 else 1.0
                logger.log_info(f"🔥 Geyser target temp inputs - Transfer: {transfer_status}, Solar rating: {solar_rating:.3f}, Axpert PV: {axpert_pv}W, Axpert SOC: {axpert_soc}%, LXP SOC: {lxp_soc}%")

                # We are using axpert and not luxpower PV, because the luxpower's PV drops earlier in the day when battery gets full.                
                if (solar_rating >= 0.4 and axpert_pv > 140) or axpert_soc >= 96:
                    if lxp_soc > 90 or (geyser_currently_on and lxp_soc > 80):
                        result = geyser_target_temp_by_hour[hour]
                        logger.log_info(f"🔥 Geyser decision: Good solar, Good LXP SOC")
                    elif lxp_soc > 70 or (geyser_currently_on and lxp_soc > 60):
                        result = min(geyser_target_temp_by_hour[hour], 48)
                        logger.log_info(f"🔥 Geyser decision: Good solar, Acceptable LXP SOC")
                elif lxp_soc > 80 or (geyser_currently_on and lxp_soc > 70):
                    result = min(geyser_target_temp_by_hour[hour], 48)
                    logger.log_info(f"🔥 Geyser decision: Low solar, Good LXP SOC")
                
                logger.log_info(f"🔥 Geyser target temp: {result}°C")
        # Update cache
        _geyser_cache['target_temp'] = result
        _geyser_cache['target_temp_time'] = now
        return result
            
    except Exception as e:
        logger.log_error(f"Target temp calculation error: {e}")
        return 30

def _get_cached_transfer_status(stats, charging_params):
    """Get transfer status with caching"""
    now = datetime.datetime.now()
    if (_geyser_cache['transfer_status'] is not None and 
        _geyser_cache['transfer_status_time'] is not None and 
        (now - _geyser_cache['transfer_status_time']).total_seconds() < 30):
        return _geyser_cache['transfer_status']
    
    # Calculate and cache
    transfer_status = detect_transfer_switch_status(stats, charging_params)
    _geyser_cache['transfer_status'] = transfer_status
    _geyser_cache['transfer_status_time'] = now
    return transfer_status

def _get_cached_solar_rating():
    """Get solar rating with caching"""
    now = datetime.datetime.now()
    if (_geyser_cache['solar_rating'] is not None and 
        _geyser_cache['solar_rating_time'] is not None and 
        (now - _geyser_cache['solar_rating_time']).total_seconds() < 30):
        return _geyser_cache['solar_rating']
    
    # Calculate and cache
    solar_rating = calculate_solar_rating()
    _geyser_cache['solar_rating'] = solar_rating
    _geyser_cache['solar_rating_time'] = now
    return solar_rating

def should_geyser_turn_on(stats=None, charging_params=None, geyser_last_off_time=None, geyser_last_off_temp=None, geyserwala_client=None, luxpower_client=None, geyser_currently_on=False):
    """Check if geyser should be turned on (point 3) with graceful degradation"""
    try:
        # Point 14: Graceful degradation - if geyser is unreachable, skip geyser logic
        if not geyserwala_client:
            logger.log_info(f"🔥 Geyser turn-on inputs - Geyserwala unreachable -> Skip geyser logic")
            return False
        
        # Use provided stats or default to 0
        current_temp = stats.get('GEY_Tank_Temp', 0) if stats else 0
        axpert_soc = float(stats.get('SOC', 0)) if stats else 0
        lxp_output = stats.get('LXP_AC_Output_Power', 0) if stats else 0
        target_temp = calculate_geyser_target_temp(stats, charging_params, luxpower_client, geyserwala_client, geyser_currently_on, use_cache=True)
        
        # Point 3.a: Time/temperature conditions
        time_since_off = datetime.datetime.now() - geyser_last_off_time if geyser_last_off_time else datetime.timedelta(hours=1)
        temp_drop = (geyser_last_off_temp - current_temp) if geyser_last_off_temp else 0
        
        time_condition = (time_since_off.total_seconds() >= 1800) or (temp_drop >= 12)
        
        # Point 3.b: Temperature condition
        temp_condition = current_temp <= (target_temp - 6)
        
        # Point 3.c: Battery SOC condition
        soc_condition = axpert_soc >= 30
        
        # Point 3.d: Luxpower output condition (skip if luxpower unreachable)
        if not luxpower_client:
            output_condition = True  # Skip this check if luxpower unreachable
            logger.log_info(f"🔥 Geyser turn-on inputs - Luxpower unreachable, skipping output check")
        else:
            # Use same calculation as detect_transfer_switch_status()
            # Account for axpert power consumption when in battery mode
            if charging_params:
                axp_utility_charging_current = charging_params.get('utility_charge_current', 0)
                axp_charger_voltage = charging_params.get('charger_voltage', 0)
            else:
                axp_utility_charging_current = 0
                axp_charger_voltage = 0
                
            axp_load = stats.get('Load', 0) if stats else 0
            
            # Calculate net power available after axpert consumption
            lxp_only_output = lxp_output - (axp_utility_charging_current * axp_charger_voltage) - axp_load
            output_condition = lxp_only_output < 1500
            logger.log_info(f"🔥 Geyser turn-on inputs - LXP output: {lxp_output}W, Net available: {lxp_only_output}W, Output condition: {output_condition}")
        
        # Log all conditions
        logger.log_info(f"🔥 Geyser turn-on inputs - Current temp: {current_temp}°C, Target: {target_temp}°C, SOC: {axpert_soc}%")
        logger.log_info(f"🔥 Geyser turn-on inputs - Time since off: {time_since_off.total_seconds()/60:.1f} minutes, Temp drop: {temp_drop}°C")
        logger.log_info(f"🔥 Geyser turn-on conditions - Time: {time_condition}, Temp: {temp_condition}, SOC: {soc_condition}, Output: {output_condition}")
        
        result = time_condition and temp_condition and soc_condition and output_condition
        logger.log_info(f"🔥 Geyser turn-on decision - {'TURN ON' if result else 'STAY OFF'}")
        return result
        
    except Exception as e:
        logger.log_error(f"Geyser turn-on check error: {e}")
        return False

def should_geyser_turn_off(stats=None, charging_params=None, luxpower_client=None, geyserwala_client=None, geyser_currently_on=False):
    """Check if geyser should be turned off (point 4)"""
    try:
        # Use provided stats or default to 0
        current_temp = stats.get('GEY_Tank_Temp', 0) if stats else 0
        axpert_soc = float(stats.get('SOC', 0)) if stats else 0
        target_temp = calculate_geyser_target_temp(stats, charging_params, luxpower_client, geyserwala_client, geyser_currently_on, use_cache=True)
        
        logger.log_info(f"🔥 Geyser turn-off inputs - Current temp: {current_temp}°C, Target: {target_temp}°C, SOC: {axpert_soc}%")
        
        # Temperature target reached
        if current_temp >= target_temp:
            logger.log_info(f"🔥 Geyser turn-off decision - Temperature target reached ({current_temp}°C >= {target_temp}°C) -> TURN OFF")
            return True, "Temperature target reached"
        
        # Battery SOC too low
        if axpert_soc < 20:
            logger.log_info(f"🔥 Geyser turn-off decision - Battery SOC too low ({axpert_soc}% < 20%) -> TURN OFF")
            return True, "Battery SOC too low"
        
        logger.log_info(f"🔥 Geyser turn-off decision - No conditions met -> STAY ON")
        return False, None
        
    except Exception as e:
        logger.log_error(f"Geyser turn-off check error: {e}")
        return False, None


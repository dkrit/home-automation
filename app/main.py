import axpert
import stats as stats_module
import manage
import luxpower
import geyserwala
import accumulator
import time
import datetime
import json
import os
import logger

# Global state variables for geyser control
geyser_last_off_time = datetime.datetime.now() - datetime.timedelta(minutes=30)  # 30 minutes ago
geyser_last_off_temp = 65  # Default temperature (will be updated on first call)
geyser_currently_on = False
geyser_monitoring_active = False
transfer_switch_status = "Unknown"  # "From utility" or "From inverter"

# Device connections
dev = axpert.connect()
luxpower_client = None
geyserwala_client = None

# Timing variables
update_interval = 3
lastUpdate = datetime.datetime.now() - datetime.timedelta(minutes=update_interval)
statsArray60 = []

# Initialize device connections
def initialize_devices():
    global luxpower_client, geyserwala_client, geyser_currently_on, geyser_last_off_time, geyser_last_off_temp, geyser_monitoring_active
    
    # Initialize Luxpower client
    try:
        luxpower_client = luxpower.LuxPowerClient(host="192.168.1.177", debug=False)
        if luxpower_client.connect():
            logger.log_info("✅ Luxpower connected")
        else:
            logger.log_error("❌ Luxpower connection failed")
            luxpower_client = None
    except Exception as e:
        logger.log_error(f"❌ Luxpower initialization error: {e}")
        luxpower_client = None
    
    # Initialize Geyserwala client
    try:
        geyserwala_client = geyserwala.GeyserwalaClient(
            host="192.168.1.94", 
            username="admin", 
            password="pwd", 
            debug=False
        )
        if geyserwala_client.connect():
            logger.log_info("✅ Geyserwala connected")
            # Check if geyser is already on at startup
            try:
                actual_geyser_status = geyserwala_client.read_element_status()
                if actual_geyser_status is not None:
                    geyser_currently_on = actual_geyser_status
                    if geyser_currently_on:
                        # If geyser is on at startup, set last_off_time to 1 hour ago so it can turn on immediately if needed
                        geyser_last_off_time = datetime.datetime.now() - datetime.timedelta(hours=1)
                        geyser_last_off_temp = geyserwala_client.read_geyser_temp() or 30
                        geyser_monitoring_active = True
                        logger.log_info(f"🔥 Geyser is already ON at startup - last_off_time set to 1 hour ago")
                    else:
                        logger.log_info(f"🔥 Geyser is OFF at startup")
            except Exception as e:
                logger.log_warning(f"⚠️ Geyser status check at startup failed: {e}")
        else:
            logger.log_error("❌ Geyserwala connection failed")
            geyserwala_client = None
    except Exception as e:
        logger.log_error(f"❌ Geyserwala initialization error: {e}")
        geyserwala_client = None



def turn_geyser_on():
    """Turn geyser on with proper error handling (point 6)"""
    global geyser_currently_on
    
    try:
        # Point 6: Put axpert in battery mode first
        axpert.sendCommand(dev, "POP02")  # Battery mode
        response = axpert.readData(dev)
        if "(ACK9" not in response:
            logger.log_error(f"❌ Axpert battery mode failed: {response}")
            return False
        
        # Turn geyser element on
        if geyserwala_client and geyserwala_client.turn_element_on():
            geyser_currently_on = True
            logger.log_info("✅ Geyser turned on")
            return True
        else:
            logger.log_error("❌ Geyser turn-on failed")
            return False
            
    except Exception as e:
        logger.log_error(f"❌ Geyser turn-on error: {e}")
        return False

def turn_geyser_off(stats=None):
    """Turn geyser off and record state (point 4)"""
    global geyser_currently_on, geyser_last_off_time, geyser_last_off_temp
    
    try:
        if geyserwala_client and geyserwala_client.turn_element_off():
            geyser_currently_on = False
            geyser_last_off_time = datetime.datetime.now()
            # Use provided stats to record temperature
            geyser_last_off_temp = stats.get('GEY_Tank_Temp', 0) if stats else 0
            logger.log_info("✅ Geyser turned off")
            return True
        else:
            logger.log_error("❌ Geyser turn-off failed")
            return False
            
    except Exception as e:
        logger.log_error(f"❌ Geyser turn-off error: {e}")
        return False

def get_luxpower_output_power():
    """Get only the luxpower AC output power - lightweight for 2.5s monitoring"""
    if not luxpower_client:
        return None
    
    try:
        # Use only first page (registers 0-40) since all needed data is there
        data = luxpower_client.read_input(0, 40)
        if data and 'data' in data:
            parsed = data['data']
            return parsed.get('grid_power', {}).get('current_output', 0)
    except Exception as e:
        logger.log_error(f"❌ Luxpower output power error: {e}")
    
    return None

def geyser_monitoring_loop(gathered_stats=None):
    """10s monitoring loop when geyser is on (point 7) with graceful degradation"""
    global geyser_monitoring_active
    
    if not geyser_monitoring_active or not geyser_currently_on:
        return
    
    try:
        # Point 13: Skip monitoring if luxpower is unreachable
        if not luxpower_client:
            return
        
        # Use provided stats or fallback to fresh data request
        if gathered_stats and 'LXP_AC_Output_Power' in gathered_stats:
            lxp_output = gathered_stats['LXP_AC_Output_Power']
            logger.log_info(f"🔥 Geyser monitoring - Using cached LXP output: {lxp_output}W")
        else:
            # Fallback: Get fresh luxpower output power if no stats provided
            lxp_output = get_luxpower_output_power()
            logger.log_info(f"🔥 Geyser monitoring - Using fresh LXP output: {lxp_output}W")
        
        # Point 7: Turn off if output > 3000W (relaxed threshold for 2000W geyser element)
        if lxp_output is not None and lxp_output > 3000:
            logger.log_warning(f"⚠️ Luxpower output {lxp_output}W > 3000W, turning geyser off")
            turn_geyser_off()  # No stats needed for turn_geyser_off in monitoring loop
            geyser_monitoring_active = False
        else:
            # Log that we're keeping the geyser on
            logger.log_info(f"🔥 Geyser monitoring - LXP output {lxp_output}W <= 3000W, keeping geyser ON")
            
    except Exception as e:
        logger.log_error(f"❌ Geyser monitoring error: {e}")
        # Point 7: Keep geyser on and try again next interval

def stats_gathering_agenda():
    """Stats gathering agenda (point 1) - called every 10 seconds by main loop"""
    global statsArray60, luxpower_client, geyserwala_client
    
    try:
        # Test reachability of connected clients and clear if unreachable
        if luxpower_client is not None:
            try:
                # Test reachability with a lightweight operation
                test_output = get_luxpower_output_power()
                if test_output is None:  # If the function returns None, connection is bad
                    logger.log_warning("⚠️ Luxpower client unreachable, clearing connection")
                    luxpower_client = None
            except Exception as e:
                logger.log_warning(f"⚠️ Luxpower reachability test failed: {e}, clearing connection")
                luxpower_client = None
        
        if geyserwala_client is not None:
            try:
                # Test reachability with a simple status check
                response = geyserwala_client.session.get(f"{geyserwala_client.base_url}/api/value/status", timeout=5)
                if response.status_code != 200:
                    logger.log_warning("⚠️ Geyserwala client unreachable, clearing connection")
                    geyserwala_client = None
            except Exception as e:
                logger.log_warning(f"⚠️ Geyserwala reachability test failed: {e}, clearing connection")
                geyserwala_client = None
        
        # Attempt to reconnect clients if they are not connected
        if luxpower_client is None:
            try:
                logger.log_info("🔄 Attempting to reconnect Luxpower client...")
                luxpower_client = luxpower.LuxPowerClient(host="192.168.1.177", debug=False)
                if luxpower_client.connect():
                    logger.log_info("✅ Luxpower reconnected")
                else:
                    logger.log_error("❌ Luxpower reconnection failed")
                    luxpower_client = None
            except Exception as e:
                logger.log_error(f"❌ Luxpower reconnection error: {e}")
                luxpower_client = None
        
        if geyserwala_client is None:
            try:
                logger.log_info("🔄 Attempting to reconnect Geyserwala client...")
                geyserwala_client = geyserwala.GeyserwalaClient(
                    host="192.168.1.94", 
                    username="admin", 
                    password="pwd", 
                    debug=False
                )
                if geyserwala_client.connect():
                    logger.log_info("✅ Geyserwala reconnected")
                else:
                    logger.log_error("❌ Geyserwala reconnection failed")
                    geyserwala_client = None
            except Exception as e:
                logger.log_error(f"❌ Geyserwala reconnection error: {e}")
                geyserwala_client = None
        
        # Gather all stats (axpert, luxpower, geyserwala) in one call
        stats = stats_module.gatherStats(dev, statsArray60, luxpower_client, geyserwala_client)
        statsArray60.append(stats)
        statsArray60 = list(filter(lambda x: datetime.datetime.strptime(x['Time'], '%Y-%m-%d %H:%M:%S') + datetime.timedelta(minutes=60) > datetime.datetime.now(), statsArray60))
        
        return stats  # Return the gathered stats
        
    except Exception as e:
        logger.log_error(f"❌ Stats gathering error: {e}")
        return None

def decision_agenda(gathered_stats):
    """3-minute decision agenda (points 2-4) with graceful degradation"""
    global lastUpdate, geyser_currently_on, geyser_monitoring_active, geyser_last_off_time, geyser_last_off_temp
    
    now = datetime.datetime.now()
    
    if (now - lastUpdate).total_seconds() >= 60 * update_interval:
        try:
            messages = []

            # Point 2: Update axpert mode
            charging_params = manage.updateInverter(dev, gathered_stats, statsArray60)

            # Log update messages
            if charging_params and 'update_messages' in charging_params:
                for message in charging_params['update_messages']:
                    logger.log_info(message)
            
            if charging_params:
                logger.log_info(f"🔋 Charging parameters: utility_current={charging_params.get('utility_charge_current', 0)}A, utilize_axpert_battery={charging_params.get('utilize_axpert_battery', False)}, utilize_axpert_solar={charging_params.get('utilize_axpert_solar', False)}, charger_voltage={charging_params.get('charger_voltage', 0)}V, trgt={charging_params.get('trgt', 0)}%")
                # Add charging parameters to messages
                messages.append(f"🔋 Charging parameters: utility_current={charging_params.get('utility_charge_current', 0)}A, utilize_axpert_battery={charging_params.get('utilize_axpert_battery', False)}, utilize_axpert_solar={charging_params.get('utilize_axpert_solar', False)}, charger_voltage={charging_params.get('charger_voltage', 0)}V, trgt={charging_params.get('trgt', 0)}%")

            # Get transfer switch status
            transfer_switch_status = stats_module._get_cached_transfer_status(gathered_stats, charging_params)
            # Update Luxpower Off-Grid EOD setting based on time
            if update_luxpower_eod_setting(transfer_switch_status):
                target_eod, target_warn, is_increasing, time_period = get_time_based_eod_setting(transfer_switch_status)
                messages.append(f"🔋 Luxpower Off-Grid EOD set to {target_eod}%, Warning SOC set to {target_warn}% ({time_period})")

            # If luxpower SOC is > 98%, set the max charge rate to 2A.
            result = update_luxpower_max_charge_rate(gathered_stats.get('LXP_Battery_SOC', 0))
            messages.append(f"🔋 Setting max LXP charge rate to {result}A")

            # Point 14: Graceful degradation - if geyser unreachable, ignore geyser logic
            if not geyserwala_client:
                write_update_txt(gathered_stats, charging_params, messages)
                lastUpdate = now
                return

            # Check actual geyser status to sync with geyser_currently_on
            try:
                # Use cached geyser status from gathered_stats if available
                if 'GEY_Element_On' in gathered_stats:
                    actual_geyser_status = gathered_stats['GEY_Element_On']
                    logger.log_info(f"🔄 Geyser status sync - Using cached data: {actual_geyser_status}")
                else:
                    # Fallback: Get fresh geyser status if no cached data available
                    actual_geyser_status = geyserwala_client.read_element_status()
                    logger.log_info(f"🔄 Geyser status sync - Using fresh API call: {actual_geyser_status}")
                
                if actual_geyser_status is not None:
                    if actual_geyser_status != geyser_currently_on:
                        logger.log_info(f"🔄 Geyser status sync: was {geyser_currently_on}, actual {actual_geyser_status}")
                        geyser_currently_on = actual_geyser_status
                        # Update monitoring status based on actual state
                        geyser_monitoring_active = geyser_currently_on
                        if not geyser_currently_on:
                            geyser_last_off_time = datetime.datetime.now()
                            geyser_last_off_temp = gathered_stats.get('GEY_Tank_Temp', 0) if gathered_stats else 0

            except Exception as e:
                logger.log_warning(f"⚠️ Geyser status check failed: {e}")
                # Continue with current geyser_currently_on value if check fails
            
            # Point 3 & 4: Make geyser decisions once and cache results
            geyser_should_turn_on = False
            geyser_should_turn_off = False
            turn_off_reason = None
            
            if not geyser_currently_on:
                # Check if geyser should turn on
                geyser_should_turn_on = stats_module.should_geyser_turn_on(gathered_stats, charging_params, geyser_last_off_time, geyser_last_off_temp, geyserwala_client, luxpower_client, geyser_currently_on)
                if geyser_should_turn_on:
                    if turn_geyser_on():
                        geyser_monitoring_active = True
                        messages.append("✅ Geyser turned on")
            elif geyser_currently_on:
                # Check if geyser should turn off
                geyser_should_turn_off, turn_off_reason = stats_module.should_geyser_turn_off(gathered_stats, charging_params, luxpower_client, geyserwala_client, geyser_currently_on)
                if geyser_should_turn_off:
                    turn_geyser_off(gathered_stats)
                    geyser_monitoring_active = False
                    logger.log_info(f"Geyser turned off: {turn_off_reason}")
                    messages.append(f"✅ Geyser turned off: {turn_off_reason}")
            
            # Update geyserwala setpoint temperature based on geyser decision
            try:
                # Calculate target temperature (uses caching)
                target_temp = stats_module.calculate_geyser_target_temp(gathered_stats, charging_params, luxpower_client, geyserwala_client)
                
                # Determine final geyser state after decisions
                final_geyser_state = geyser_currently_on
                if geyser_should_turn_on:
                    final_geyser_state = True
                elif geyser_should_turn_off:
                    final_geyser_state = False
                
                # Set setpoint based on final decision
                if final_geyser_state:
                    # Geyser should be ON - set to calculated target temperature
                    if geyserwala_client.set_external_setpoint(target_temp):
                        logger.log_info(f"🌡️ Setpoint updated to {target_temp}°C (geyser should be ON)")
                        messages.append(f"🌡️ Setpoint updated to {target_temp}°C (geyser should be ON)")
                    else:
                        logger.log_error(f"❌ Failed to set setpoint to {target_temp}°C")
                        messages.append(f"❌ Failed to set setpoint to {target_temp}°C")
                else:
                    # Geyser should be OFF - set to 30°C
                    if geyserwala_client.set_external_setpoint(30):
                        logger.log_info(f"🌡️ Setpoint updated to 30°C (geyser should be OFF)")
                        messages.append(f"🌡️ Setpoint updated to 30°C (geyser should be OFF)")
                    else:
                        logger.log_error(f"❌ Failed to set setpoint to 30°C")
                        messages.append(f"❌ Failed to set setpoint to 30°C")
                        
            except Exception as e:
                logger.log_error(f"❌ Setpoint update error: {e}")
                        
            write_update_txt(gathered_stats, charging_params, messages)            
            lastUpdate = now
            
        except Exception as e:
            logger.log_error(f"❌ Decision agenda error: {e}")

def get_time_based_eod_setting(transfer_switch_status):
    """Determine the correct Off-Grid EOD and Warning SOC settings based on current time"""
    now = datetime.datetime.now()
    current_hour = now.hour
    
    if current_hour < 4:
        return 30, 30, False, "12pm-4am"
    elif 4 <= current_hour < 5:
        return 27, 27, False, "4am-5am"
    elif 5 <= current_hour < 6:
        return 20, 20, False, "5am-6am"
    elif 6 <= current_hour < 7:
        return 16, 16, False, "6am-7am"
    elif 7 <= current_hour < 8:
        return 8, 8, False, "7am-8am"
    elif 8 <= current_hour < 13:
        return 0, 0, False, "8am-1pm"
    elif 13 <= current_hour < 17:
        return 54, 57 if transfer_switch_status == "From inverter" else 54, True, "1pm-5pm"
    elif 17 <= current_hour < 18:
        return 51, 54 if transfer_switch_status == "From inverter" else 51, False, "5pm-6pm"
    elif 18 <= current_hour < 19:
        return 48, 51 if transfer_switch_status == "From inverter" else 48, False, "6pm-7pm"
    elif 19 <= current_hour < 20:
        return 45, 48 if transfer_switch_status == "From inverter" else 45, False, "7pm-8pm"
    elif 20 <= current_hour < 21:
        return 42, 45 if transfer_switch_status == "From inverter" else 42, False, "8pm-9pm"
    elif 21 <= current_hour < 22:
        return 39, 42 if transfer_switch_status == "From inverter" else 39, False, "9pm-10pm"
    elif 22 <= current_hour < 23:
        return 36, 36, False, "10pm-11pm"
    else:
        return 33, 33, False, "11pm-12pm"

def update_luxpower_max_charge_rate(luxpower_soc):
    """Update Luxpower max charge rate setting based on SOC"""
    if not luxpower_client:
        logger.log_warning("⚠️ Luxpower client not available for max charge rate update")
        return False
    
    if luxpower_soc > 98:
        max_charge_rate = 1 # 1Ah @ 2A = 30 minutes
    elif luxpower_soc > 97:
        max_charge_rate = 4 # 1Ah @ 4A = 15 minutes
    elif luxpower_soc > 95:
        max_charge_rate = 9 # 2Ah @ 9A = ~13 minutes
    elif luxpower_soc > 91:
        max_charge_rate = 16 # 4Ah @ 16A = 15 minutes
    else:
        max_charge_rate = 25 # 92Ah @ 25A = ~221 minutes

    try:
        success = luxpower_client.write_single(101, max_charge_rate)
        if success:
            logger.log_info(f"✅ Luxpower max charge rate updated to {max_charge_rate}A")
            return max_charge_rate
        else:
            logger.log_error(f"❌ Failed to update Luxpower max charge rate to {max_charge_rate}A")
            return False
    except Exception as e:
        logger.log_error(f"❌ Error updating Luxpower max charge rate: {e}")
        return False

def update_luxpower_eod_setting(transfer_switch_status):
    """Update Luxpower Off-Grid EOD setting based on current time"""
    if not luxpower_client:
        logger.log_warning("⚠️ Luxpower client not available for EOD setting update")
        return False
    
    try:
        # Get the correct EOD setting for current time
        target_eod, target_warn, is_increasing, time_period = get_time_based_eod_setting(transfer_switch_status)

        if is_increasing:
            # Write the setting to register 164: Battery warning SOC first, as it must be higher than Off-Grid EOD setting
            success = luxpower_client.write_single(164, target_warn)            
            if success:
                logger.log_info(f"✅ Luxpower Warning SOC setting updated to {target_warn}% ({time_period})")
            else:
                logger.log_error(f"❌ Failed to update Luxpower Warning SOC setting to {target_warn}%")
                return False

        # Write the setting to register 125: Off-Grid EOD setting
        success = luxpower_client.write_single(125, target_eod)
        
        if success:
            logger.log_info(f"✅ Luxpower Off-Grid EOD setting updated to {target_eod}% ({time_period})")
        else:
            logger.log_error(f"❌ Failed to update Luxpower Off-Grid EOD setting to {target_eod}%")
            return False

        if not is_increasing:
            # Write the setting to register 164: Battery warning SOC last, as it must be higher than Off-Grid EOD setting
            success = luxpower_client.write_single(164, target_warn)            
            if success:
                logger.log_info(f"✅ Luxpower Warning SOC setting updated to {target_warn}% ({time_period})")
            else:
                logger.log_error(f"❌ Failed to update Luxpower Warning SOC setting to {target_warn}%")
                return False

        return True

    except Exception as e:
        logger.log_error(f"❌ Error updating Luxpower EOD setting: {e}")
        return False

def write_update_txt(stats, charging_params, messages=None):
    """Write update.txt with inverter and geyser decision information"""
    try:
        # Archive current update.txt to update.log
        with open('stats/update.log', 'a') as log_file, open('stats/update.txt', 'r') as update_file:
            log_file.write('\n')
            log_file.write(update_file.read())
        
        # Write new update.txt
        with open('stats/update.txt', 'w') as f:
            print("TIME", stats['Time'], file=f)
            # Decision messages
            if messages:
                for message in messages:
                    print(message, file=f)
            
    except Exception as e:
        logger.log_error(f"❌ Update.txt write error: {e}")

# Initialize devices
initialize_devices()

# Main loop with three agendas (point 15)
while True:
    iteration_start_time = time.time()
    try:
        # Agenda 1: 10s stats gathering
        gathered_stats = stats_gathering_agenda()
        
        # Agenda 2: 10s monitoring (if geyser is on) - uses cached stats
        if geyser_currently_on:
            geyser_monitoring_loop(gathered_stats)
        
        # Agenda 3: 3-minute decisions (only if stats were gathered)
        if gathered_stats is not None:
            decision_agenda(gathered_stats)
        
        # Calculate elapsed time and adjust sleep
        elapsed_time = time.time() - iteration_start_time
        
        # Sleep for 10s interval, accounting for time already spent
        target_interval = 10  # Always 10s now
        
        remaining_sleep = target_interval - elapsed_time
        if remaining_sleep > 0:
            time.sleep(remaining_sleep)
        else:
            logger.log_warning(f"⚠️ Iteration took {elapsed_time:.2f}s, exceeding target interval of {target_interval}s")
            
    except KeyboardInterrupt:
        logger.log_info("🛑 Shutting down...")
        break
    except Exception as e:
        logger.log_error(f"❌ Main loop error: {e}")
        time.sleep(10)

# Cleanup
if luxpower_client:
    luxpower_client.disconnect()
if geyserwala_client:
    geyserwala_client.disconnect()
axpert.disconnect(dev)

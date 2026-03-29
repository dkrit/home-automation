import requests
import json
import time
from typing import Dict, Optional, Union
import logger

class GeyserwalaClient:
    """Geyserwala Connect REST API Client"""
    
    def __init__(self, host: str, port: int = 80, username: str = None, password: str = None, debug: bool = False):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.debug = debug
        self.base_url = f"http://{host}:{port}"
        self.session = requests.Session()
        self.session.timeout = 10  # 10 second timeout
        self.auth_token = None
    
    def connect(self) -> bool:
        """Connect to the Geyserwala device and authenticate if credentials provided"""
        try:
            # If credentials are provided, authenticate first
            if self.username and self.password:
                if not self._authenticate():
                    return False
            
            # Test connection by getting a simple value
            response = self.session.get(f"{self.base_url}/api/value/status")
            if response.status_code == 200:
                if self.debug:
                    print("✅ Connected to Geyserwala")
                return True
            else:
                if self.debug:
                    print(f"❌ Connection failed: HTTP {response.status_code}")
                return False
        except Exception as e:
            if self.debug:
                print(f"❌ Connection failed: {e}")
            return False
    
    def _authenticate(self) -> bool:
        """Authenticate with the Geyserwala device"""
        try:
            if self.debug:
                print("🔐 Authenticating with Geyserwala...")
            
            auth_data = {
                "username": self.username,
                "password": self.password
            }
            
            response = self.session.post(
                f"{self.base_url}/api/session",
                json=auth_data,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                auth_result = response.json()
                if auth_result.get("success") and "token" in auth_result:
                    self.auth_token = auth_result["token"]
                    # Set the authorization header for future requests
                    self.session.headers.update({
                        'Authorization': f'Bearer {self.auth_token}'
                    })
                    if self.debug:
                        print("✅ Authentication successful")
                    return True
                else:
                    if self.debug:
                        print(f"❌ Authentication failed: {auth_result}")
                    return False
            else:
                if self.debug:
                    print(f"❌ Authentication failed: HTTP {response.status_code}")
                    try:
                        error_data = response.json()
                        print(f"   Error: {error_data}")
                    except:
                        print(f"   Error: {response.text}")
                return False
                
        except Exception as e:
            if self.debug:
                print(f"❌ Authentication error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the Geyserwala device and logout if authenticated"""
        try:
            # If we have an auth token, logout
            if self.auth_token:
                if self.debug:
                    print("🔐 Logging out...")
                self.session.delete(f"{self.base_url}/api/session")
                self.auth_token = None
        except Exception as e:
            if self.debug:
                print(f"⚠️  Logout error: {e}")
        finally:
            if self.session:
                self.session.close()
    
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Union[Dict, str, int, bool]]:
        """Make a REST API request to the Geyserwala device"""
        try:
            url = f"{self.base_url}{endpoint}"
            
            if method.upper() == "GET":
                response = self.session.get(url)
            elif method.upper() == "PATCH":
                response = self.session.patch(url, json=data, headers={'Content-Type': 'application/json'})
            else:
                if self.debug:
                    print(f"❌ Unsupported method: {method}")
                return None
            
            if response.status_code == 200:
                if self.debug:
                    print(f"✅ {method} {endpoint}: {response.status_code}")
                return response.json()
            else:
                if self.debug:
                    print(f"❌ {method} {endpoint}: HTTP {response.status_code}")
                    try:
                        error_data = response.json()
                        print(f"   Error: {error_data}")
                    except:
                        print(f"   Error: {response.text}")
                return None
                
        except Exception as e:
            if self.debug:
                print(f"❌ Request failed: {e}")
            return None
    
    def read_collector_temp(self) -> Optional[int]:
        """Read the collector temperature in Celsius"""
        if self.debug:
            print("📡 Reading collector temperature...")
        
        result = self._make_request("GET", "/api/value/collector-temp")
        if result is not None:
            if self.debug:
                print(f"   Collector temperature: {result}°C")
            return result
        return None
    
    def read_geyser_temp(self) -> Optional[int]:
        """Read the geyser (tank) temperature in Celsius"""
        if self.debug:
            print("📡 Reading geyser temperature...")
        
        result = self._make_request("GET", "/api/value/tank-temp")
        if result is not None:
            if self.debug:
                print(f"   Geyser temperature: {result}°C")
            return result
        return None
    
    def read_element_status(self) -> Optional[bool]:
        """Read the element status (True = On, False = Off)"""
        if self.debug:
            print("📡 Reading element status...")
        
        result = self._make_request("GET", "/api/value/element-demand")
        if result is not None:
            # The API returns boolean values
            status = bool(result)
            if self.debug:
                print(f"   Element status: {'ON' if status else 'OFF'}")
            return status
        return None
    
    def read_external_setpoint(self) -> Optional[int]:
        """Read the external setpoint temperature in Celsius"""
        if self.debug:
            print("📡 Reading external setpoint...")
        
        result = self._make_request("GET", "/api/value/external-setpoint")
        if result is not None:
            if self.debug:
                print(f"   External setpoint: {result}°C")
            return result
        return None
    
    def turn_element_on(self) -> bool:
        """Turn the heating element on"""
        if self.debug:
            print("🔥 Turning element ON...")
        
        # Log the API call
        logger.log_info("🔥 Geyserwala API call - PATCH /api/value with {\"external-demand\": true}")
        
        # Use external-demand to control the element
        data = {"external-demand": True}
        result = self._make_request("PATCH", "/api/value", data)
        
        if result is not None:
            if self.debug:
                print("   ✅ Element turned ON")
            return True
        else:
            if self.debug:
                print("   ❌ Failed to turn element ON")
            return False
    
    def turn_element_off(self) -> bool:
        """Turn the heating element off"""
        if self.debug:
            print("❄️ Turning element OFF...")
        
        # Log the API call
        logger.log_info("❄️ Geyserwala API call - PATCH /api/value with {\"external-demand\": false}")
        
        # Use external-demand to control the element
        data = {"external-demand": False}
        result = self._make_request("PATCH", "/api/value", data)
        
        if result is not None:
            if self.debug:
                print("   ✅ Element turned OFF")
            return True
        else:
            if self.debug:
                print("   ❌ Failed to turn element OFF")
            return False
    
    def set_external_setpoint(self, temperature: int) -> bool:
        """Set the external setpoint temperature in Celsius"""
        if self.debug:
            print(f"🌡️ Setting external setpoint to {temperature}°C...")
        
        # Validate temperature range (typical geyser range: 20-80°C)
        if temperature < 20 or temperature > 80:
            if self.debug:
                print(f"   ❌ Temperature {temperature}°C is out of range (20-80°C)")
            return False
        
        # Log the API call
        logger.log_info(f"🌡️ Geyserwala API call - PATCH /api/value with {{\"external-setpoint\": {temperature}}}")
        
        data = {"external-setpoint": temperature}
        result = self._make_request("PATCH", "/api/value", data)
        
        if result is not None:
            if self.debug:
                print(f"   ✅ External setpoint set to {temperature}°C")
            return True
        else:
            if self.debug:
                print(f"   ❌ Failed to set external setpoint to {temperature}°C")
            return False
    
    def read_all_status(self) -> Optional[Dict]:
        """Read all available status values for debugging/monitoring"""
        if self.debug:
            print("📡 Reading all status values...")
        
        # Get multiple values at once
        result = self._make_request("GET", "/api/value?f=status,mode,setpoint,boost-demand,element-demand,tank-temp,collector-temp,pump-status,external-setpoint,external-demand,external-disable")
        
        if result is not None:
            if self.debug:
                print("   Status values:")
                for key, value in result.items():
                    print(f"     {key}: {value}")
            return result
        return None

def main():
    """Test the Geyserwala client"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Geyserwala Connect REST API Client')
    parser.add_argument('--host', default='192.168.1.94', help='Geyserwala device IP address')
    parser.add_argument('--port', type=int, default=80, help='Geyserwala device port (default: 80)')
    parser.add_argument('--username', default='admin', help='Username for authentication (optional)')
    parser.add_argument('--password', default='pwd', help='Password for authentication (optional)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--element', choices=['on', 'off', 'status'], default='status', 
                       help='Control element: on (turn on), off (turn off), status (read only, default)')
    parser.add_argument('--setpoint', type=int, help='Set external setpoint temperature (20-80°C)')
    parser.add_argument('--read-setpoint', action='store_true', help='Read current external setpoint')
    
    args = parser.parse_args()
    
    # Create client
    client = GeyserwalaClient(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        debug=args.debug
    )
    
    try:
        # Test connection
        if not client.connect():
            print("❌ Failed to connect to Geyserwala device")
            return 1
        
        # Handle setpoint operations first
        if args.setpoint is not None:
            print(f"\n=== Setting External Setpoint to {args.setpoint}°C ===")
            success = client.set_external_setpoint(args.setpoint)
            if success:
                print(f"✅ External setpoint set to {args.setpoint}°C successfully")
            else:
                print(f"❌ Failed to set external setpoint to {args.setpoint}°C")
                return 1
        
        if args.read_setpoint:
            print("\n=== Reading External Setpoint ===")
            setpoint = client.read_external_setpoint()
            if setpoint is not None:
                print(f"✅ Current external setpoint: {setpoint}°C")
            else:
                print("❌ Failed to read external setpoint")
                return 1
        
        # Test all functions
        print("\n=== Testing Geyserwala API ===")
        
        # Read temperatures
        collector_temp = client.read_collector_temp()
        geyser_temp = client.read_geyser_temp()
        
        # Handle element control
        if args.element == 'on':
            print("\n=== Turning Element ON ===")
            success = client.turn_element_on()
            if success:
                print("✅ Element turned ON successfully")
            else:
                print("❌ Failed to turn element ON")
                return 1
        elif args.element == 'off':
            print("\n=== Turning Element OFF ===")
            success = client.turn_element_off()
            if success:
                print("✅ Element turned OFF successfully")
            else:
                print("❌ Failed to turn element OFF")
                return 1
        
        # Read element status (for all modes)
        element_status = client.read_element_status()
        
        # Read external setpoint if not already read
        if not args.read_setpoint:
            external_setpoint = client.read_external_setpoint()
        else:
            external_setpoint = None
        
        # Read all status for debugging
        all_status = client.read_all_status()
        
        print(f"\n=== Results ===")
        print(f"Collector temperature: {collector_temp}°C" if collector_temp is not None else "Collector temperature: Failed")
        print(f"Geyser temperature: {geyser_temp}°C" if geyser_temp is not None else "Geyser temperature: Failed")
        print(f"Element status: {'ON' if element_status else 'OFF'}" if element_status is not None else "Element status: Failed")
        if external_setpoint is not None:
            print(f"External setpoint: {external_setpoint}°C")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️  Operation interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1
    finally:
        client.disconnect()

if __name__ == '__main__':
    exit(main())

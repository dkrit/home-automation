
import socket
import struct
import time
import argparse
import json
import copy
from typing import Dict, Optional

class Serial:
    """Represents a 10-byte serial number used in the protocol"""
    def __init__(self, data: bytes):
        if len(data) != 10:
            raise ValueError("Serial must be exactly 10 bytes")
        self.data = data
    
    def __str__(self):
        return self.data.decode('ascii', errors='replace')
    
    @classmethod
    def from_string(cls, s: str):
        if len(s) != 10:
            raise ValueError("Serial string must be exactly 10 characters")
        return cls(s.encode('ascii'))

class LuxPowerClient:
    """LuxPower Inverter Communication Client - Protocol Version 1 Only"""
    
    def __init__(self, host: str, port: int = 8000, datalog_serial: str = "DG51406871", 
                 inverter_serial: str = "51831V0671", debug: bool = False):
        self.host = host
        self.port = port
        self.datalog = Serial.from_string(datalog_serial)
        self.inverter = Serial.from_string(inverter_serial)
        self.debug = debug
        self.socket = None
        # Cache last valid reading for use when a reading is invalid (e.g. comms glitch)
        self._last_valid_reading: Optional[Dict] = None
    
    def connect(self) -> bool:
        """Connect to the inverter and wait for initial packet"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(30.0)
            self.socket.connect((self.host, self.port))
            
            if self.debug:
                print("✅ Connected to inverter")
                print("Waiting for initial packet...")
            
            # Wait for initial packet from inverter
            initial_packet = self.socket.recv(4096)
            if initial_packet:
                if self.debug:
                    self._print_hex_dump(initial_packet, "Initial Packet from Inverter")
                return True
            else:
                print("❌ No initial packet received")
                return False
                
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the inverter"""
        if self.socket:
            self.socket.close()
            self.socket = None
    
    def _calculate_checksum(self, data: bytes) -> bytes:
        """CRC-16/MODBUS checksum calculation"""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return struct.pack('<H', crc)
    
    def _build_tcp_frame(self, tcp_function: int, data: bytes) -> bytes:
        """Build a TCP frame - following original projects exactly"""
        data_length = len(data)
        frame_length = 18 + data_length
        
        frame = bytearray(frame_length)
        
        # Header - exactly like original projects
        frame[0] = 161  # 0xA1
        frame[1] = 26   # 0x1A
        frame[2:4] = struct.pack('<H', 1)  # Protocol version 1
        frame[4:6] = struct.pack('<H', frame_length - 6)  # Frame length
        frame[6] = 1  # Unknown field, always 1
        frame[7] = tcp_function
        
        # Datalog serial (10 bytes)
        frame[8:18] = self.datalog.data
        
        # Data section
        frame[18:] = data
        
        return bytes(frame)
    
    def _build_translated_data(self, device_function: int, register: int, value: int = None, 
                              register_count: int = 1) -> bytes:
        """Build TranslatedData packet - following original projects exactly"""
        data = bytearray()
        
        # Data length field (2 bytes) - will be updated
        data.extend(b'\x00\x00')
        
        # Not sure what this is for
        data.append(0)
        
        # Device function
        data.append(device_function)
        
        # Inverter serial (10 bytes)
        # For ReadInput operations, use zero bytes instead of inverter serial
        if device_function == 4:  # ReadInput
            data.extend(b'\x00' * 10)
        else:
            data.extend(self.inverter.data)
        
        # Register (2 bytes, little endian)
        data.extend(struct.pack('<H', register))
        
        # Add register count if more than 1 (for multi-register reads)
        if register_count > 1:
            data.extend(struct.pack('<H', register_count))
        
        # Add value for write operations
        if value is not None:
            data.extend(struct.pack('<H', value))
        
        # Calculate checksum on data[2:] (excluding data_length field)
        checksum_data = data[2:]
        checksum = self._calculate_checksum(checksum_data)
        data.extend(checksum)
        
        # Update data length (excluding the length field itself)
        # The data length should be the total data section length minus the data_length field itself
        data_length = len(data) - 2  # Exclude data_length field (2 bytes)
        data[0:2] = struct.pack('<H', data_length)
        
        return bytes(data)
    
    def _print_hex_dump(self, data: bytes, title: str = "Hex Dump", max_bytes: int = 2000) -> None:
        """Print a detailed hex dump of data, split into header and data sections"""
        print(f"\n=== {title.upper()} ===")
        print(f"Length: {len(data)} bytes")
        
        # Split into header and data sections
        if len(data) >= 18:
            header_data = data[:18]
            data_section = data[18:]
            
            # Print header section
            self._print_hex_section(header_data, "Header", 0)
            
            # Print data section if it exists
            if len(data_section) > 0:
                self._print_hex_section(data_section, "Data Section", 18)
        else:
            # If too short, print as single section
            self._print_hex_section(data, "Complete Packet", 0)
    
    def _print_hex_section(self, data: bytes, section_name: str, start_offset: int, max_bytes: int = 2000) -> None:
        """Print a hex dump section with 10 u16 values per line"""
        print(f"\n--- {section_name.upper()} ---")
        print(f"Length: {len(data)} bytes, Offset: {start_offset}")
        print(f"{'='*140}")
        print(f"{'Offset':>6} | {'HEX':<29} | {'Dec':<39} | {'ASCII':>10} | {'u16 (10 values)':<50} | {'Field':<15}")
        print(f"{'='*140}")
        
        # Process data in chunks of 10 bytes
        data_to_show = data[:max_bytes]
        for i in range(0, len(data_to_show), 10):
            chunk = data_to_show[i:i+10]
            global_offset = start_offset + i
            offset_str = f"{global_offset:4d}"
            
            # Add field annotation based on global offset
            field_annotation = self._get_field_annotation(global_offset)
            
            # HEX column (3 chars per byte: "XX ")
            hex_values = [f'{b:02x}' for b in chunk]
            # Pad to exactly 10 values
            while len(hex_values) < 10:
                hex_values.append('  ')
            hex_str = ' '.join(hex_values)
            
            # Dec column (4 chars per byte: "XXX ")
            dec_values = [f'{b:3d}' for b in chunk]
            # Pad to exactly 10 values
            while len(dec_values) < 10:
                dec_values.append('   ')
            dec_str = ' '.join(dec_values)
            
            # ASCII column (1 char per byte)
            ascii_values = [chr(b) if 32 <= b <= 126 else '.' for b in chunk]
            # Pad to exactly 10 values
            while len(ascii_values) < 10:
                ascii_values.append(' ')
            ascii_str = ''.join(ascii_values)
            
            # u16 column - 10 u16 values per line (every byte as starting point)
            u16_values = []
            for j in range(len(chunk)):
                if j + 1 < len(chunk):
                    # Little-endian u16 starting at byte j within current chunk
                    u16_val = struct.unpack('<H', chunk[j:j+2])[0]
                    u16_values.append(f'{u16_val:5d}')
                elif j == len(chunk) - 1 and i + j + 1 < len(data_to_show):
                    # Last byte of current chunk, use first byte of next chunk
                    next_chunk_start = i + 10
                    if next_chunk_start < len(data_to_show):
                        u16_val = struct.unpack('<H', chunk[j:j+1] + data_to_show[next_chunk_start:next_chunk_start+1])[0]
                        u16_values.append(f'{u16_val:5d}')
                    else:
                        u16_values.append('     ')
                else:
                    # Last byte, pad with spaces
                    u16_values.append('     ')
            
            # Pad to exactly 10 u16 values
            while len(u16_values) < 10:
                u16_values.append('     ')
            u16_str = ' '.join(u16_values)
            
            print(f"{offset_str:>6} | {hex_str} | {dec_str} | {ascii_str} | {u16_str} | {field_annotation}")
        
        if len(data) > max_bytes:
            print(f"... (truncated, showing first {max_bytes} of {len(data)} bytes)")
        print(f"{'='*140}")
    
    def _get_field_annotation(self, offset: int) -> str:
        """Get field annotation based on offset"""
        if offset == 0:
            return "Magic"
        elif offset == 2:
            return "Protocol"
        elif offset == 4:
            return "Frame Length"
        elif offset == 6:
            return "Unknown"
        elif offset == 7:
            return "TCP Function"
        elif offset == 8:
            return "Datalog Serial"
        elif offset == 18:
            return "Data Length"
        elif offset == 19:
            return "Address"
        elif offset == 20:
            return "Device Function"
        elif offset == 21:
            return "Inverter Serial"
        elif offset >= 18:
            return "Data"
        else:
            return ""
    
    def send_request(self, device_function: int, tcp_function: int, register: int = 0, 
                    value: int = None, register_count: int = 1) -> Optional[bytes]:
        """Send a request to the inverter and return the response"""
        if not self.socket:
            print("❌ Not connected to inverter")
            return None
        
        try:
            # Build the request using Protocol Version 1
            data = self._build_translated_data(device_function, register, value, register_count)
            packet = self._build_tcp_frame(tcp_function, data)
            
            if self.debug:
                self._print_hex_dump(packet, "Request Packet")
            
            # Send the request
            self.socket.send(packet)
            
            if self.debug:
                print("✅ Request sent, waiting for response...")
            
            # Wait for response
            time.sleep(0.5)  # Give the inverter time to process
            response = self.socket.recv(4096)
            
            if response:
                if self.debug:
                    self._print_hex_dump(response, "Response Packet")
                return response
            else:
                print("❌ No response received")
                return None
                
        except Exception as e:
            print(f"❌ Error sending request: {e}")
            return None
    
    def read_input(self, register: int = 0, register_count: int = 1) -> Optional[Dict]:
        """Read input data from a register"""
        response = self.send_request(4, 194, register, register_count=register_count)  # ReadInput, TranslatedData
        
        if not response:
            return None
        
        # Parse the response
        if len(response) < 20:
            print("❌ Invalid response length")
            return None
        
        # Extract data section
        data_section = response[18:]
        if len(data_section) < 16:
            print("❌ Invalid data section length")
            return None
        
        # Parse the data section
        data_length = struct.unpack('<H', data_section[0:2])[0]
        address = data_section[2]
        device_function = data_section[3]
        inverter_serial = data_section[4:14]
        register_resp = struct.unpack('<H', data_section[14:16])[0]
        values = data_section[17:-2]
        checksum = data_section[-2:]
        
        # Verify checksum
        checksum_data = data_section[2:-2]
        calculated_checksum = self._calculate_checksum(checksum_data)
        checksum_match = checksum == calculated_checksum
        
        if self.debug:
            print(f"Response Analysis:")
            print(f"  Data length: {data_length}")
            print(f"  Address: {address}")
            print(f"  Device function: {device_function}")
            print(f"  Inverter serial: {inverter_serial.decode('ascii', errors='replace')}")
            print(f"  Register: {register_resp}")
            print(f"  Values: {len(values)} bytes")
            print(f"  Checksum: {checksum.hex()}")
            print(f"  Checksum match: {'✅' if checksum_match else '❌'}")
        
        # Parse the values into meaningful JSON based on register type
        parsed_data = self._parse_read_input_values(register_resp, values)
        
        return {
            "register": register_resp,
            "data_length": data_length,
            "checksum_valid": checksum_match,
            "data": parsed_data,
            "raw_values": values,  # Include raw values for combination
            "raw_values_hex": values.hex()  # Include hex representation for JSON serialization
        }
    
    def _is_reading_valid(self, result: Dict) -> bool:
        """Return True if the reading looks valid (not a comms glitch).
        Checks: AC voltage ~44-55V; PV total power <= 6000 W; SOC not 0% when previous was >30%."""
        if not result or "data" not in result:
            return False
        parsed = result.get("data") or {}
        # AC voltage: normal range ~44-55 V; allow 30-60 for margin
        ac = parsed.get("ac_voltage") or {}
        r = ac.get("phase_r") or 0
        s = ac.get("phase_s") or 0
        t = ac.get("phase_t") or 0
        MIN_V, MAX_V = 30.0, 60.0
        voltage_ok = (MIN_V <= r <= MAX_V) or (MIN_V <= s <= MAX_V) or (MIN_V <= t <= MAX_V)
        if not voltage_ok:
            return False
        # PV power: equipment ~3600 W max, occasional spike to ~5000; reject e.g. 25000 W glitches
        pv = parsed.get("pv_power") or {}
        pv_total = pv.get("total") or 0
        if pv_total > 6000:
            return False
        # SOC: 0% can be valid (empty battery) or a glitch. If previous reading was >30% and current is 0%, treat as bad.
        soc = (parsed.get("battery") or {}).get("soc")
        if soc is not None and soc == 0 and self._last_valid_reading:
            prev = (self._last_valid_reading.get("data") or {}).get("battery") or {}
            prev_soc = prev.get("soc")
            if prev_soc is not None and prev_soc > 30:
                return False
        return True
    
    def read_input_complete(self) -> Optional[Dict]:
        """Read complete input data by making two requests (registers 0-126 and 127-253)"""
        print("📡 Reading complete input data (two requests)...")
        
        # First request: registers 0-126 (127 registers)
        print("  📡 Request 1: registers 0-126...")
        response1 = self.read_input(0, 127)
        if not response1:
            print("❌ First request failed")
            return None
        
        # Second request: registers 127-253 (127 registers)  
        print("  📡 Request 2: registers 127-253...")
        response2 = self.read_input(127, 127)
        if not response2:
            print("❌ Second request failed")
            return None
        
        # Extract raw values from both responses
        raw_values1 = response1.get("raw_values", b"")
        raw_values2 = response2.get("raw_values", b"")
        
        if not raw_values1 or not raw_values2:
            print("❌ Failed to extract raw values from responses")
            return None
        
        # Combine the raw data (254 bytes + 254 bytes = 508 bytes total)
        combined_values = raw_values1 + raw_values2
        
        print(f"  ✅ Combined data: {len(combined_values)} bytes")
        
        # Parse the combined data
        parsed_data = self._parse_all_readinput_fields(combined_values)
        
        result = {
            "type": "ReadInputComplete",
            "description": "Complete inverter data from two requests (508 bytes)",
            "data_length": len(combined_values),
            "checksum_valid": response1["checksum_valid"] and response2["checksum_valid"],
            "data": parsed_data
        }
        # If reading looks like a comms glitch (e.g. all zeros), use last valid reading
        if not self._is_reading_valid(result):
            if self._last_valid_reading:
                if self.debug:
                    print("  ⚠️  Current reading invalid (e.g. voltage out of range); using last valid reading")
                out = copy.deepcopy(self._last_valid_reading)
                out["reading_cached"] = True
                return out
            # No cache; return current result but mark as invalid
            result["reading_cached"] = False
            result["reading_invalid"] = True
            return result
        self._last_valid_reading = copy.deepcopy(result)
        result["reading_cached"] = False
        return result

    def read_input_complete_3_pages(self) -> Optional[Dict]:
        """Read complete input data by making three requests (registers 0-126, 127-253, and 254-319)"""
        print("📡 Reading complete input data (three requests)...")
        
        # First request: registers 0-126 (127 registers)
        print("  📡 Request 1: registers 0-126...")
        response1 = self.read_input(0, 127)
        if not response1:
            print("❌ First request failed")
            return None
        
        # Second request: registers 127-253 (127 registers)  
        print("  📡 Request 2: registers 127-253...")
        response2 = self.read_input(127, 127)
        if not response2:
            print("❌ Second request failed")
            return None
        
        # Third request: registers 254-319 (66 registers)
        print("  📡 Request 3: registers 254-319...")
        response3 = self.read_input(254, 66)
        if not response3:
            print("❌ Third request failed")
            return None
        
        # Extract raw values from all three responses
        raw_values1 = response1.get("raw_values", b"")
        raw_values2 = response2.get("raw_values", b"")
        raw_values3 = response3.get("raw_values", b"")
        
        if not raw_values1 or not raw_values2 or not raw_values3:
            print("❌ Failed to extract raw values from responses")
            return None
        
        # Combine the raw data (254 + 254 + 132 = 640 bytes total)
        combined_values = raw_values1 + raw_values2 + raw_values3
        
        print(f"  ✅ Combined data: {len(combined_values)} bytes")
        
        # Parse the combined data
        parsed_data = self._parse_all_readinput_fields(combined_values)
        
        result = {
            "type": "ReadInputComplete3Pages",
            "description": "Complete inverter data from three requests (640 bytes)",
            "data_length": len(combined_values),
            "checksum_valid": response1["checksum_valid"] and response2["checksum_valid"] and response3["checksum_valid"],
            "data": parsed_data
        }
        # If reading looks like a comms glitch (e.g. all zeros), use last valid reading
        if not self._is_reading_valid(result):
            if self._last_valid_reading:
                if self.debug:
                    print("  ⚠️  Current reading invalid (e.g. voltage out of range); using last valid reading")
                out = copy.deepcopy(self._last_valid_reading)
                out["reading_cached"] = True
                return out
            # No cache; return current result but mark as invalid
            result["reading_cached"] = False
            result["reading_invalid"] = True
            return result
        self._last_valid_reading = copy.deepcopy(result)
        result["reading_cached"] = False
        return result
    
    def _parse_read_input_values(self, register: int, values: bytes) -> Dict:
        """Parse ReadInput values into comprehensive JSON with all known fields"""
        
        if len(values) < 80:
            return {
                "type": "ReadInput",
                "description": "Insufficient data for parsing",
                "error": f"Need at least 80 bytes, got {len(values)}",
                "raw_data": values.hex()
            }
        
        # Parse all known fields directly from their offsets
        return self._parse_all_readinput_fields(values)
    
    def _parse_all_readinput_fields(self, values: bytes) -> Dict:
        """Parse all ReadInput fields directly from their known offsets"""
        try:
            # Helper functions with bounds checking
            def read_u16(offset: int) -> int:
                if offset + 2 > len(values):
                    return 0  # Return 0 for missing data
                return struct.unpack('<H', values[offset:offset + 2])[0]
            
            def read_i8(offset: int) -> int:
                if offset + 1 > len(values):
                    return 0  # Return 0 for missing data
                return struct.unpack('b', values[offset:offset + 1])[0]
            
            def read_u32(offset: int) -> int:
                if offset + 4 > len(values):
                    return 0  # Return 0 for missing data
                return struct.unpack('<I', values[offset:offset + 4])[0]
            
            # Build comprehensive result with all known fields
            result = {
                "type": "ReadInput",
                "description": "Complete inverter status and measurements",
                
                # Basic system status (offsets 0-12)
                "status": read_u16(0),
                "internal_fault": read_u16(12),
                
                # PV voltages (offsets 2-6)
                "pv_voltage": {
                    "string_1": read_u16(2) / 10.0,  # V
                    "string_2": read_u16(4) / 10.0,  # V
                    "string_3": read_u16(6) / 10.0   # V
                },
                
                # Battery data (offsets 8-11)
                "battery": {
                    "voltage": read_u16(8) / 10.0,   # V
                    "soc": read_i8(10),              # %
                    "soh": read_i8(11)               # %
                },
                
                # PV power (offsets 14-18)
                "pv_power": {
                    "total": read_u16(14) + read_u16(16) + read_u16(18),  # W
                    "string_1": read_u16(14),  # W
                    "string_2": read_u16(16),  # W
                    "string_3": read_u16(18)   # W
                },
                
                # Battery power (offsets 20-22)
                "battery_power": {
                    "charge": read_u16(20),     # W
                    "discharge": read_u16(22)   # W
                },
                
                # AC voltage and frequency (offsets 24-30)
                "ac_voltage": {
                    "phase_r": read_u16(24) / 10.0,  # V
                    "phase_s": read_u16(26) / 10.0,  # V
                    "phase_t": read_u16(28) / 10.0   # V
                },
                "ac_frequency": read_u16(30) / 100.0,  # Hz
                
                # Inverter power (offsets 32-34)
                "inverter_power": {
                    "inverter": read_u16(32),   # W
                    "rectifier": read_u16(34)   # W
                },
                
                # Power factor (offset 36)
                "power_factor": read_u16(36) / 1000.0,
                
                # EPS voltage and frequency (offsets 38-44)
                "eps_voltage": {
                    "phase_r": read_u16(38) / 10.0,  # V
                    "phase_s": read_u16(40) / 10.0,  # V
                    "phase_t": read_u16(42) / 10.0   # V
                },
                "eps_frequency": read_u16(44) / 100.0,  # Hz
                
                # Grid power (offsets 46-48)
                "grid_power": {
                    "inverter_capacity": read_u16(46),    # W - Inverter's maximum capacity/supply to loads
                    "current_output": read_u16(48)     # W - Current output power being supplied to loads
                },
                
                   # Daily energy (offsets 50-68)
                   "daily_energy": {
                       "pv_total": (read_u16(50) + read_u16(52) + read_u16(54)) / 10.0,  # kWh - Total PV energy today
                       "pv_string_1": read_u16(50) / 10.0,  # kWh
                       "pv_string_2": read_u16(52) / 10.0,  # kWh
                       "pv_string_3": read_u16(54) / 10.0,  # kWh
                       "inverter": read_u16(56) / 10.0,     # kWh
                       "rectifier": read_u16(58) / 10.0,    # kWh
                       "battery_charge": read_u16(60) / 10.0,       # kWh - Total battery charge today
                       "battery_discharge": read_u16(62) / 10.0,    # kWh - Total battery discharge today
                       "eps": read_u16(64) / 10.0,          # kWh
                       "to_grid": read_u16(66) / 10.0,      # kWh
                       "to_user": read_u16(68) / 10.0       # kWh
                   },
                
                # Daily consumption/loads (offsets 70-72)
                "daily_consumption": {
                    "total_loads": read_u16(70) / 10.0,  # kWh - Daily total consumption/loads
                    "bus_2": read_u16(72) / 10.0   # V - Unknown field
                }
            }
            
            # Add total energy fields (offsets 80-159 for ReadInput2 section)
            if len(values) >= 160:
                result["total_energy"] = {
                    "pv_total": (read_u32(80) + read_u32(84) + read_u32(88)) / 10.0,  # kWh
                    "pv_string_1": read_u32(80) / 10.0,  # kWh
                    "pv_string_2": read_u32(84) / 10.0,  # kWh
                    "pv_string_3": read_u32(88) / 10.0,  # kWh
                    "inverter": read_u32(92) / 10.0,     # kWh
                    "rectifier": read_u32(96) / 10.0,    # kWh
                    "battery_charge": read_u32(100) / 10.0,      # kWh - Total battery charge lifetime
                    "battery_discharge": read_u32(104) / 10.0,   # kWh - Total battery discharge lifetime
                    "eps": read_u32(108) / 10.0,         # kWh
                    "to_grid": read_u32(112) / 10.0,     # kWh
                    "to_user": read_u32(116) / 10.0      # kWh
                }
                
                # Add fault codes (offsets 120-128)
                result["faults"] = {
                    "fault_code": read_u32(120),     # System fault code
                    "warning_code": read_u32(124)    # System warning code
                }
                
                # Add temperatures (offsets 128-144)
                result["temperatures"] = {
                    "internal": read_u16(128),       # °C
                    "radiator_1": read_u16(130),     # °C
                    "radiator_2": read_u16(132),     # °C
                    "battery": read_u16(134),        # °C
                    "radiator_3": read_u16(136)      # °C
                }
                
                # Add runtime (offset 144)
                result["runtime"] = read_u32(144)  # seconds
            
            # Add battery management fields (offsets 160-239 for ReadInput3 section)
            if len(values) >= 240:
                result["battery_config"] = {
                    "max_charge_current": read_u16(162) / 100.0,    # A
                    "max_discharge_current": read_u16(164) / 100.0, # A
                    "charge_voltage_ref": read_u16(166) / 10.0,     # V
                    "discharge_cutoff_voltage": read_u16(168) / 10.0 # V
                }
                
                result["battery_status"] = {
                    "status_0": read_u16(170),
                    "status_1": read_u16(172),
                    "status_2": read_u16(174),
                    "status_3": read_u16(176),
                    "status_4": read_u16(178),
                    "status_5": read_u16(180),
                    "status_6": read_u16(182),
                    "status_7": read_u16(184),
                    "status_8": read_u16(186),
                    "status_9": read_u16(188),
                    "status_inverter": read_u16(190)
                }
                
                result["battery_count"] = read_u16(192)
            
            # Add generator and EPS fields (offsets 240-253 for ReadInput4 section - limited data)
            if len(values) >= 254:
                result["generator"] = {
                    "voltage": read_u16(242) / 10.0,     # V (skip first 2 bytes)
                    "frequency": read_u16(244) / 100.0,  # Hz
                    "power": read_u16(246),              # W
                    "daily_energy": read_u16(248) / 10.0, # kWh
                    "total_energy": read_u32(250) / 10.0  # kWh
                }
                
                # Note: EPS data would start at offset 254, but we only have 14 bytes total in ReadInput4
                # So we can't parse full EPS data in ReadInputAll mode
                result["eps"] = {
                    "note": "Insufficient data for EPS fields in ReadInputAll mode (only 14 bytes available)"
                }
            
            # Add complete EPS fields if we have the full 640 bytes (from three requests)
            if len(values) >= 640:
                # EPS data starts at offset 254 in the first 254 bytes, then continues in the second 254 bytes
                result["eps"] = {
                    "voltage_l1": read_u16(254) / 10.0,   # V
                    "voltage_l2": read_u16(256) / 10.0,   # V
                    "power_l1": read_u16(258),            # W
                    "power_l2": read_u16(260),            # W
                    "apparent_power_l1": read_u16(262),   # VA
                    "apparent_power_l2": read_u16(264),   # VA
                    "daily_energy_l1": read_u16(266) / 10.0,  # kWh
                    "daily_energy_l2": read_u16(268) / 10.0,  # kWh
                    "total_energy_l1": read_u32(270) / 10.0,  # kWh
                    "total_energy_l2": read_u32(274) / 10.0   # kWh
                }
                
                # Additional data from the third request (registers 254-319)
                additional_bytes = values[508:] if len(values) > 508 else b""
                result["additional_data"] = {
                    "note": f"Additional data from registers 254-319 ({len(additional_bytes)} bytes)",
                    "raw_data_length": len(additional_bytes),
                    "raw_hex": additional_bytes.hex() if additional_bytes else "",
                    "non_zero_bytes": [i for i, b in enumerate(additional_bytes) if b != 0] if additional_bytes else []
                }
            elif len(values) >= 508:
                # Partial EPS data from two requests (508 bytes)
                result["eps"] = {
                    "voltage_l1": read_u16(254) / 10.0,   # V
                    "voltage_l2": read_u16(256) / 10.0,   # V
                    "power_l1": read_u16(258),            # W
                    "power_l2": read_u16(260),            # W
                    "apparent_power_l1": read_u16(262),   # VA
                    "apparent_power_l2": read_u16(264),   # VA
                    "daily_energy_l1": read_u16(266) / 10.0,  # kWh
                    "daily_energy_l2": read_u16(268) / 10.0,  # kWh
                    "total_energy_l1": read_u32(270) / 10.0,  # kWh
                    "total_energy_l2": read_u32(274) / 10.0,  # kWh
                    "note": "Complete EPS data from two requests (508 bytes)"
                }
                
                # Additional data from the second request (registers 127-253)
                result["additional_data"] = {
                    "note": f"Additional data from registers 127-253 ({len(values) - 254} bytes)",
                    "raw_data_length": len(values) - 254
                }
            
            return result
            
        except (IndexError, struct.error) as e:
            return {
                "type": "ReadInput",
                "description": "Complete inverter status and measurements",
                "error": f"Parsing error: {str(e)}",
                "data_length": len(values),
                "raw_data": values.hex()
            }
    
    
    # ChargePowerPercentCmd = 64,  // System Charge Rate (%)
    # DischgPowerPercentCmd = 65,  // System Discharge Rate (%)
    # AcChargePowerCmd = 66,       // Grid Charge Power Rate (%)
    # AcChargeSocLimit = 67,       // AC Charge SOC Limit (%)
    # ChargePriorityPowerCmd = 74, // Charge Priority Charge Rate (%)
    # ChargePrioritySocLimit = 75, // Charge Priority SOC Limit (%)
    # ForcedDischgSocLimit = 83,   // Forced Discarge SOC Limit (%)
    # DischgCutOffSocEod = 105,    // Discharge cut-off SOC (%)
    # EpsDischgCutoffSocEod = 125, // EPS Discharge cut-off SOC (%)
    # AcChargeStartSocLimit = 160, // SOC at which AC charging will begin (%)
    # AcChargeEndSocLimit = 161,   // SOC at which AC charging will end (%)
    def read_hold(self, register: int, register_count: int = 2) -> Optional[int]:
        """Read hold data from a register"""
        response = self.send_request(3, 194, register, register_count=register_count)  # ReadHold, TranslatedData
        
        if not response:
            return None
        
        # Parse the response
        if len(response) < 20:
            print("❌ Invalid response length")
            return None
        
        # Extract data section
        data_section = response[18:]
        if len(data_section) < 16:
            print("❌ Invalid data section length")
            return None
        
        # Parse the data section
        data_length = struct.unpack('<H', data_section[0:2])[0]
        address = data_section[2]
        device_function = data_section[3]
        inverter_serial = data_section[4:14]
        register_resp = struct.unpack('<H', data_section[14:16])[0]
        # byte 16 is the length of the values
        values_length = data_section[16]
        values = data_section[17:-2]
        checksum = data_section[-2:]
        
        # Verify checksum
        checksum_data = data_section[2:-2]
        calculated_checksum = self._calculate_checksum(checksum_data)
        checksum_match = checksum == calculated_checksum
        
        if self.debug:
            print(f"Response Analysis:")
            print(f"  Data length: {data_length}")
            print(f"  Address: {address}")
            print(f"  Device function: {device_function}")
            print(f"  Inverter serial: {inverter_serial.decode('ascii', errors='replace')}")
            print(f"  Register: {register_resp}")
            print(f"  Values: {len(values)} bytes")
            print(f"  Checksum: {checksum.hex()}")
            print(f"  Checksum match: {'✅' if checksum_match else '❌'}")
        
        if not checksum_match:
            print("⚠️  Checksum verification failed")
            return None
        
        # Extract the value (assuming it's a single 16-bit value)
        if len(values) >= 2:
            value = struct.unpack('<H', values[0:2])[0]
            return value
        else:
            print("❌ No value data in response")
            return None
    
    def write_single(self, register: int, value: int) -> bool:
        """Write a single value to a register"""
        response = self.send_request(6, 194, register, value)  # WriteSingle, TranslatedData
        
        if not response:
            return False
        
        # For write operations, we just need to check if we got a response
        # The inverter should echo back the same packet for WriteSingle
        if len(response) > 0:
            if self.debug:
                print("✅ Write operation completed successfully")
            return True
        else:
            print("❌ Write operation failed")
            return False

def main():
    parser = argparse.ArgumentParser(description='LuxPower Inverter Communication Client - Protocol Version 1 Only')
    
    # Connection parameters
    parser.add_argument('--host', default='192.168.1.177', help='Inverter IP address')
    parser.add_argument('--port', type=int, default=8000, help='Inverter port (default: 8000)')
    parser.add_argument('--datalog-serial', default='DG51406871', help='Datalog serial (default: DG51406871)')
    parser.add_argument('--inverter-serial', default='51831V0671', help='Inverter serial (default: 51831V0671)')
    
    # Operation parameters
    parser.add_argument('--device-function', type=int, choices=[3, 4, 6], required=True, 
                       help='Device function (3=ReadHold, 4=ReadInput, 6=WriteSingle)')
    parser.add_argument('--tcp-function', type=int, choices=[194, 195, 196], default=194, 
                       help='TCP function (194=TranslatedData, 195=ReadParam, 196=WriteParam)')
    parser.add_argument('--register', type=int, default=0, help='Register number (default: 0)')
    parser.add_argument('--register-count', type=int, help='Register count (default: 320 for ReadInput, 127 for ReadHold)')
    parser.add_argument('--write-value', type=int, help='Value to write (required for WriteSingle)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output with hex dumps')
    
    args = parser.parse_args()
    
    # Set default register count based on device function
    if args.register_count is None:
        if args.device_function == 4:  # ReadInput
            args.register_count = 320  # 160 registers = 320 bytes (complete dataset)
        elif args.device_function == 3:  # ReadHold
            args.register_count = 2
        else:  # ReadHold or WriteSingle
            args.register_count = 127
    
    # Validate arguments
    if args.device_function == 6 and args.write_value is None:
        print("❌ --write-value is required for WriteSingle operations")
        return 1
    
    # Create client
    client = LuxPowerClient(
        host=args.host,
        port=args.port,
        datalog_serial=args.datalog_serial,
        inverter_serial=args.inverter_serial,
        debug=args.debug
    )
    
    try:
        # Connect to inverter
        if not client.connect():
            return 1
        
        # Perform the requested operation
        if args.device_function == 4:  # ReadInput
            if args.register_count >= 128:
                # Use multiple requests for complete dataset
                if args.register_count > 254:
                    # Use 3 requests for complete dataset (registers 0-126, 127-253, 254-319)
                    result = client.read_input_complete_3_pages()
                else:
                    # Use 2 requests for partial dataset (registers 0-126, 127-253)
                    result = client.read_input_complete()
                
                if result:
                    print(json.dumps(result, indent=2))
                else:
                    print("❌ ReadInputComplete failed")
                    return 1
            else:
                # Use single request for partial dataset
                result = client.read_input(args.register, args.register_count)
                if result:
                    # Remove raw_values for JSON serialization
                    json_result = {k: v for k, v in result.items() if k != 'raw_values'}
                    print(json.dumps(json_result, indent=2))
                else:
                    print("❌ ReadInput failed")
                    return 1
                
        elif args.device_function == 3:  # ReadHold
            result = client.read_hold(args.register, args.register_count)
            if result is not None:
                print(f"Register {args.register}: {result}")
            else:
                print("❌ ReadHold failed")
                return 1
                
        elif args.device_function == 6:  # WriteSingle
            success = client.write_single(args.register, args.write_value)
            if success:
                print("OK")
            else:
                print("❌ WriteSingle failed")
                return 1
        
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

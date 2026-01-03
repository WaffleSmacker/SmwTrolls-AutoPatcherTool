"""
BPS (Beat Patch System) patcher implementation
Based on the BPS format specification
"""

import os

def apply_bps_patch(source_rom, patch_data):
    """
    Apply a BPS patch to a ROM file
    
    Args:
        source_rom: bytes or bytearray of the source ROM
        patch_data: bytes of the BPS patch file
    
    Returns:
        bytes: Patched ROM data
    """
    if len(patch_data) < 19:
        raise ValueError("Patch file too small")
    
    # Read BPS header
    if patch_data[0:4] != b'BPS1':
        raise ValueError("Invalid BPS patch file")
    
    # Read metadata lengths
    source_size = read_vlv(patch_data, 4)
    target_size = read_vlv(patch_data, source_size[1])
    metadata_size = read_vlv(patch_data, target_size[1])
    
    offset = metadata_size[1]
    
    # Skip metadata
    offset += metadata_size[0]
    
    # Apply actions
    target = bytearray(target_size[0])
    source_read_offset = 0
    target_write_offset = 0
    
    # Safety: Limit iterations to prevent infinite loops
    max_iterations = len(patch_data) * 2
    iteration_count = 0
    
    # Process actions until we reach the checksum section (last 12 bytes)
    while offset < len(patch_data) - 12:
        iteration_count += 1
        if iteration_count > max_iterations:
            raise ValueError("Patch processing exceeded maximum iterations - patch may be corrupted")
        action_data = read_vlv(patch_data, offset)
        offset = action_data[1]
        action_raw = action_data[0]
        action = action_raw & 3
        length = (action_raw >> 2) + 1
        
        if action == 0:  # SourceRead - copy from source ROM
            for i in range(length):
                if source_read_offset < len(source_rom) and target_write_offset < len(target):
                    target[target_write_offset] = source_rom[source_read_offset]
                elif target_write_offset < len(target):
                    target[target_write_offset] = 0
                target_write_offset += 1
                source_read_offset += 1
                
        elif action == 1:  # TargetRead - read new data from patch
            for i in range(length):
                if offset < len(patch_data) and target_write_offset < len(target):
                    target[target_write_offset] = patch_data[offset]
                elif target_write_offset < len(target):
                    target[target_write_offset] = 0
                target_write_offset += 1
                offset += 1
                
        elif action == 2:  # SourceCopy - copy from source ROM at relative offset
            copy_data = read_vlv(patch_data, offset)
            offset = copy_data[1]
            copy_offset = copy_data[0]
            # Decode relative offset (signed)
            if copy_offset & 1:
                relative_offset = -((copy_offset >> 1) + 1)
            else:
                relative_offset = (copy_offset >> 1)
            
            source_read_offset += relative_offset
            
            for i in range(length):
                if source_read_offset >= 0 and source_read_offset < len(source_rom) and target_write_offset < len(target):
                    target[target_write_offset] = source_rom[source_read_offset]
                elif target_write_offset < len(target):
                    target[target_write_offset] = 0
                target_write_offset += 1
                source_read_offset += 1
                
        elif action == 3:  # TargetCopy - copy from already-written target data
            copy_data = read_vlv(patch_data, offset)
            offset = copy_data[1]
            copy_offset = copy_data[0]
            # Decode relative offset (signed)
            if copy_offset & 1:
                relative_offset = -((copy_offset >> 1) + 1)
            else:
                relative_offset = (copy_offset >> 1)
            
            # Calculate absolute position to copy from
            copy_from = target_write_offset + relative_offset
            
            for i in range(length):
                if copy_from >= 0 and copy_from < target_write_offset and target_write_offset < len(target):
                    # Copy from already-written target data
                    target[target_write_offset] = target[copy_from]
                elif target_write_offset < len(target):
                    target[target_write_offset] = 0
                target_write_offset += 1
                copy_from += 1
    
    # Note: Checksum verification skipped for now (last 12 bytes contain checksums)
    return bytes(target)


def read_vlv(data, offset):
    """
    Read a variable-length value from BPS patch data
    
    Returns:
        tuple: (value, new_offset)
    """
    result = 0
    shift = 1
    
    while offset < len(data):
        byte = data[offset]
        offset += 1
        result += (byte & 0x7F) * shift
        if byte & 0x80:
            break
        shift <<= 7
    
    return (result, offset)


def apply_bps_patch_safe(source_rom, patch_data):
    """
    Safer BPS patch implementation with better error handling
    Falls back to using flips tool if available
    """
    try:
        return apply_bps_patch(source_rom, patch_data)
    except Exception as e:
        # Try using flips tool as fallback
        import tempfile
        import subprocess
        
        # Check if flips is available
        flips_paths = [
            'flips.exe',
            'flips',
            os.path.join(os.path.dirname(__file__), 'flips.exe')
        ]
        
        flips = None
        for path in flips_paths:
            if os.path.exists(path) or (path == 'flips' and subprocess.run(['which', 'flips'], capture_output=True).returncode == 0):
                flips = path
                break
        
        if flips:
            # Use flips to apply patch
            with tempfile.NamedTemporaryFile(delete=False, suffix='.smc') as source_file:
                source_file.write(source_rom)
                source_path = source_file.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.bps') as patch_file:
                patch_file.write(patch_data)
                patch_path = patch_file.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.smc') as output_file:
                output_path = output_file.name
            
            try:
                subprocess.run([flips, '--apply', patch_path, source_path, output_path], 
                             check=True, capture_output=True)
                
                with open(output_path, 'rb') as f:
                    result = f.read()
                
                return result
            finally:
                # Cleanup temp files
                for path in [source_path, patch_path, output_path]:
                    try:
                        os.unlink(path)
                    except:
                        pass
        else:
            raise e


#!/usr/bin/env python3
# K!ll Fl!utter - Flutter SSL Pinning Bypass Tool
# By: f3rb
# Supports: Android (APK) + iOS (IPA)
# For authorized penetration testing only

import struct, re, sys, os, zipfile, subprocess, argparse


# ─────────────────────────────────────────────
#  BANNER & HELP
# ─────────────────────────────────────────────

def print_banner():
    print("""
\033[36m
██╗  ██╗██╗██╗     ██╗     
██║ ██╔╝██║██║     ██║     
█████╔╝ ██║██║     ██║     
██╔═██╗ ██║██║     ██║     
██║  ██╗██║███████╗███████╗
╚═╝  ╚═╝╚═╝╚══════╝╚══════╝
\033[35m
███████╗██╗     ██╗   ██╗████████╗████████╗███████╗██████╗ 
██╔════╝██║     ██║   ██║╚══██╔══╝╚══██╔══╝██╔════╝██╔══██╗
█████╗  ██║     ██║   ██║   ██║      ██║   █████╗  ██████╔╝
██╔══╝  ██║     ██║   ██║   ██║      ██║   ██╔══╝  ██╔══██╗
██║     ███████╗╚██████╔╝   ██║      ██║   ███████╗██║  ██║
╚═╝     ╚══════╝ ╚═════╝    ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═╝
\033[0m
\033[96m  ╔══════════════════════════════════════════════════════╗
  ║   \033[93mK!ll Fl!utter  \033[91m—  Flutter SSL Pinning Bypass      \033[96m║
  ║   \033[92mBy: f3rb                            \033[90mv2.0.0        \033[96m║
  ║   \033[95mAndroid (APK) + iOS (IPA) Support               \033[96m║
  ║   \033[95mFor authorized penetration testing only          \033[96m║
  ╚══════════════════════════════════════════════════════╝\033[0m
""")


def print_help():
    print_banner()
    print("""
\033[93mUSAGE:\033[0m
  python3 kill_flutter.py <path_to_apk_or_ipa> [options]

\033[93mOPTIONS:\033[0m
  \033[92m-h, --help\033[0m          Show this help message
  \033[92m-i, --ip\033[0m            Your machine IP (for proxy/iptables commands)
  \033[92m-p, --port\033[0m          Burp Suite port (default: 8080)
  \033[92m-o, --output\033[0m        Output directory for generated files
  \033[92m--platform\033[0m          Force platform: android or ios (auto-detected from extension)

\033[93mEXAMPLES:\033[0m
  \033[90m# Android APK\033[0m
  python3 kill_flutter.py app.apk -i 192.168.1.10 -p 8080

  \033[90m# iOS IPA\033[0m
  python3 kill_flutter.py app.ipa -i 192.168.1.10 -p 8080

  \033[90m# Force platform\033[0m
  python3 kill_flutter.py app.apk --platform android -i 192.168.1.10

\033[93mWORKFLOW:\033[0m
  \033[96m1.\033[0m Auto-detects platform from file extension
  \033[96m2.\033[0m Extracts Flutter engine binary (libflutter.so / Flutter framework)
  \033[96m3.\033[0m Scans for ssl_client/ssl_server string anchors
  \033[96m4.\033[0m Parses ELF (Android) or Mach-O (iOS) segments
  \033[96m5.\033[0m Finds ADRP+ADD instruction pairs referencing both strings
  \033[96m6.\033[0m Walks back to function prologue to get exact hook offset
  \033[96m7.\033[0m Generates ready-to-use Frida script
  \033[96m8.\033[0m Prints copy-paste commands for your platform

\033[93mREQUIREMENTS:\033[0m
  \033[92m- Python 3\033[0m
  \033[92m- Frida\033[0m             pip install frida-tools
  \033[92m- aapt\033[0m              Android SDK build tools (Android only)
  \033[92m- Rooted Android / Jailbroken iOS device\033[0m
  \033[92m- Burp Suite\033[0m        invisible proxy on all interfaces

\033[93mBURP SETUP:\033[0m
  \033[96m-\033[0m Proxy → Listeners → Bind to 0.0.0.0:8080
  \033[96m-\033[0m Request handling → Enable invisible proxying
  \033[96m-\033[0m Intercept → OFF

\033[93mANDROID — REVERT IPTABLES:\033[0m
  adb shell su -c "iptables -t nat -D OUTPUT -p tcp --dport 443 -j DNAT --to-destination <IP>:8080"
  adb shell su -c "iptables -t nat -D OUTPUT -p tcp --dport 80  -j DNAT --to-destination <IP>:8080"
  \033[90m# Or simply: adb reboot\033[0m

\033[93miOS — REVERT IPTABLES (via SSH):\033[0m
  ssh root@<device-ip> "iptables -t nat -D OUTPUT -p tcp --dport 443 -j DNAT --to-destination <IP>:8080"
  ssh root@<device-ip> "iptables -t nat -D OUTPUT -p tcp --dport 80  -j DNAT --to-destination <IP>:8080"
  \033[90m# Or simply reboot the device\033[0m
""")


# ─────────────────────────────────────────────
#  PLATFORM DETECTION
# ─────────────────────────────────────────────

def detect_platform(file_path, forced=None):
    if forced:
        return forced.lower()
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.apk':
        return 'android'
    elif ext == '.ipa':
        return 'ios'
    else:
        print("\033[93m[!] Cannot detect platform from extension. Use --platform android or --platform ios\033[0m")
        sys.exit(1)


# ─────────────────────────────────────────────
#  ANDROID — PACKAGE NAME
# ─────────────────────────────────────────────

def get_package_name_android(apk_path):
    try:
        result = subprocess.run(
            ['aapt', 'dump', 'badging', apk_path],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if line.startswith("package:"):
                for part in line.split():
                    if part.startswith("name="):
                        return part.split("'")[1]
    except Exception as e:
        print(f"\033[93m[!] aapt failed: {e}\033[0m")
    return None


# ─────────────────────────────────────────────
#  iOS — BUNDLE ID
# ─────────────────────────────────────────────

def get_bundle_id_ios(ipa_path):
    try:
        with zipfile.ZipFile(ipa_path, 'r') as z:
            # Find Info.plist
            for name in z.namelist():
                if re.match(r'Payload/[^/]+\.app/Info\.plist$', name):
                    with z.open(name) as f:
                        content = f.read().decode('utf-8', errors='ignore')
                    # Simple regex parse for CFBundleIdentifier
                    m = re.search(r'CFBundleIdentifier.*?<string>(.*?)</string>', content, re.DOTALL)
                    if m:
                        return m.group(1).strip()
    except Exception as e:
        print(f"\033[93m[!] Could not parse Info.plist: {e}\033[0m")
    return None


# ─────────────────────────────────────────────
#  ANDROID — EXTRACT libflutter.so
# ─────────────────────────────────────────────

def extract_flutter_android(apk_path, out_dir):
    so_path = os.path.join(out_dir, 'libflutter.so')
    print(f"\033[96m[*]\033[0m Extracting libflutter.so from APK...")
    with zipfile.ZipFile(apk_path, 'r') as z:
        for name in z.namelist():
            if 'arm64-v8a/libflutter.so' in name:
                print(f"\033[92m[+]\033[0m Found: {name}")
                with z.open(name) as src, open(so_path, 'wb') as dst:
                    dst.write(src.read())
                return so_path
    print("\033[91m[-] libflutter.so (arm64-v8a) not found — is this a Flutter APK?\033[0m")
    return None


# ─────────────────────────────────────────────
#  iOS — EXTRACT Flutter framework binary
# ─────────────────────────────────────────────

def extract_flutter_ios(ipa_path, out_dir):
    fw_path = os.path.join(out_dir, 'Flutter')
    print(f"\033[96m[*]\033[0m Extracting Flutter framework from IPA...")
    with zipfile.ZipFile(ipa_path, 'r') as z:
        for name in z.namelist():
            if re.search(r'Payload/[^/]+\.app/Frameworks/Flutter\.framework/Flutter$', name):
                print(f"\033[92m[+]\033[0m Found: {name}")
                with z.open(name) as src, open(fw_path, 'wb') as dst:
                    dst.write(src.read())
                return fw_path
    print("\033[91m[-] Flutter.framework/Flutter not found — is this a Flutter IPA?\033[0m")
    return None


# ─────────────────────────────────────────────
#  ELF SEGMENT PARSER (Android ARM64)
# ─────────────────────────────────────────────

def parse_elf_segments(data):
    """Returns (code_foff, code_vaddr, code_filesz) for the executable segment."""
    if data[:4] != b'\x7fELF':
        return None, None, None

    e_phoff     = struct.unpack_from('<Q', data, 0x20)[0]
    e_phentsize = struct.unpack_from('<H', data, 0x36)[0]
    e_phnum     = struct.unpack_from('<H', data, 0x38)[0]

    code_foff = code_vaddr = code_filesz = None
    for i in range(e_phnum):
        ph      = data[e_phoff + i*e_phentsize : e_phoff + (i+1)*e_phentsize]
        p_type  = struct.unpack_from('<I', ph, 0x00)[0]
        p_flags = struct.unpack_from('<I', ph, 0x04)[0]
        if p_type == 1 and (p_flags & 1):  # PT_LOAD + PF_X
            code_foff   = struct.unpack_from('<Q', ph, 0x08)[0]
            code_vaddr  = struct.unpack_from('<Q', ph, 0x10)[0]
            code_filesz = struct.unpack_from('<Q', ph, 0x20)[0]
            print(f"\033[96m[*]\033[0m ELF code segment: file={hex(code_foff)} vaddr={hex(code_vaddr)} size={hex(code_filesz)}")

    return code_foff, code_vaddr, code_filesz


# ─────────────────────────────────────────────
#  MACH-O SEGMENT PARSER (iOS ARM64)
# ─────────────────────────────────────────────

def parse_macho_segments(data):
    """Returns (code_foff, code_vaddr, code_filesz) for __TEXT executable segment."""

    MH_MAGIC_64    = 0xFEEDFACF  # 64-bit little-endian
    FAT_MAGIC      = 0xCAFEBABE  # Fat binary (big-endian)
    LC_SEGMENT_64  = 0x19
    CPU_TYPE_ARM64 = 0x0100000C  # in big-endian fat arch

    magic = struct.unpack_from('<I', data, 0)[0]

    # Handle fat binary — extract arm64 slice
    if magic == struct.unpack('>I', struct.pack('<I', FAT_MAGIC))[0] or \
       struct.unpack_from('>I', data, 0)[0] == FAT_MAGIC:
        print(f"\033[96m[*]\033[0m Detected fat binary — extracting arm64 slice")
        nfat = struct.unpack_from('>I', data, 4)[0]
        for i in range(nfat):
            off = 8 + i * 20
            cputype = struct.unpack_from('>I', data, off)[0]
            slice_offset = struct.unpack_from('>I', data, off + 8)[0]
            slice_size   = struct.unpack_from('>I', data, off + 12)[0]
            # ARM64 cputype = 0x0100000C
            if cputype == 0x0100000C:
                print(f"\033[92m[+]\033[0m arm64 slice found at offset {hex(slice_offset)}")
                data = data[slice_offset:slice_offset + slice_size]
                magic = struct.unpack_from('<I', data, 0)[0]
                break

    if magic != MH_MAGIC_64:
        print(f"\033[91m[-] Not a valid Mach-O 64-bit binary (magic={hex(magic)})\033[0m")
        return None, None, None

    ncmds    = struct.unpack_from('<I', data, 16)[0]
    cmd_off  = 32  # sizeof mach_header_64

    code_foff = code_vaddr = code_filesz = None

    for _ in range(ncmds):
        cmd     = struct.unpack_from('<I', data, cmd_off)[0]
        cmdsize = struct.unpack_from('<I', data, cmd_off + 4)[0]

        if cmd == LC_SEGMENT_64:
            # segname is 16 bytes at offset +8
            segname  = data[cmd_off + 8 : cmd_off + 24].rstrip(b'\x00').decode('utf-8', errors='ignore')
            vmaddr   = struct.unpack_from('<Q', data, cmd_off + 24)[0]
            vmsize   = struct.unpack_from('<Q', data, cmd_off + 32)[0]
            fileoff  = struct.unpack_from('<Q', data, cmd_off + 40)[0]
            filesize = struct.unpack_from('<Q', data, cmd_off + 48)[0]
            maxprot  = struct.unpack_from('<I', data, cmd_off + 56)[0]

            # __TEXT segment with execute permission (VM_PROT_EXECUTE = 4)
            if segname == '__TEXT' and (maxprot & 4):
                code_foff   = fileoff
                code_vaddr  = vmaddr
                code_filesz = filesize
                print(f"\033[96m[*]\033[0m Mach-O __TEXT segment: file={hex(fileoff)} vaddr={hex(vmaddr)} size={hex(filesize)}")

        cmd_off += cmdsize

    return code_foff, code_vaddr, code_filesz, data  # return possibly-sliced data


# ─────────────────────────────────────────────
#  CORE — FIND SSL OFFSET (shared for both platforms)
# ─────────────────────────────────────────────

def find_offset(binary_path, platform):
    print(f"\033[96m[*]\033[0m Loading binary: {binary_path}")
    with open(binary_path, 'rb') as f:
        data = f.read()

    # Find string anchors
    ssl_client = [m.start() for m in re.finditer(b'ssl_client\x00', data)]
    ssl_server  = [m.start() for m in re.finditer(b'ssl_server\x00', data)]

    if not ssl_client or not ssl_server:
        print("\033[91m[-] ssl_client/ssl_server strings not found — may not be a Flutter binary\033[0m")
        return None

    print(f"\033[92m[+]\033[0m ssl_client @ {[hex(x) for x in ssl_client]}")
    print(f"\033[92m[+]\033[0m ssl_server @ {[hex(x) for x in ssl_server]}")

    # Parse segments based on platform
    if platform == 'android':
        code_foff, code_vaddr, code_filesz = parse_elf_segments(data)
    else:
        result = parse_macho_segments(data)
        if len(result) == 4:
            code_foff, code_vaddr, code_filesz, data = result
            # Re-find strings in possibly-sliced data
            ssl_client = [m.start() for m in re.finditer(b'ssl_client\x00', data)]
            ssl_server  = [m.start() for m in re.finditer(b'ssl_server\x00', data)]
        else:
            code_foff, code_vaddr, code_filesz = result[:3]

    if code_foff is None:
        print("\033[91m[-] No executable segment found\033[0m")
        return None

    def foff_to_vaddr(fo):
        return fo - code_foff + code_vaddr

    def find_refs(target_va):
        lo12 = target_va & 0xfff
        refs = []
        for fi in range(code_foff, code_foff + code_filesz - 4, 4):
            instr = struct.unpack_from('<I', data, fi)[0]
            if (instr & 0xffc00000) == 0x91000000 and ((instr >> 10) & 0xfff) == lo12:
                if fi >= 4:
                    adrp = struct.unpack_from('<I', data, fi - 4)[0]
                    if (adrp & 0x9f000000) == 0x90000000:
                        immlo = (adrp >> 29) & 0x3
                        immhi = (adrp >> 5) & 0x7ffff
                        imm = ((immhi << 2) | immlo) << 12
                        if imm & (1 << 32):
                            imm -= (1 << 33)
                        pc_va = foff_to_vaddr(fi - 4)
                        if (pc_va & ~0xfff) + imm == (target_va & ~0xfff):
                            refs.append(fi)
        return refs

    print(f"\033[96m[*]\033[0m Scanning ADRP+ADD refs... (may take a moment)")
    sc_refs = find_refs(ssl_client[0])
    ss_refs = find_refs(ssl_server[0])
    print(f"\033[96m[*]\033[0m ssl_client code refs: {[hex(x) for x in sc_refs]}")
    print(f"\033[96m[*]\033[0m ssl_server code refs: {[hex(x) for x in ss_refs]}")

    for a in sc_refs:
        for b in ss_refs:
            if abs(a - b) < 0x800:
                start = min(a, b)
                for i in range(start, max(code_foff, start - 0x300), -4):
                    instr = struct.unpack_from('<I', data, i)[0]
                    if (instr & 0xff8003ff) == 0xd10003ff or (instr & 0xffe07fff) == 0xa9007bfd:
                        vaddr = foff_to_vaddr(i)
                        print(f"\033[92m[+]\033[0m SSL verify offset: \033[93m{hex(vaddr)}\033[0m")
                        print(f"\033[92m[+]\033[0m First bytes: {data[i:i+16].hex(' ')}")
                        return vaddr

    print("\033[91m[-] Could not find SSL verify function\033[0m")
    return None


# ─────────────────────────────────────────────
#  FRIDA SCRIPT GENERATOR
# ─────────────────────────────────────────────

def write_frida_script(offset, package, platform, out_path):
    # Module name differs between platforms
    module_name = 'libflutter.so' if platform == 'android' else 'Flutter'

    script = f"""// ================================================
// K!ll Fl!utter - Auto-generated Frida Script
// By: f3rb
// Platform : {platform.upper()}
// Package  : {package}
// Offset   : {hex(offset)}
// Module   : {module_name}
// ================================================

function hook_ssl_verify_result(address) {{
    Interceptor.attach(address, {{
        onEnter: function(args) {{
            console.log("[+] ssl_verify hooked — killing cert validation");
        }},
        onLeave: function(retval) {{
            console.log("[*] retval was: " + retval);
            retval.replace(0x1);
            console.log("[*] forced success");
        }}
    }});
}}

function disablePinning() {{
    var m = Process.findModuleByName("{module_name}");
    if (!m) {{
        console.log("[-] {module_name} not found");
        return;
    }}
    console.log("[+] {module_name} base: " + m.base);

    var offset = {hex(offset)};
    var addr = m.base.add(offset);
    console.log("[+] Hooking at: " + addr);
    hook_ssl_verify_result(addr);
}}

setTimeout(disablePinning, 1000);
"""
    with open(out_path, 'w') as f:
        f.write(script)
    print(f"\033[92m[+]\033[0m Frida script saved: \033[93m{out_path}\033[0m")


# ─────────────────────────────────────────────
#  PRINT FINAL COMMANDS
# ─────────────────────────────────────────────

def print_commands_android(package, proxy, script_path):
    set_443   = f'adb shell su -c "iptables -t nat -A OUTPUT -p tcp --dport 443 -j DNAT --to-destination {proxy}"'
    set_80    = f'adb shell su -c "iptables -t nat -A OUTPUT -p tcp --dport 80  -j DNAT --to-destination {proxy}"'
    verify    = 'adb shell su -c "iptables -t nat -L OUTPUT --line-numbers"'
    frida_cmd = f'frida -U -f {package} --no-pause -l "{script_path}"'
    del_443   = f'adb shell su -c "iptables -t nat -D OUTPUT -p tcp --dport 443 -j DNAT --to-destination {proxy}"'
    del_80    = f'adb shell su -c "iptables -t nat -D OUTPUT -p tcp --dport 80  -j DNAT --to-destination {proxy}"'

    print("")
    print("\033[96m╔══════════════════════════════════════════════════════╗")
    print("║          \033[93mANDROID — COPY PASTE COMMANDS\033[96m                ║")
    print("╚══════════════════════════════════════════════════════╝\033[0m")
    print("")
    print("\033[93m[1] Set iptables on device:\033[0m")
    print("  " + set_443)
    print("  " + set_80)
    print("")
    print("\033[93m[2] Verify iptables rules:\033[0m")
    print("  " + verify)
    print("")
    print("\033[93m[3] Launch Frida:\033[0m")
    print("\033[92m  " + frida_cmd + "\033[0m")
    print("")
    print("\033[93m[4] Revert when done:\033[0m")
    print("  " + del_443)
    print("  " + del_80)
    print("\033[90m  # or just: adb reboot\033[0m")


def print_commands_ios(package, proxy, script_path, device_ip):
    frida_cmd = f'frida -U -f {package} --no-pause -l "{script_path}"'
    set_443   = f'ssh root@{device_ip} "iptables -t nat -A OUTPUT -p tcp --dport 443 -j DNAT --to-destination {proxy}"'
    set_80    = f'ssh root@{device_ip} "iptables -t nat -A OUTPUT -p tcp --dport 80  -j DNAT --to-destination {proxy}"'
    del_443   = f'ssh root@{device_ip} "iptables -t nat -D OUTPUT -p tcp --dport 443 -j DNAT --to-destination {proxy}"'
    del_80    = f'ssh root@{device_ip} "iptables -t nat -D OUTPUT -p tcp --dport 80  -j DNAT --to-destination {proxy}"'

    print("")
    print("\033[96m╔══════════════════════════════════════════════════════╗")
    print("║            \033[93miOS — COPY PASTE COMMANDS\033[96m                  ║")
    print("╚══════════════════════════════════════════════════════╝\033[0m")
    print("")
    print("\033[93m[1] Set WiFi proxy on device:\033[0m")
    print(f"  Settings → WiFi → Your Network → HTTP Proxy → Manual")
    print(f"  Server: {proxy.split(':')[0]}  Port: {proxy.split(':')[1]}")
    print("")
    print("\033[93m[2] Set iptables on device (jailbroken via SSH):\033[0m")
    print("  " + set_443)
    print("  " + set_80)
    print("")
    print("\033[93m[3] Launch Frida:\033[0m")
    print("\033[92m  " + frida_cmd + "\033[0m")
    print("")
    print("\033[93m[4] Revert when done:\033[0m")
    print("  " + del_443)
    print("  " + del_80)
    print("\033[90m  # or just reboot the device\033[0m")


def print_summary(package, offset, script_path, proxy, platform):
    print("")
    print("\033[96m╔══════════════════════════════════════════════════════╗")
    print("\033[93m  Platform : \033[92m" + platform.upper())
    print("\033[93m  Package  : \033[92m" + package)
    print("\033[93m  Offset   : \033[92m" + hex(offset))
    print("\033[93m  Script   : \033[92m" + os.path.basename(script_path))
    print("\033[93m  Proxy    : \033[92m" + proxy)
    print("\033[96m╚══════════════════════════════════════════════════════╝\033[0m")
    print("")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) == 1 or '-h' in sys.argv or '--help' in sys.argv:
        print_help()
        sys.exit(0)

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('app', nargs='?', help='Path to APK or IPA')
    parser.add_argument('-i', '--ip', default='<YOUR_IP>', help='Your machine IP')
    parser.add_argument('-p', '--port', default='8080', help='Burp port')
    parser.add_argument('-o', '--output', help='Output directory')
    parser.add_argument('--platform', choices=['android', 'ios'], help='Force platform')
    parser.add_argument('--device-ip', default='<DEVICE_IP>', help='iOS device IP (for SSH iptables)')
    args = parser.parse_args()

    print_banner()

    app_path = args.app
    if not app_path:
        print("\033[91m[-] No APK/IPA provided. Use -h for help.\033[0m")
        sys.exit(1)

    if not os.path.exists(app_path):
        print(f"\033[91m[-] File not found: {app_path}\033[0m")
        sys.exit(1)

    platform = detect_platform(app_path, args.platform)
    out_dir  = args.output or os.path.dirname(os.path.abspath(app_path))
    os.makedirs(out_dir, exist_ok=True)

    ip        = args.ip
    port      = args.port
    proxy     = ip + ":" + port
    device_ip = args.device_ip

    print(f"\033[96m[*]\033[0m Platform : \033[93m{platform.upper()}\033[0m")
    print(f"\033[96m[*]\033[0m App      : {app_path}")
    print(f"\033[96m[*]\033[0m Output   : {out_dir}")
    print(f"\033[96m[*]\033[0m Proxy    : {proxy}")

    # Step 1: Get identifier
    if platform == 'android':
        package = get_package_name_android(app_path)
        if package:
            print(f"\033[92m[+]\033[0m Package: \033[93m{package}\033[0m")
        else:
            package = input("\033[93m[?] Enter package name manually: \033[0m").strip()
    else:
        package = get_bundle_id_ios(app_path)
        if package:
            print(f"\033[92m[+]\033[0m Bundle ID: \033[93m{package}\033[0m")
        else:
            package = input("\033[93m[?] Enter bundle ID manually (e.g. com.example.app): \033[0m").strip()

    # Step 2: Extract Flutter binary
    if platform == 'android':
        binary_path = extract_flutter_android(app_path, out_dir)
    else:
        binary_path = extract_flutter_ios(app_path, out_dir)

    if not binary_path:
        sys.exit(1)

    # Step 3: Find SSL offset
    offset = find_offset(binary_path, platform)
    if offset is None:
        sys.exit(1)

    # Step 4: Write Frida script
    script_path = os.path.join(out_dir, 'flutter_bypass.js')
    write_frida_script(offset, package, platform, script_path)

    # Step 5: Print commands
    if platform == 'android':
        print_commands_android(package, proxy, script_path)
    else:
        print_commands_ios(package, proxy, script_path, device_ip)

    print_summary(package, offset, script_path, proxy, platform)


if __name__ == '__main__':
    main()
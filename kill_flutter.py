#!/usr/bin/env python3
# K!ll Fl!utter - Flutter SSL Pinning Bypass Tool
# By: f3rb
# Supports: Android (APK) + iOS (IPA)
# Architectures: arm64-v8a, x86_64, armeabi-v7a (Android) + arm64 (iOS)
# For authorized penetration testing only

import struct, re, sys, os, zipfile, subprocess, argparse, plistlib
import bisect
from collections import defaultdict


# ─────────────────────────────────────────────
#  BOX HELPERS (keeps all boxes perfectly aligned)
# ─────────────────────────────────────────────

BOX_WIDTH = 54  # visible characters between the ║ borders

C_CYAN   = "\033[96m"
C_YELLOW = "\033[93m"
C_GREEN  = "\033[92m"
C_RED    = "\033[91m"
C_GREY   = "\033[90m"
C_PURPLE = "\033[95m"
C_RESET  = "\033[0m"


def box_top():
    return C_CYAN + "╔" + "═" * BOX_WIDTH + "╗" + C_RESET


def box_bottom():
    return C_CYAN + "╚" + "═" * BOX_WIDTH + "╝" + C_RESET


def box_line(text, color=""):
    """text is the raw visible text (no ANSI). Pads to BOX_WIDTH and adds borders."""
    padded = text.ljust(BOX_WIDTH)
    return f"{C_CYAN}║{C_RESET}{color}{padded}{C_RESET}{C_CYAN}║{C_RESET}"


# ─────────────────────────────────────────────
#  BANNER & HELP
# ─────────────────────────────────────────────

def print_banner():
    print(C_CYAN + """
██╗  ██╗██╗██╗     ██╗     
██║ ██╔╝██║██║     ██║     
█████╔╝ ██║██║     ██║     
██╔═██╗ ██║██║     ██║     
██║  ██╗██║███████╗███████╗
╚═╝  ╚═╝╚═╝╚══════╝╚══════╝""" + C_PURPLE + """
███████╗██╗     ██╗   ██╗████████╗████████╗███████╗██████╗ 
██╔════╝██║     ██║   ██║╚══██╔══╝╚══██╔══╝██╔════╝██╔══██╗
█████╗  ██║     ██║   ██║   ██║      ██║   █████╗  ██████╔╝
██╔══╝  ██║     ██║   ██║   ██║      ██║   ██╔══╝  ██╔══██╗
██║     ███████╗╚██████╔╝   ██║      ██║   ███████╗██║  ██║
╚═╝     ╚══════╝ ╚═════╝    ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═╝""" + C_RESET)

    print(box_top())
    print(box_line("  K!ll Fl!utter  —  Flutter SSL Pinning Bypass", C_YELLOW))
    print(box_line("  By: f3rb                              v3.0.0", C_GREEN))
    print(box_line("  Android (APK) + iOS (IPA) Support", C_PURPLE))
    print(box_line("  Multi-arch: arm64 / x86_64 / armeabi-v7a", C_PURPLE))
    print(box_line("  For authorized penetration testing only", C_PURPLE))
    print(box_bottom())
    print("")


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
  \033[92m--arch\033[0m              Android ABI to target: arm64-v8a | x86_64 |
                      armeabi-v7a | x86  (auto-detected if omitted;
                      defaults to arm64-v8a when present)
  \033[92m--list-arch\033[0m         List the ABIs bundled in the APK and exit
  \033[92m--platform\033[0m          Force platform: android or ios
  \033[92m--device-ip\033[0m         iOS device IP (for SSH iptables)

\033[93mEXAMPLES:\033[0m
  \033[90m# Android APK (defaults to arm64-v8a)\033[0m
  python3 kill_flutter.py app.apk -i 192.168.1.10 -p 8080

  \033[90m# Target an x86_64 emulator build\033[0m
  python3 kill_flutter.py app.apk --arch x86_64 -i 192.168.1.10

  \033[90m# Target a 32-bit device build\033[0m
  python3 kill_flutter.py app.apk --arch armeabi-v7a -i 192.168.1.10

  \033[90m# Just see what's inside\033[0m
  python3 kill_flutter.py app.apk --list-arch

  \033[90m# iOS IPA\033[0m
  python3 kill_flutter.py app.ipa -i 192.168.1.10 -p 8080

\033[93mWORKFLOW:\033[0m
  \033[96m1.\033[0m Auto-detects platform from file extension
  \033[96m2.\033[0m Extracts the chosen ABI's libflutter.so (or Flutter framework)
  \033[96m3.\033[0m Scans for ssl_client/ssl_server string anchors
  \033[96m4.\033[0m Detects arch from the ELF/Mach-O header and routes to the
     matching offset engine (ARM64 ADRP+ADD, x86_64 RIP-relative LEA,
     or ARMv7 MOVW/MOVT+ADD-PC / literal pool)
  \033[96m5.\033[0m Walks back to the function prologue to get the hook offset
  \033[96m6.\033[0m Generates a ready-to-use Frida script + copy-paste commands

\033[93mREQUIREMENTS:\033[0m
  \033[92m- Python 3\033[0m
  \033[92m- Frida\033[0m             pip install frida-tools
  \033[92m- capstone\033[0m          pip install capstone   (only for x86_64 / armeabi-v7a)
  \033[92m- aapt\033[0m              Android SDK build tools (Android only)
  \033[92m- Rooted Android / Jailbroken iOS device\033[0m
  \033[92m- Burp Suite\033[0m        invisible proxy on all interfaces

\033[93mNOTE ON ARCHITECTURES:\033[0m
  Android maps only the ABI matching the device/emulator at runtime, so the
  offset must come from the SAME ABI you will actually run Frida against:
    - real phones          -> arm64-v8a (a few old/budget ones -> armeabi-v7a)
    - Intel/AMD emulators  -> x86_64 (older images -> x86)
  The arm64 engine is dependency-free. x86_64 and armeabi-v7a require capstone.

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
                        content = f.read()

                    try:
                        plist_data = plistlib.loads(content)
                        if 'CFBundleIdentifier' in plist_data:
                            return plist_data['CFBundleIdentifier'].strip()
                    except Exception as parse_e:
                        print(f"\033[93m[!] Could not parse Info.plist data: {parse_e}\033[0m")
    except Exception as e:
        print(f"\033[93m[!] Could not read Info.plist from zip: {e}\033[0m")
    return None


# ─────────────────────────────────────────────
#  ANDROID — EXTRACT libflutter.so (arch-aware)
# ─────────────────────────────────────────────

# ABIs we know how to analyse, best -> worst practical value
KNOWN_ABIS = ['arm64-v8a', 'armeabi-v7a', 'x86_64', 'x86']


def list_flutter_arches(apk_path):
    """Return {abi: zip_entry_name} for every libflutter.so found in the APK."""
    found = {}
    with zipfile.ZipFile(apk_path, 'r') as z:
        for name in z.namelist():
            m = re.search(r'lib/([^/]+)/libflutter\.so$', name)
            if m:
                found[m.group(1)] = name
    return found


def extract_flutter_android(apk_path, out_dir, arch=None):
    """Extract the requested (or auto-selected) ABI's libflutter.so.
    Returns (so_path, abi) or (None, None)."""
    arches = list_flutter_arches(apk_path)
    if not arches:
        print("\033[91m[-] No libflutter.so found in any lib/<abi>/ — is this a Flutter APK?\033[0m")
        return None, None

    available = ', '.join(sorted(arches))
    print(f"\033[96m[*]\033[0m ABIs present in APK: \033[93m{available}\033[0m")

    if arch is None:
        # Prefer arm64-v8a (real devices), then fall back to the first known ABI
        for cand in KNOWN_ABIS:
            if cand in arches:
                arch = cand
                break
        if arch is None:
            arch = sorted(arches)[0]
        print(f"\033[96m[*]\033[0m No --arch given, auto-selected: \033[93m{arch}\033[0m")

    if arch not in arches:
        print(f"\033[91m[-] ABI '{arch}' not bundled in this APK.\033[0m")
        print(f"\033[93m[!] Available: {available}  (pass one with --arch)\033[0m")
        return None, None

    so_path = os.path.join(out_dir, f'libflutter_{arch}.so')
    print(f"\033[96m[*]\033[0m Extracting {arch}/libflutter.so ...")
    with zipfile.ZipFile(apk_path, 'r') as z:
        with z.open(arches[arch]) as src, open(so_path, 'wb') as dst:
            dst.write(src.read())
    print(f"\033[92m[+]\033[0m Found: {arches[arch]}")
    print(f"\033[92m[+]\033[0m Saved: {so_path}")
    return so_path, arch


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
#  ELF / MACH-O SEGMENT PARSERS
#  Each returns a dict describing the executable segment plus a list of
#  (file_offset, vaddr, filesz) LOAD segments used for foff<->vaddr mapping.
# ─────────────────────────────────────────────

def parse_elf64_segments(data):
    if data[:4] != b'\x7fELF':
        return None
    e_phoff     = struct.unpack_from('<Q', data, 0x20)[0]
    e_phentsize = struct.unpack_from('<H', data, 0x36)[0]
    e_phnum     = struct.unpack_from('<H', data, 0x38)[0]

    loads = []
    code = None
    eh_frame_hdr = None
    for i in range(e_phnum):
        ph = e_phoff + i * e_phentsize
        p_type   = struct.unpack_from('<I', data, ph + 0x00)[0]
        p_flags  = struct.unpack_from('<I', data, ph + 0x04)[0]
        p_offset = struct.unpack_from('<Q', data, ph + 0x08)[0]
        p_vaddr  = struct.unpack_from('<Q', data, ph + 0x10)[0]
        p_filesz = struct.unpack_from('<Q', data, ph + 0x20)[0]
        if p_type == 1:  # PT_LOAD
            loads.append((p_offset, p_vaddr, p_filesz))
            if p_flags & 1 and code is None:  # PF_X
                code = (p_offset, p_vaddr, p_filesz)
                print(f"\033[92m[+]\033[0m ELF64 code segment: file={hex(p_offset)} vaddr={hex(p_vaddr)} size={hex(p_filesz)}")
        elif p_type == 0x6474e550:  # PT_GNU_EH_FRAME
            eh_frame_hdr = (p_offset, p_vaddr, p_filesz)

    if code is None:
        return None
    return {'loads': loads, 'code': code, 'eh_frame_hdr': eh_frame_hdr}


def parse_elf32_segments(data):
    if data[:4] != b'\x7fELF':
        return None
    e_phoff     = struct.unpack_from('<I', data, 0x1C)[0]
    e_phentsize = struct.unpack_from('<H', data, 0x2A)[0]
    e_phnum     = struct.unpack_from('<H', data, 0x2C)[0]

    loads = []
    code = None
    arm_exidx = None
    for i in range(e_phnum):
        ph = e_phoff + i * e_phentsize
        p_type   = struct.unpack_from('<I', data, ph + 0x00)[0]
        p_offset = struct.unpack_from('<I', data, ph + 0x04)[0]
        p_vaddr  = struct.unpack_from('<I', data, ph + 0x08)[0]
        p_filesz = struct.unpack_from('<I', data, ph + 0x10)[0]
        p_flags  = struct.unpack_from('<I', data, ph + 0x18)[0]
        if p_type == 1:  # PT_LOAD
            loads.append((p_offset, p_vaddr, p_filesz))
            if p_flags & 1 and code is None:  # PF_X
                code = (p_offset, p_vaddr, p_filesz)
                print(f"\033[92m[+]\033[0m ELF32 code segment: file={hex(p_offset)} vaddr={hex(p_vaddr)} size={hex(p_filesz)}")
        elif p_type == 0x70000001:  # PT_ARM_EXIDX
            arm_exidx = (p_offset, p_vaddr, p_filesz)

    if code is None:
        return None
    return {'loads': loads, 'code': code, 'arm_exidx': arm_exidx}


# ─────────────────────────────────────────────
#  MACH-O SEGMENT PARSER (iOS ARM64)
# ─────────────────────────────────────────────

def parse_macho_segments(data):
    """Returns (segdict, data) where data may be a sliced arm64 view of a fat binary."""
    MH_MAGIC_64    = 0xFEEDFACF  # 64-bit little-endian
    FAT_MAGIC      = 0xCAFEBABE  # Fat binary (big-endian)
    LC_SEGMENT_64  = 0x19

    magic = struct.unpack_from('<I', data, 0)[0]
    if struct.unpack_from('>I', data, 0)[0] == FAT_MAGIC:
        print(f"\033[96m[*]\033[0m Detected fat binary — extracting arm64 slice")
        nfat = struct.unpack_from('>I', data, 4)[0]
        for i in range(nfat):
            off = 8 + i * 20
            cputype      = struct.unpack_from('>I', data, off)[0]
            slice_offset = struct.unpack_from('>I', data, off + 8)[0]
            slice_size   = struct.unpack_from('>I', data, off + 12)[0]
            if cputype == 0x0100000C:  # ARM64
                print(f"\033[92m[+]\033[0m arm64 slice found at offset {hex(slice_offset)}")
                data = data[slice_offset:slice_offset + slice_size]
                magic = struct.unpack_from('<I', data, 0)[0]
                break

    if magic != MH_MAGIC_64:
        print(f"\033[91m[-] Not a valid Mach-O 64-bit binary (magic={hex(magic)})\033[0m")
        return None, data

    ncmds   = struct.unpack_from('<I', data, 16)[0]
    cmd_off = 32

    loads = []
    code = None
    for _ in range(ncmds):
        cmd     = struct.unpack_from('<I', data, cmd_off)[0]
        cmdsize = struct.unpack_from('<I', data, cmd_off + 4)[0]
        if cmd == LC_SEGMENT_64:
            segname  = data[cmd_off + 8: cmd_off + 24].rstrip(b'\x00').decode('utf-8', 'ignore')
            vmaddr   = struct.unpack_from('<Q', data, cmd_off + 24)[0]
            fileoff  = struct.unpack_from('<Q', data, cmd_off + 40)[0]
            filesize = struct.unpack_from('<Q', data, cmd_off + 48)[0]
            maxprot  = struct.unpack_from('<I', data, cmd_off + 56)[0]
            loads.append((fileoff, vmaddr, filesize))
            if segname == '__TEXT' and (maxprot & 4):  # VM_PROT_EXECUTE
                code = (fileoff, vmaddr, filesize)
                print(f"\033[92m[+]\033[0m Mach-O __TEXT segment: file={hex(fileoff)} vaddr={hex(vmaddr)} size={hex(filesize)}")
        cmd_off += cmdsize

    if code is None:
        return None, data
    # iOS builds don't ship .eh_frame_hdr; arm64 offset engine uses prologue fallback.
    return {'loads': loads, 'code': code, 'eh_frame_hdr': None}, data


def foff_to_vaddr(loads, fo):
    """Map a file offset to a virtual address using the LOAD segment table."""
    for (off, va, sz) in loads:
        if off <= fo < off + sz:
            return va + (fo - off)
    return fo  # last resort: assume identity


# ─────────────────────────────────────────────
#  UNWIND-TABLE FUNCTION-START TABLES  (exact boundaries)
# ─────────────────────────────────────────────

def eh_frame_function_starts(data, hdr_off, hdr_va):
    """Parse .eh_frame_hdr's binary-search table -> sorted list of function-start VAs."""
    p = hdr_off
    version = data[p]
    enc_fp  = data[p + 1]
    enc_cnt = data[p + 2]
    enc_tbl = data[p + 3]
    p += 4
    if version != 1:
        return []

    def dec(enc):
        nonlocal p
        fmt = enc & 0x0f
        if fmt == 0x03:      # udata4
            v = struct.unpack_from('<I', data, p)[0]; p += 4
        elif fmt == 0x0b:    # sdata4
            v = struct.unpack_from('<i', data, p)[0]; p += 4
        elif fmt == 0x0c:    # udata8
            v = struct.unpack_from('<Q', data, p)[0]; p += 8
        else:
            raise ValueError(f"eh_frame_hdr enc fmt {hex(fmt)} unsupported")
        return v

    dec(enc_fp)              # eh_frame_ptr (unused)
    cnt = dec(enc_cnt)

    appl = enc_tbl & 0x70
    fmt  = enc_tbl & 0x0f
    starts = []
    for _ in range(cnt):
        if fmt == 0x0b:
            iloc = struct.unpack_from('<i', data, p)[0]; p += 4
            struct.unpack_from('<i', data, p)[0];        p += 4  # fde ptr (skip)
        elif fmt == 0x03:
            iloc = struct.unpack_from('<I', data, p)[0]; p += 4
            struct.unpack_from('<I', data, p)[0];        p += 4
        else:
            raise ValueError("eh_frame_hdr table fmt unsupported")
        if appl == 0x30:     # datarel (relative to eh_frame_hdr start)
            va = (hdr_va + iloc) & 0xffffffffffffffff
        elif appl == 0x10:   # pcrel
            va = (hdr_va + (p - 8 - hdr_off) + iloc) & 0xffffffffffffffff
        else:
            va = iloc & 0xffffffffffffffff
        starts.append(va)
    starts.sort()
    return starts


def arm_exidx_function_starts(data, exidx_off, exidx_va, exidx_sz, code_lo, code_hi):
    """Parse .ARM.exidx (8-byte entries, prel31 fn ptr) -> sorted function-start VAs."""
    def prel31(v):
        v &= 0x7fffffff
        if v & 0x40000000:
            v -= 0x80000000
        return v

    starts = []
    for e in range(exidx_off, exidx_off + exidx_sz, 8):
        w0 = struct.unpack_from('<I', data, e)[0]
        if w0 & 0x80000000:          # not a prel31 function pointer
            continue
        entry_va = (e - exidx_off) + exidx_va
        fn = ((entry_va + prel31(w0)) & 0xffffffff) & ~1   # clear Thumb bit
        if code_lo <= fn < code_hi:
            starts.append(fn)
    return sorted(set(starts))


def func_start_before(starts, va):
    idx = bisect.bisect_right(starts, va) - 1
    return starts[idx] if idx >= 0 else None


# ─────────────────────────────────────────────
#  ARCH DETECTION (from the extracted binary itself)
# ─────────────────────────────────────────────

# EI_CLASS, e_machine -> engine key
EM_AARCH64 = 0xB7   # 183
EM_X86_64  = 0x3E   # 62
EM_ARM     = 0x28   # 40
EM_386     = 0x03   # 3


def detect_binary_arch(data):
    """Return one of: 'arm64', 'x86_64', 'arm', 'x86', or None (from ELF header)."""
    if data[:4] != b'\x7fELF':
        return None
    ei_class = data[4]          # 1=ELF32, 2=ELF64
    e_machine = struct.unpack_from('<H', data, 0x12)[0]
    if ei_class == 2 and e_machine == EM_AARCH64: return 'arm64'
    if ei_class == 2 and e_machine == EM_X86_64:  return 'x86_64'
    if ei_class == 1 and e_machine == EM_ARM:     return 'arm'
    if ei_class == 1 and e_machine == EM_386:     return 'x86'
    return None


def _load_capstone():
    try:
        import capstone  # noqa
        return capstone
    except ImportError:
        print("\033[91m[-] This architecture needs capstone.\033[0m")
        print("\033[93m[!] Install it with:  pip install capstone\033[0m")
        return None


# ─────────────────────────────────────────────
#  SHARED: choose the verify function from grouped references
# ─────────────────────────────────────────────

def select_verify_function(sc_refs, ss_refs, starts, label):
    """Group refs by enclosing function; keep functions that reference BOTH
    anchors; return the entry VA of the one whose two anchors sit closest
    together (the is_client?ssl_client:ssl_server select in
    session_verify_cert_chain). `starts` may be None (no unwind table) — then a
    synthetic grouping by proximity is used and the caller must resolve the
    prologue itself."""
    if not sc_refs or not ss_refs:
        print(f"\033[91m[-]\033[0m [{label}] Missing references to one or both anchors")
        return None, None

    if starts:
        grouped = defaultdict(lambda: [[], []])
        for a in sc_refs:
            f = func_start_before(starts, a)
            if f is not None:
                grouped[f][0].append(a)
        for a in ss_refs:
            f = func_start_before(starts, a)
            if f is not None:
                grouped[f][1].append(a)

        candidates = []
        for f, (scs, sss) in grouped.items():
            if scs and sss:
                gap = min(abs(a - b) for a in scs for b in sss)
                candidates.append((gap, f, scs, sss))
        if not candidates:
            print(f"\033[93m[!]\033[0m [{label}] No single function references both anchors; "
                  "falling back to nearest-pair prologue search")
            return None, _nearest_pair(sc_refs, ss_refs)
        candidates.sort()
        gap, f, scs, sss = candidates[0]
        print(f"\033[96m[*]\033[0m [{label}] {len(candidates)} function(s) reference both anchors; "
              f"selected entry {hex(f)} (anchor gap {hex(gap)})")
        if len(candidates) > 1:
            others = ', '.join(hex(c[1]) for c in candidates[1:])
            print(f"\033[96m[*]\033[0m [{label}] other both-anchor functions (likely helpers): {others}")
        return f, _nearest_pair(sc_refs, ss_refs)

    # No unwind table: return the nearest pair so caller can walk back a prologue.
    return None, _nearest_pair(sc_refs, ss_refs)


def _nearest_pair(sc_refs, ss_refs):
    best = None
    for a in sc_refs:
        for b in ss_refs:
            d = abs(a - b)
            if best is None or d < best[0]:
                best = (d, min(a, b))
    return best[1] if best else None


# ─────────────────────────────────────────────
#  ENGINE — ARM64 (ELF & Mach-O). Dependency-free.
# ─────────────────────────────────────────────

def scan_arm64(data, seg, base_vaddr, ssl_client, ssl_server, starts):
    code_foff, code_vaddr, code_filesz = seg['code']

    def foff_to_cv(fo):
        return fo - code_foff + code_vaddr

    def find_refs(target_va):
        lo12 = target_va & 0xfff
        refs = []
        for fi in range(code_foff, code_foff + code_filesz - 4, 4):
            instr = struct.unpack_from('<I', data, fi)[0]
            # ADD (immediate, 64-bit) with matching lo12
            if (instr & 0xffc00000) == 0x91000000 and ((instr >> 10) & 0xfff) == lo12:
                if fi >= 4:
                    adrp = struct.unpack_from('<I', data, fi - 4)[0]
                    if (adrp & 0x9f000000) == 0x90000000:  # ADRP
                        immlo = (adrp >> 29) & 0x3
                        immhi = (adrp >> 5) & 0x7ffff
                        imm = ((immhi << 2) | immlo) << 12
                        if imm & (1 << 32):
                            imm -= (1 << 33)
                        pc_va = foff_to_cv(fi - 4)
                        if (pc_va & ~0xfff) + imm == (target_va & ~0xfff):
                            refs.append(foff_to_cv(fi))
        return refs

    print("\033[96m[*]\033[0m [arm64] Scanning ADRP+ADD references ...")
    sc_refs = find_refs(ssl_client)
    ss_refs = find_refs(ssl_server)
    print(f"\033[96m[*]\033[0m [arm64] ssl_client refs: {[hex(x) for x in sc_refs]}")
    print(f"\033[96m[*]\033[0m [arm64] ssl_server refs: {[hex(x) for x in ss_refs]}")

    entry, nearest = select_verify_function(sc_refs, ss_refs, starts, 'arm64')
    if entry is not None:
        rva = entry - base_vaddr
        fo = entry - code_vaddr + code_foff
        print(f"\033[92m[+]\033[0m [arm64] SSL verify entry (RVA): \033[93m{hex(rva)}\033[0m")
        print(f"\033[92m[+]\033[0m [arm64] First bytes: {data[fo:fo+16].hex(' ')}")
        return rva

    # Fallback (no unwind table, e.g. iOS): walk back to a prologue.
    if nearest is None:
        return None
    start_fo = nearest - code_vaddr + code_foff
    for i in range(start_fo, max(code_foff, start_fo - 0x400), -4):
        instr = struct.unpack_from('<I', data, i)[0]
        is_sub_sp = (instr & 0xff8003ff) == 0xd10003ff              # SUB SP,SP,#imm
        is_stp_fp = (instr & 0xffe07fff) == 0xa9007bfd              # STP X29,X30,[SP,#imm]
        if is_sub_sp or is_stp_fp:
            entry = i
            # A standard framed prologue is `SUB SP,SP,#N ; STP X29,X30,...`.
            # If we matched the STP, back up to the SUB SP so we return the
            # true function entry (fixes the v3 off-by-one-instruction).
            if is_stp_fp and i - 4 >= code_foff:
                prev = struct.unpack_from('<I', data, i - 4)[0]
                if (prev & 0xff8003ff) == 0xd10003ff:
                    entry = i - 4
            rva = foff_to_cv(entry) - base_vaddr
            print(f"\033[92m[+]\033[0m [arm64] SSL verify offset (prologue fallback, RVA): \033[93m{hex(rva)}\033[0m")
            print(f"\033[92m[+]\033[0m [arm64] First bytes: {data[entry:entry+16].hex(' ')}")
            return rva
    print("\033[91m[-]\033[0m [arm64] Could not resolve verify function")
    return None


# ─────────────────────────────────────────────
#  ENGINE — x86_64 (ELF). Byte-scan RIP-relative LEA; needs capstone only for
#  the optional prologue fallback.
# ─────────────────────────────────────────────

def scan_x86_64(data, seg, base_vaddr, ssl_client, ssl_server, starts):
    code_foff, code_vaddr, code_filesz = seg['code']

    def find_lea_rip(target_va):
        """Scan for  REX.W 8D modrm(mod=00,rm=101) disp32  -> lea reg,[rip+disp32]."""
        hits = []
        lo = code_foff
        hi = code_foff + code_filesz - 7
        i = lo
        while i < hi:
            b0 = data[i]
            # REX with W set: 0x48,0x49,0x4C,0x4D (also plain-ish 0x4A/0x4B rare, include W-set only)
            if b0 in (0x48, 0x49, 0x4C, 0x4D) and data[i + 1] == 0x8D:
                modrm = data[i + 2]
                if (modrm & 0xC7) == 0x05:      # mod=00, rm=101 -> RIP-relative
                    disp = struct.unpack_from('<i', data, i + 3)[0]
                    insn_va = foff_to_cv(i)
                    if insn_va + 7 + disp == target_va:
                        hits.append(insn_va)
            i += 1
        return hits

    def foff_to_cv(fo):
        return fo - code_foff + code_vaddr

    print("\033[96m[*]\033[0m [x86_64] Scanning RIP-relative LEA references ...")
    sc_refs = find_lea_rip(ssl_client)
    ss_refs = find_lea_rip(ssl_server)
    print(f"\033[96m[*]\033[0m [x86_64] ssl_client refs: {[hex(x) for x in sc_refs]}")
    print(f"\033[96m[*]\033[0m [x86_64] ssl_server refs: {[hex(x) for x in ss_refs]}")

    entry, nearest = select_verify_function(sc_refs, ss_refs, starts, 'x86_64')
    if entry is not None:
        rva = entry - base_vaddr
        fo = entry - code_vaddr + code_foff
        print(f"\033[92m[+]\033[0m [x86_64] SSL verify entry (RVA): \033[93m{hex(rva)}\033[0m")
        print(f"\033[92m[+]\033[0m [x86_64] First bytes: {data[fo:fo+16].hex(' ')}")
        return rva

    # Fallback (no unwind table): find the enclosing function start by locating
    # the inter-function padding gap that precedes it. Clang aligns functions
    # and fills the gap with 0xCC (int3) or multi-byte NOPs, so the function
    # begins at the first byte after the last padding run before `nearest`.
    if nearest is None:
        return None
    ref_fo = nearest - code_vaddr + code_foff
    lo = max(code_foff, ref_fo - 0x800)

    def is_pad(i):
        b = data[i]
        if b == 0xCC:                       # int3 padding
            return True
        if b == 0x90:                       # nop
            return True
        if b == 0x66 and data[i+1:i+2] == b'\x90':   # 66 90
            return True
        if data[i:i+2] == b'\x0f\x1f':      # multi-byte nop
            return True
        return False

    # Prefer the nearest real prologue (a push of a callee-saved reg, or
    # endbr64) at/before the ref; fall back to the padding-gap boundary.
    entry_fo = None
    cs = _load_capstone()
    if cs is not None:
        md = cs.Cs(cs.CS_ARCH_X86, cs.CS_MODE_64)
        cand = None
        for insn in md.disasm(data[lo:ref_fo + 1], foff_to_cv(lo)):
            if insn.mnemonic == 'endbr64' or \
               (insn.mnemonic == 'push' and insn.op_str in ('rbp', 'rbx', 'r12', 'r13', 'r14', 'r15')):
                # start of a prologue = a push not immediately preceded by another push
                cand = insn.address
        # walk that candidate up to the first push of its push-cluster
        if cand is not None:
            cfo = cand - code_vaddr + code_foff
            # step backwards over contiguous single-byte/2-byte pushes
            while cfo - 1 >= lo:
                b = data[cfo - 1]
                if b in (0x55, 0x53):                     # push rbp / rbx
                    cfo -= 1
                elif data[cfo - 2:cfo] in (b'\x41\x54', b'\x41\x55', b'\x41\x56', b'\x41\x57'):
                    cfo -= 2                               # push r12..r15
                else:
                    break
            entry_fo = cfo

    if entry_fo is None:
        i = ref_fo - 1
        while i > lo:
            if is_pad(i):
                j = i
                while j >= lo and is_pad(j):
                    j -= 1
                entry_fo = j + 1
                break
            i -= 1

    if entry_fo is not None:
        rva = foff_to_cv(entry_fo) - base_vaddr
        print(f"\033[92m[+]\033[0m [x86_64] SSL verify offset (prologue fallback, RVA): \033[93m{hex(rva)}\033[0m")
        print(f"\033[92m[+]\033[0m [x86_64] First bytes: {data[entry_fo:entry_fo+16].hex(' ')}")
        return rva
    print("\033[91m[-]\033[0m [x86_64] Could not resolve verify function")
    return None


# ─────────────────────────────────────────────
#  ENGINE — armeabi-v7a (ELF32). Needs capstone.
#  MOVW/MOVT+ADD-PC and LDR-literal refs + PUSH{...,lr} prologue.
#  Flutter ARM32 is compiled as Thumb-2.
# ─────────────────────────────────────────────

def scan_arm32(data, seg, base_vaddr, ssl_client, ssl_server, starts):
    cs = _load_capstone()
    if cs is None:
        return None

    code_foff, code_vaddr, code_filesz = seg['code']
    startset = set(starts) if starts else set()

    def foff_to_cv(fo):
        return fo - code_foff + code_vaddr

    def align4(x):
        return x & ~3

    md = cs.Cs(cs.CS_ARCH_ARM, cs.CS_MODE_THUMB)   # disasm_lite -> low memory

    ldrpc_re = re.compile(r'^(\w+), \[pc, #(?:0x)?([0-9a-fA-F]+)\]$')
    imm_re   = re.compile(r'^(\w+), #(?:0x)?([0-9a-fA-F]+)$')

    # reg -> ('lit', signed_word) | ('movwt', value)
    regs = {}
    sc_refs, ss_refs = [], []

    print("\033[96m[*]\033[0m [armeabi-v7a] Streaming Thumb-2 disassembly (resync on data) ...")
    pos = code_vaddr
    end = code_vaddr + code_filesz
    guard = 0
    while pos < end:
        progressed = False
        start_fo = pos - code_vaddr + code_foff
        for (addr, size, mnem, ops) in md.disasm_lite(data[start_fo:end - code_vaddr + code_foff], pos):
            progressed = True
            if addr in startset:
                regs = {}
            if mnem in ('ldr', 'ldr.w'):
                m = ldrpc_re.match(ops)
                if m:
                    pool = align4(addr + 4) + int(m.group(2), 16)
                    fo = pool - code_vaddr + code_foff
                    if 0 <= fo <= len(data) - 4:
                        regs[m.group(1)] = ('lit', struct.unpack_from('<i', data, fo)[0])
                    else:
                        regs.pop(m.group(1), None)
                else:
                    regs.pop(ops.split(',')[0].strip(), None)
            elif mnem == 'movw':
                m = imm_re.match(ops)
                if m:
                    regs[m.group(1)] = ('movwt', int(m.group(2), 16) & 0xffff)
            elif mnem == 'movt':
                m = imm_re.match(ops)
                if m:
                    r = m.group(1)
                    cur = regs.get(r)
                    base = cur[1] if (cur and cur[0] == 'movwt') else 0
                    regs[r] = ('movwt', (base & 0xffff) | ((int(m.group(2), 16) & 0xffff) << 16))
            elif mnem in ('add', 'add.w'):
                parts = [p.strip() for p in ops.split(',')]
                if parts and parts[-1] == 'pc':
                    rd = parts[0]
                    cur = regs.get(rd)
                    if cur:
                        # Thumb ADD Rd,pc : PC = addr + 4 (NOT word-aligned)
                        tgt = (addr + 4 + cur[1]) & 0xffffffff
                        if tgt == ssl_client:
                            sc_refs.append(addr)
                        elif tgt == ssl_server:
                            ss_refs.append(addr)
                    regs.pop(rd, None)
            pos = addr + size
        if not progressed:
            pos += 2      # undecodable halfword -> resync
        else:
            pos += 2      # generator hit embedded data -> nudge past it
        guard += 1
        if guard > code_filesz:   # safety valve
            break

    print(f"\033[96m[*]\033[0m [armeabi-v7a] ssl_client refs: {[hex(x) for x in sc_refs]}")
    print(f"\033[96m[*]\033[0m [armeabi-v7a] ssl_server refs: {[hex(x) for x in ss_refs]}")

    entry, nearest = select_verify_function(sc_refs, ss_refs, starts, 'armeabi-v7a')
    if entry is not None:
        rva = entry - base_vaddr
        fo = entry - code_vaddr + code_foff
        print(f"\033[92m[+]\033[0m [armeabi-v7a] SSL verify entry (RVA): \033[93m{hex(rva)}\033[0m")
        print(f"\033[92m[+]\033[0m [armeabi-v7a] First bytes: {data[fo:fo+16].hex(' ')}")
        # Frida hooks module.base + rva; Interceptor handles the Thumb bit.
        return rva

    # Fallback: nearest ref -> walk back to PUSH {...,lr}
    if nearest is None:
        return None
    
    # Function starts: Thumb prologue PUSH {..., lr}
    push_lr = []
    fo_lo = max(code_foff, (nearest - code_vaddr + code_foff) - 0x400)
    fo_hi = (nearest - code_vaddr + code_foff) + 2
    for insn in md.disasm(data[fo_lo:fo_hi], foff_to_cv(fo_lo)):
        if insn.mnemonic in ('push', 'push.w') and 'lr' in insn.op_str:
            push_lr.append(insn.address)
    if push_lr:
        rva = push_lr[-1] - base_vaddr
        print(f"\033[92m[+]\033[0m [armeabi-v7a] SSL verify offset (prologue fallback, RVA): \033[93m{hex(rva)}\033[0m")
        return rva
    print("\033[91m[-]\033[0m [armeabi-v7a] Could not resolve verify function")
    return None


# ─────────────────────────────────────────────
#  ENGINE — x86 (ELF32). Same PIC idea as ARM32 but via the GOT/thunk; rare.
# ─────────────────────────────────────────────

def scan_x86_32(data, seg, base_vaddr, ssl_client, ssl_server, starts):
    print("\033[93m[!]\033[0m x86 (32-bit) uses call-thunk PIC (__x86.get_pc_thunk); static "
         "resolution is unreliable. Prefer x86_64, or hook dynamically with "
         "objection/frida. Skipping static analysis.")
    return None


# ─────────────────────────────────────────────
#  CORE — FIND SSL OFFSET (dispatches by architecture)
# ─────────────────────────────────────────────

def find_offset(binary_path, platform, arch=None):
    print(f"\033[96m[*]\033[0m Loading binary: {binary_path}")
    with open(binary_path, 'rb') as f:
        data = f.read()

    # ---- iOS: always arm64 Mach-O ----
    if platform == 'ios':
        seg, data = parse_macho_segments(data)
        if seg is None:
            print("\033[91m[-]\033[0m No executable Mach-O segment found")
            return None
        loads = seg['loads']
        base_vaddr = next((va for (off, va, sz) in loads if off == 0), 0)
        sc = [foff_to_vaddr(loads, m.start()) for m in re.finditer(b'ssl_client\x00', data)]
        ss = [foff_to_vaddr(loads, m.start()) for m in re.finditer(b'ssl_server\x00', data)]
        if not sc or not ss:
            print("\033[91m[-]\033[0m ssl_client/ssl_server strings not found in arm64 slice")
            return None
        print(f"\033[92m[+]\033[0m ssl_client @ {[hex(x) for x in sc]}")
        print(f"\033[92m[+]\033[0m ssl_server @ {[hex(x) for x in ss]}")
        return scan_arm64(data, seg, base_vaddr, sc[0], ss[0], None)

    # ---- Android: detect arch from the ELF header itself ----
    bin_arch = detect_binary_arch(data)
    if bin_arch is None:
        print("\033[91m[-] Unrecognised ELF machine type\033[0m")
        return None
    print(f"\033[96m[*]\033[0m Binary arch (from ELF header): \033[93m{bin_arch}\033[0m")

    if bin_arch in ('arm64', 'x86_64'):
        seg = parse_elf64_segments(data)
    else:
        seg = parse_elf32_segments(data)
    if seg is None:
        print("\033[91m[-]\033[0m No executable segment found")
        return None

    loads = seg['loads']
    base_vaddr = next((va for (off, va, sz) in loads if off == 0), 0)

    sc = [foff_to_vaddr(loads, m.start()) for m in re.finditer(b'ssl_client\x00', data)]
    ss = [foff_to_vaddr(loads, m.start()) for m in re.finditer(b'ssl_server\x00', data)]
    if not sc or not ss:
        print("\033[91m[-]\033[0m ssl_client/ssl_server strings not found — may not be a Flutter binary")
        return None
    print(f"\033[92m[+]\033[0m ssl_client @ {[hex(x) for x in sc]}")
    print(f"\033[92m[+]\033[0m ssl_server @ {[hex(x) for x in ss]}")

    code_foff, code_vaddr, code_filesz = seg['code']

    # Build exact function-start table from unwind info when present.
    starts = None
    if bin_arch in ('arm64', 'x86_64') and seg.get('eh_frame_hdr'):
        ho, hv, hs = seg['eh_frame_hdr']
        try:
            starts = eh_frame_function_starts(data, ho, hv)
            print(f"\033[92m[+]\033[0m Parsed .eh_frame_hdr: {len(starts)} function starts")
        except Exception as e:
            print(f"\033[93m[!]\033[0m .eh_frame_hdr parse failed ({e}); using prologue fallback")
            starts = None
    elif bin_arch == 'arm' and seg.get('arm_exidx'):
        eo, ev, es = seg['arm_exidx']
        starts = arm_exidx_function_starts(data, eo, ev, es,
                                           code_vaddr, code_vaddr + code_filesz)
        print(f"\033[92m[+]\033[0m Parsed .ARM.exidx: {len(starts)} function starts")

    if bin_arch == 'arm64':
        return scan_arm64(data, seg, base_vaddr, sc[0], ss[0], starts)
    elif bin_arch == 'x86_64':
        return scan_x86_64(data, seg, base_vaddr, sc[0], ss[0], starts)
    elif bin_arch == 'arm':
        return scan_arm32(data, seg, base_vaddr, sc[0], ss[0], starts)
    else:  # x86 (32-bit)
        return scan_x86_32(data, seg, base_vaddr, sc[0], ss[0], starts)


# ─────────────────────────────────────────────
#  FRIDA SCRIPT GENERATOR
# ─────────────────────────────────────────────

def write_frida_script(offset, package, platform, out_path, arch=None):
    # Module name is libflutter.so on ALL Android ABIs; Flutter on iOS.
    module_name = 'libflutter.so' if platform == 'android' else 'Flutter'
    arch_note = f" ({arch})" if arch else ""

    script = f"""// ================================================
// K!ll Fl!utter - Auto-generated Frida Script
// By: f3rb
// Platform : {platform.upper()}{arch_note}
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
            retval.replace(ptr("0x1"));
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
    frida_cmd = f'frida -U -f {package} -l "{script_path}"'
    del_443   = f'adb shell su -c "iptables -t nat -D OUTPUT -p tcp --dport 443 -j DNAT --to-destination {proxy}"'
    del_80    = f'adb shell su -c "iptables -t nat -D OUTPUT -p tcp --dport 80  -j DNAT --to-destination {proxy}"'

    print("")
    print(box_top())
    print(box_line("          ANDROID — COPY PASTE COMMANDS", C_YELLOW))
    print(box_bottom())
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
    frida_cmd = f'frida -U -f {package} -l "{script_path}"'
    set_443   = f'ssh root@{device_ip} "iptables -t nat -A OUTPUT -p tcp --dport 443 -j DNAT --to-destination {proxy}"'
    set_80    = f'ssh root@{device_ip} "iptables -t nat -A OUTPUT -p tcp --dport 80  -j DNAT --to-destination {proxy}"'
    del_443   = f'ssh root@{device_ip} "iptables -t nat -D OUTPUT -p tcp --dport 443 -j DNAT --to-destination {proxy}"'
    del_80    = f'ssh root@{device_ip} "iptables -t nat -D OUTPUT -p tcp --dport 80  -j DNAT --to-destination {proxy}"'

    print("")
    print(box_top())
    print(box_line("            iOS — COPY PASTE COMMANDS", C_YELLOW))
    print(box_bottom())
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


def print_summary(package, offset, script_path, proxy, platform, arch=None):
    print("")
    print(box_top())
    print(box_line(f"  Platform : {platform.upper()}", C_GREEN))
    if arch:
        print(box_line(f"  ABI      : {arch}", C_GREEN))
    print(box_line(f"  Package  : {package}", C_GREEN))
    print(box_line(f"  Offset   : {hex(offset)}", C_GREEN))
    print(box_line(f"  Script   : {os.path.basename(script_path)}", C_GREEN))
    print(box_line(f"  Proxy    : {proxy}", C_GREEN))
    print(box_bottom())
    print("")


# ─────────────────────────────────────────────
#  ONE ABI END-TO-END
# ─────────────────────────────────────────────

def process_android_abi(apk_path, out_dir, arch, package, platform, proxy):
    binary_path, real_arch = extract_flutter_android(apk_path, out_dir, arch)
    if not binary_path:
        return None
    offset = find_offset(binary_path, platform, real_arch)
    if offset is None:
        print(f"\033[91m[-]\033[0m [{real_arch}] Offset not found")
        return None
    script_path = os.path.join(out_dir, f'flutter_bypass_{real_arch}.js')
    write_frida_script(offset, package, platform, script_path, real_arch)
    return (real_arch, offset, script_path)


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
    parser.add_argument('--arch', choices=KNOWN_ABIS, help='Android ABI to target')
    parser.add_argument('--list-arch', action='store_true', help='List ABIs in the APK and exit')
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

    # --list-arch shortcut (Android only)
    if args.list_arch:
        if platform != 'android':
            print("\033[93m[!] --list-arch only applies to Android APKs\033[0m")
            sys.exit(0)
        arches = list_flutter_arches(app_path)
        if not arches:
            print("\033[91m[-] No libflutter.so found in this APK\033[0m")
        else:
            print("\033[92m[+]\033[0m ABIs bundled in this APK:")
            for a in sorted(arches):
                supported = "\033[92msupported\033[0m" if a in ('arm64-v8a', 'x86_64', 'armeabi-v7a') else "\033[93mlimited\033[0m"
                print(f"    - {a:<14} ({supported})")
        sys.exit(0)

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

    # Identifier
    if platform == 'android':
        package = get_package_name_android(app_path) \
            or input("\033[93m[?] Enter package name manually: \033[0m").strip()
        print(f"\033[92m[+]\033[0m Package: \033[93m{package}\033[0m")
    else:
        package = get_bundle_id_ios(app_path) \
            or input("\033[93m[?] Enter bundle ID manually (e.g. com.example.app): \033[0m").strip()
        print(f"\033[92m[+]\033[0m Bundle ID: \033[93m{package}\033[0m")

    # ---- Single ABI / iOS ----
    if platform == 'android':
        r = process_android_abi(app_path, out_dir, args.arch, package, platform, proxy)
        if not r:
            sys.exit(1)
        arch, offset, script_path = r
        print_commands_android(package, proxy, script_path)
        print_summary(package, offset, script_path, proxy, platform, arch)
    else:
        binary_path = extract_flutter_ios(app_path, out_dir)
        if not binary_path:
            sys.exit(1)
        offset = find_offset(binary_path, platform)
        if offset is None:
            sys.exit(1)
        script_path = os.path.join(out_dir, 'flutter_bypass.js')
        write_frida_script(offset, package, platform, script_path)
        print_commands_ios(package, proxy, script_path, device_ip)

    print_summary(package, offset, script_path, proxy, platform)


if __name__ == '__main__':
    main()

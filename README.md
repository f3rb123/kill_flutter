# K!ll Fl!utter 🔪

![K!ll Fl!utter](flutter.jpg)

> **Flutter SSL Pinning Bypass Tool — Android & iOS**  
> By [f3rb](https://github.com/f3rb)  
> For authorized penetration testing only

---

## The Problem

Flutter apps are notoriously difficult to intercept during penetration testing.
Unlike standard Android or iOS apps, Flutter bundles its own network stack —
**BoringSSL** — compiled directly into a native binary (`libflutter.so` on
Android, `Flutter.framework/Flutter` on iOS).

This means:

- ❌ Android Network Security Config is completely ignored
- ❌ Java-level SSL hooks (OkHttp, HttpURLConnection) don't exist
- ❌ iOS App Transport Security is bypassed
- ❌ System proxy settings are not respected
- ❌ Standard tools like Objection, SSL Kill Switch, and generic Frida scripts hook the wrong layer entirely

Even **reFlutter** — the most popular Flutter-specific bypass tool — relies on
a hardcoded database of known Flutter engine hashes. Any app built on a Flutter
version not in that database simply won't be patched correctly.

---

## The Solution

K!ll Fl!utter takes a fundamentally different approach. Instead of relying on
known patterns or version databases, it **derives the exact hook offset directly
from the binary itself** using three version-agnostic techniques:

### 1. String Anchors
Regardless of Flutter version or compiler, BoringSSL's SSL verification function
always references two strings: `ssl_client` and `ssl_server`. This is hardcoded
in BoringSSL's open source and will never change. These strings act as permanent
landmarks inside any Flutter binary.

### 2. ADRP+ADD Instruction Scan
ARM64 always loads string addresses using `ADRP+ADD` instruction pairs — this is
an architecture-level constant, not a Flutter-specific pattern. By scanning the
executable segment for these instruction pairs pointing to our landmark strings,
we precisely locate the function body in any binary regardless of version.

### 3. Prologue Walkback
ARM64 functions always begin with a stack setup instruction (`STP x29,x30` or
`SUB sp`) — an ABI requirement that never changes. Walking backwards from the
landmark hits the exact function start, giving us the offset to hook.

Once the offset is found, a Frida script is generated that intercepts
`ssl_crypto_x509_session_verify_cert_chain` at runtime, forcing it to always
return success — making the app trust any certificate including Burp's.

Since Flutter ignores system proxy settings, **iptables DNAT rules** are used
to transparently redirect all TCP 443/80 traffic to Burp at the kernel level,
bypassing Flutter's direct connection behavior entirely.

```
APK/IPA
  └── Extract Flutter binary (libflutter.so / Flutter.framework)
       └── Find ssl_client + ssl_server string anchors
            └── Scan ADRP+ADD instruction pairs in executable segment
                 └── Walk back to ARM64 function prologue
                      └── Offset found → Frida script generated
                           └── iptables DNAT → all traffic hits Burp ✓
```

---

## Why Other Tools Fail

| Tool | Approach | Why It Fails |
|---|---|---|
| Objection / SSL Kill Switch | Hooks Java/ObjC SSL layer | Flutter doesn't use this layer |
| Generic Frida scripts | Hardcoded byte patterns | Patterns change with every Flutter version |
| reFlutter | Patches APK from hash database | Database doesn't cover new Flutter versions |
| **K!ll Fl!utter** | **Dynamic binary analysis** | **Works on any Flutter version** |

---

## What Pinning Does It Bypass?

✅ Default Flutter `HttpClient` (dart:io) certificate validation  
✅ `dio` package SSL pinning  
✅ Custom certificate validators built on Flutter's HTTP stack  
✅ Any pinning that ultimately calls `ssl_crypto_x509_session_verify_cert_chain`  

❌ mTLS / client certificate pinning (server requires a client cert)  
❌ Native Android/iOS certificate pinning outside Flutter  
❌ Root / jailbreak detection (separate problem)  

---

## Requirements

| Requirement | Notes |
|---|---|
| Python 3 | Any recent version |
| `frida-tools` | `pip install frida-tools` |
| `aapt` | Android SDK build tools (Android only, for package name detection) |
| Rooted Android **or** Jailbroken iOS | Required for Frida + iptables |
| Burp Suite | Community or Pro |

---

## Installation

```bash
git clone https://github.com/f3rb/kill_flutter
cd kill_flutter
pip install frida-tools
```

---

## Usage

```bash
# Help
python3 kill_flutter.py -h

# Android APK
python3 kill_flutter.py app.apk -i 192.168.1.10 -p 8080

# iOS IPA
python3 kill_flutter.py app.ipa -i 192.168.1.10 -p 8080 --device-ip 192.168.1.50

# Custom output directory
python3 kill_flutter.py app.apk -i 192.168.1.10 -o /tmp/pentest

# Force platform (if extension is ambiguous)
python3 kill_flutter.py app.apk --platform android -i 192.168.1.10
```

---

## Options

| Flag | Description | Default |
|---|---|---|
| `app` | Path to APK or IPA | required |
| `-i, --ip` | Your machine IP address | `<YOUR_IP>` |
| `-p, --port` | Burp Suite listener port | `8080` |
| `-o, --output` | Output directory for generated files | App directory |
| `--platform` | Force platform: `android` or `ios` | auto-detected |
| `--device-ip` | iOS device IP for SSH iptables | `<DEVICE_IP>` |
| `-h, --help` | Show help | — |

---

## Output

The tool generates everything needed in one run:

- `flutter_bypass.js` — Ready-to-use Frida script with offset baked in
- Copy-paste iptables commands (Android via adb / iOS via SSH)
- Copy-paste Frida launch command with package name auto-filled

```
[*] Platform : ANDROID
[+] Package  : com.example.flutterapp
[+] ssl_client @ ['0x1bb68a']
[+] ssl_server @ ['0x1c4cb0']
[*] Scanning ADRP+ADD refs... (may take a moment)
[+] SSL verify offset: 0x73ee8c
[+] Frida script saved: /path/to/flutter_bypass.js

[1] Set iptables on device:
  adb shell su -c "iptables -t nat -A OUTPUT -p tcp --dport 443 -j DNAT --to-destination 192.168.1.10:8080"
  adb shell su -c "iptables -t nat -A OUTPUT -p tcp --dport 80  -j DNAT --to-destination 192.168.1.10:8080"

[2] Verify iptables rules:
  adb shell su -c "iptables -t nat -L OUTPUT --line-numbers"

[3] Launch Frida:
  frida -U -f com.example.flutterapp --no-pause -l "/path/to/flutter_bypass.js"

[4] Revert iptables when done:
  adb shell su -c "iptables -t nat -D OUTPUT -p tcp --dport 443 -j DNAT --to-destination 192.168.1.10:8080"
  adb shell su -c "iptables -t nat -D OUTPUT -p tcp --dport 80  -j DNAT --to-destination 192.168.1.10:8080"
```

---

## Burp Suite Setup

1. Proxy → Listeners → Add listener on port `8080`
2. Bind address → **All interfaces** (`0.0.0.0`)
3. Request handling → ✅ **Support invisible proxying**
4. Intercept → **Off**

---

## Revert

**Android:**
```bash
adb shell su -c "iptables -t nat -D OUTPUT -p tcp --dport 443 -j DNAT --to-destination <IP>:8080"
adb shell su -c "iptables -t nat -D OUTPUT -p tcp --dport 80  -j DNAT --to-destination <IP>:8080"
# or just:
adb reboot
```

**iOS:**
```bash
ssh root@<device-ip> "iptables -t nat -D OUTPUT -p tcp --dport 443 -j DNAT --to-destination <IP>:8080"
ssh root@<device-ip> "iptables -t nat -D OUTPUT -p tcp --dport 80  -j DNAT --to-destination <IP>:8080"
# or just reboot the device
```

---

## How It Works — Technical Deep Dive

Flutter's `libflutter.so` / `Flutter.framework` is a fully stripped binary —
no symbols, no debug info. The SSL verification function
`ssl_crypto_x509_session_verify_cert_chain` cannot be found by name.

**Step 1 — String anchors:**  
BoringSSL source always has:
```c
const char *peer = SSL_is_server(ssl) ? "ssl_client" : "ssl_server";
```
These strings exist in every Flutter binary ever compiled. We find their
file offsets using a simple byte scan.

**Step 2 — ELF/Mach-O segment parsing:**  
ARM64 instructions encode virtual addresses, not file offsets. We parse
the binary's segment headers to build a file-offset ↔ virtual-address
mapping so our instruction scan produces correct results.

**Step 3 — ADRP+ADD scan:**  
We scan the executable segment for `ADD` instructions whose immediate
value matches the low 12 bits of our string virtual addresses, then verify
the preceding `ADRP` instruction targets the correct 4KB page. This gives
us the exact code locations that load both strings.

**Step 4 — Prologue walkback:**  
We walk backwards from the co-located string references until we hit a
function prologue instruction (`STP x29,x30` or `SUB sp`). This is the
first instruction of `ssl_crypto_x509_session_verify_cert_chain` —
the offset we bake into the Frida script.

**Step 5 — Frida hook:**
```javascript
var addr = m.base.add(offset);  // ASLR base + fixed offset
Interceptor.attach(addr, {
    onLeave: function(retval) {
        retval.replace(0x1);    // always return success
    }
});
```

**Step 6 — iptables redirect:**  
Flutter opens TCP connections directly, ignoring system proxy.
Kernel-level DNAT intercepts all outgoing 443/80 traffic and
redirects to Burp regardless of what the app does.

---

## References

- [NVISO — Intercepting Flutter Traffic](https://blog.nviso.eu/2022/08/18/intercept-flutter-traffic-on-ios-and-android-http-https-dio-pinning/)
- [MindedSecurity — Bypassing Certificate Pinning on Flutter](https://blog.mindedsecurity.com/2024/05/bypassing-certificate-pinning-on.html)
- [reFlutter](https://github.com/ptswarm/reFlutter)
- [BoringSSL Source — ssl_x509.cc](https://github.com/google/boringssl/blob/master/ssl/ssl_x509.cc)

---

## Disclaimer

This tool is intended for **authorized security testing only**.  
Only use on applications you have explicit written permission to test.  
The author is not responsible for any misuse or damage caused by this tool.

---

## Author

**f3rb** — Offensive Security | Mobile Pentesting | Tool Development

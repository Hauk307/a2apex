import subprocess, sys

result = subprocess.run(["dig", "@8.8.8.8", "a2apex.io", "A", "+short"], 
                       capture_output=True, text=True, timeout=10)
ip = result.stdout.strip()
if ip:
    print(f"DNS RESOLVED: a2apex.io -> {ip}")
    sys.exit(0)
else:
    print("DNS still propagating...")
    sys.exit(1)

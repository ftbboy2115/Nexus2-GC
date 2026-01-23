#!/usr/bin/env python3
"""
Schwab OAuth Auto-Auth Script

Run locally to re-authenticate Schwab API with zero manual code extraction.

Usage:
    python scripts/schwab_auth.py [--vps-url http://100.113.178.7:8000]

What it does:
1. Fetches auth URL from VPS
2. Opens browser for Schwab login
3. Captures OAuth callback automatically
4. Sends code to VPS
5. Verifies authentication
"""

import argparse
import http.server
import ssl
import socket
import threading
import webbrowser
import urllib.parse
import sys
import ipaddress
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# Default VPS URL
DEFAULT_VPS_URL = "http://100.113.178.7:8000"


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handle OAuth callback and extract authorization code."""
    
    code = None
    error = None
    
    def do_GET(self):
        """Handle GET request from OAuth redirect."""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        if "code" in params:
            CallbackHandler.code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: green;">&#10004; Authorization Successful!</h1>
                <p>Code captured. You can close this window.</p>
                <p style="color: gray;">Sending to VPS...</p>
                </body></html>
            """)
        elif "error" in params:
            CallbackHandler.error = params.get("error_description", ["Unknown error"])[0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(f"""
                <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: red;">&#10008; Authorization Failed</h1>
                <p>{CallbackHandler.error}</p>
                </body></html>
            """.encode())
        else:
            self.send_response(400)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def create_self_signed_cert():
    """Create temporary self-signed cert for HTTPS callback using Python cryptography."""
    import tempfile
    
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime
    except ImportError:
        print("      Note: Install 'cryptography' package for HTTPS support")
        return None, None
    
    # Generate private key
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    
    # Generate certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
        datetime.datetime.utcnow() + datetime.timedelta(days=1)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]),
        critical=False,
    ).sign(key, hashes.SHA256())
    
    # Write to temp files
    cert_dir = tempfile.mkdtemp()
    cert_file = Path(cert_dir) / "cert.pem"
    key_file = Path(cert_dir) / "key.pem"
    
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_file, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    return cert_file, key_file


def run_callback_server(port=8443, use_https=True, timeout_seconds=300):
    """Run local callback server to capture OAuth code."""
    import time
    
    server_address = ("127.0.0.1", port)
    httpd = http.server.HTTPServer(server_address, CallbackHandler)
    httpd.timeout = 5  # 5 second timeout per request
    
    if use_https:
        cert_file, key_file = create_self_signed_cert()
        if cert_file and key_file:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(str(cert_file), str(key_file))
            httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        else:
            print("Warning: Could not create SSL cert, using HTTP (may not work)")
            use_https = False
    
    print(f"Callback server listening on {'https' if use_https else 'http'}://127.0.0.1:{port}")
    print(f"      Waiting for callback (timeout: {timeout_seconds}s)...")
    
    # Loop until we get the code or timeout
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            httpd.handle_request()
            if CallbackHandler.code or CallbackHandler.error:
                break
        except Exception as e:
            # Ignore SSL handshake errors (browser cert warnings)
            continue
    
    httpd.server_close()
    
    return CallbackHandler.code, CallbackHandler.error


def main():
    parser = argparse.ArgumentParser(description="Schwab OAuth Auto-Auth")
    parser.add_argument("--vps-url", default=DEFAULT_VPS_URL, help="VPS base URL")
    parser.add_argument("--port", type=int, default=8443, help="Local callback port")
    args = parser.parse_args()
    
    print("=" * 50)
    print("Schwab Auto-Auth Script")
    print("=" * 50)
    
    # Step 1: Get auth URL from VPS
    print("\n[1/4] Fetching auth URL from VPS...")
    try:
        resp = httpx.get(f"{args.vps_url}/warrior/schwab/auth-url", timeout=10)
        auth_data = resp.json()
        auth_url = auth_data.get("auth_url") or auth_data.get("url")
        if not auth_url:
            print(f"ERROR: No auth URL in response: {auth_data}")
            return 1
        print(f"      Got auth URL")
    except Exception as e:
        print(f"ERROR: Failed to get auth URL: {e}")
        return 1
    
    # Step 2: Start callback server in background
    print("\n[2/4] Starting local callback server...")
    server_thread = threading.Thread(target=lambda: None)  # Placeholder
    
    # Step 3: Open browser
    print("\n[3/4] Opening browser for Schwab login...")
    print("      Please log in and authorize the app.")
    webbrowser.open(auth_url)
    
    # Run callback server (blocks until callback received)
    code, error = run_callback_server(port=args.port)
    
    if error:
        print(f"\nERROR: Authorization failed: {error}")
        return 1
    
    if not code:
        print("\nERROR: No authorization code received")
        return 1
    
    print(f"\n      Code captured: {code[:20]}...")
    
    # Step 4: Exchange code on VPS
    print("\n[4/4] Exchanging code on VPS...")
    try:
        resp = httpx.post(
            f"{args.vps_url}/warrior/schwab/callback",
            params={"code": code},
            timeout=30
        )
        result = resp.json()
        
        if result.get("success") or result.get("authenticated") or result.get("status") == "authenticated":
            print("\n" + "=" * 50)
            print("SUCCESS! Schwab is now authenticated.")
            print("=" * 50)
            return 0
        else:
            print(f"\nERROR: Code exchange failed: {result}")
            return 1
    except Exception as e:
        print(f"\nERROR: Failed to exchange code: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

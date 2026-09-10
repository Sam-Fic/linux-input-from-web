"""LAN address discovery and startup QR output."""

import socket


def get_lan_ip():
    """Get LAN IP via UDP socket trick (no traffic actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def print_startup_qr(qr_url: str) -> None:
    import qrcode

    qr = qrcode.QRCode(box_size=1, border=1)
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    print()

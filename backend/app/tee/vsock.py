"""Phase 12 (v)sock transport framing for the Nitro Enclave boundary.

Wire format (explicit length-prefixed framing):
    frame = uint32 BE payload_length + payload bytes

Rules:
- Partial reads/writes are handled by looping until the exact byte count
  is transferred (sockets may return short counts).
- Oversized frames (> max_bytes) are rejected BEFORE allocating the
  payload buffer (DoS guard).
- Malformed headers, truncated streams and invalid payloads raise
  FrameError subclasses -- never return partial/corrupt plaintext.
- No payload bytes are ever logged; errors carry sizes only.

On real Nitro hardware the same framing runs over AF_VSOCK sockets to
the enclave CID:port. Locally (no /dev/nsm, no AF_VSOCK peer) the
provider uses an in-process loopback transport that exercises the
identical encode/decode path without hardware.
"""

import socket
import struct

FRAME_HEADER_LEN = 4
DEFAULT_MAX_FRAME_BYTES = 256 * 1024  # 256 KiB -- far above our ~1 KiB payloads

# Default Nitro vsock endpoint (overridable via NITRO_CID / NITRO_PORT).
DEFAULT_CID = 16
DEFAULT_PORT = 5000


class FrameError(ValueError):
    """Base class for framing failures."""


class FrameTooLargeError(FrameError):
    """Declared payload length exceeds the configured maximum."""


class TruncatedFrameError(FrameError):
    """Stream closed before the declared payload arrived."""


class MalformedFrameError(FrameError):
    """Header/payload violates the framing contract."""


class NitroTransportError(RuntimeError):
    """Vsock transport unavailable/failed (hardware-only path)."""


def encode_frame(payload: bytes, max_bytes: int = DEFAULT_MAX_FRAME_BYTES) -> bytes:
    """Encode one frame: 4-byte BE length prefix + payload."""
    if not isinstance(payload, (bytes, bytearray)):
        raise MalformedFrameError("frame payload must be bytes")
    payload = bytes(payload)
    if len(payload) == 0:
        raise MalformedFrameError("frame payload must not be empty")
    if len(payload) > max_bytes:
        raise FrameTooLargeError(
            f"frame payload size {len(payload)} exceeds maximum {max_bytes}"
        )
    return struct.pack(">I", len(payload)) + payload


def decode_one_frame(
    buf: bytes | bytearray, max_bytes: int = DEFAULT_MAX_FRAME_BYTES
) -> tuple[bytes, int]:
    """Decode a single frame from the head of `buf`.

    Returns (payload, bytes_consumed). Raises TruncatedFrameError when
    `buf` holds a partial frame, MalformedFrameError on bad headers and
    FrameTooLargeError when the declared length exceeds max_bytes.
    """
    buf = bytes(buf)
    if len(buf) < FRAME_HEADER_LEN:
        raise TruncatedFrameError(
            f"incomplete frame header: have {len(buf)} of {FRAME_HEADER_LEN} bytes"
        )
    (declared,) = struct.unpack(">I", buf[:FRAME_HEADER_LEN])
    if declared == 0:
        raise MalformedFrameError("frame declares zero-length payload")
    if declared > max_bytes:
        raise FrameTooLargeError(
            f"frame declares {declared} bytes, maximum is {max_bytes}"
        )
    if len(buf) - FRAME_HEADER_LEN < declared:
        raise TruncatedFrameError(
            f"incomplete frame payload: have {len(buf) - FRAME_HEADER_LEN} "
            f"of {declared} bytes"
        )
    return buf[FRAME_HEADER_LEN : FRAME_HEADER_LEN + declared], FRAME_HEADER_LEN + declared


def _send_all(sock, data: bytes) -> None:
    """Loop socket.send until all bytes are written (partial-write safe)."""
    view = memoryview(data)
    while view:
        try:
            sent = sock.send(view)
        except socket.timeout as exc:
            raise NitroTransportError("vsock send timed out") from exc
        except OSError as exc:
            raise NitroTransportError(f"vsock send failed: {exc}") from exc
        if sent <= 0:
            raise NitroTransportError("vsock send returned zero (peer closed)")
        view = view[sent:]


def _recv_exact(sock, nbytes: int) -> bytes:
    """Loop socket.recv until exactly nbytes arrive (partial-read safe)."""
    chunks: list[bytes] = []
    remaining = nbytes
    while remaining > 0:
        try:
            chunk = sock.recv(remaining)
        except socket.timeout as exc:
            raise TruncatedFrameError(
                f"vsock recv timed out with {remaining} of {nbytes} bytes pending"
            ) from exc
        except OSError as exc:
            raise NitroTransportError(f"vsock recv failed: {exc}") from exc
        if not chunk:
            raise TruncatedFrameError(
                f"peer closed with {remaining} of {nbytes} bytes pending"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def send_frame(sock, payload: bytes, max_bytes: int = DEFAULT_MAX_FRAME_BYTES) -> None:
    """Frame + send one message, handling partial writes."""
    _send_all(sock, encode_frame(payload, max_bytes))


def recv_frame(sock, max_bytes: int = DEFAULT_MAX_FRAME_BYTES) -> bytes:
    """Receive + validate one framed message, handling partial reads."""
    header = _recv_exact(sock, FRAME_HEADER_LEN)
    try:
        (declared,) = struct.unpack(">I", header)
    except struct.error as exc:
        raise MalformedFrameError("frame header is not a uint32 length") from exc
    if declared == 0:
        raise MalformedFrameError("frame declares zero-length payload")
    if declared > max_bytes:
        raise FrameTooLargeError(
            f"frame declares {declared} bytes, maximum is {max_bytes}"
        )
    payload = _recv_exact(sock, declared)
    if len(payload) != declared:
        raise TruncatedFrameError("short frame payload")
    return payload


def open_vsock_socket(cid: int = DEFAULT_CID, port: int = DEFAULT_PORT,
                      timeout: float = 5.0):
    """Open an AF_VSOCK socket to the enclave (hardware-only).

    Raises NitroTransportError on non-Nitro hosts (no AF_VSOCK support or
    no enclave peer). Callers MUST surface this error -- never silently
    fall back to demo mode.
    """
    if not hasattr(socket, "AF_VSOCK"):
        raise NitroTransportError(
            "AF_VSOCK is unavailable on this host; a real Nitro Enclave "
            "peer (EC2 Nitro host) is required for vsock transport"
        )
    try:
        sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
    except OSError as exc:
        raise NitroTransportError(f"AF_VSOCK socket creation failed: {exc}") from exc
    sock.settimeout(timeout)
    try:
        sock.connect((cid, port))
    except OSError as exc:
        sock.close()
        raise NitroTransportError(
            f"vsock connect to CID {cid} port {port} failed: {exc}. "
            "Requires a running Nitro Enclave image on EC2."
        ) from exc
    return sock


def socketpair_transport():
    """In-process byte-stream pair exercising the same framing code.

    Used by the loopback transport and by tests (including partial
    read/write behaviour via small chunk sizes). Not a hardware path.
    """
    return socket.socketpair()

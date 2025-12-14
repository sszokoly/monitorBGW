#!/usr/bin/env python3
"""
Async HTTP server that receives file uploads via PUT/POST requests.
Compatible with Python 3.6+

Usage:
    python3 upload_server.py [--host HOST] [--port PORT] [--dir DIRECTORY]

Client upload examples:
    curl -T gwcapture.pcap http://10.10.10.1:8080/gwcapture.pcap
    curl -X PUT --data-binary @gwcapture.pcap http://10.10.10.1:8080/gwcapture.pcap
    wget --method=PUT --body-file=gwcapture.pcap http://10.10.10.1:8080/gwcapture.pcap
"""

import asyncio
import argparse
import os
import sys
from urllib.parse import unquote
from datetime import datetime


class FileUploadProtocol(asyncio.Protocol):
    def __init__(self, upload_dir):
        self.upload_dir = upload_dir
        self.transport = None
        self.buffer = b""
        self.headers = {}
        self.method = None
        self.path = None
        self.content_length = 0
        self.headers_complete = False
        self.body = b""

    def connection_made(self, transport):
        self.transport = transport
        peername = transport.get_extra_info("peername")
        print(
            f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] '
            f"Connection from {peername[0]}:{peername[1]}"
        )

    def data_received(self, data):
        self.buffer += data

        if not self.headers_complete:
            # Check if we have complete headers
            if b"\r\n\r\n" in self.buffer:
                header_end = self.buffer.index(b"\r\n\r\n")
                header_data = self.buffer[:header_end].decode(
                    "utf-8", errors="ignore"
                )
                self.body = self.buffer[header_end + 4 :]
                self.headers_complete = True

                # Parse request line and headers
                lines = header_data.split("\r\n")
                request_line = lines[0].split()

                if len(request_line) >= 2:
                    self.method = request_line[0]
                    self.path = unquote(request_line[1])

                # Parse headers
                for line in lines[1:]:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        self.headers[key.strip().lower()] = value.strip()

                self.content_length = int(self.headers.get("content-length", 0))
        else:
            # Accumulate body data
            self.body += data

        # Check if we have complete body
        if self.headers_complete and len(self.body) >= self.content_length:
            self.handle_request()

    def handle_request(self):
        if self.method in ["PUT", "POST"]:
            self.handle_upload()
        else:
            self.send_response(
                405,
                "Method Not Allowed",
                "Only PUT and POST methods are supported",
            )

    def handle_upload(self):
        # Extract filename from path
        filename = os.path.basename(self.path.lstrip("/"))

        if not filename:
            self.send_response(
                400, "Bad Request", "Filename must be specified in URL path"
            )
            return

        # Sanitize filename
        filename = filename.replace("..", "").replace("/", "").replace("\\", "")

        if not filename:
            self.send_response(400, "Bad Request", "Invalid filename")
            return

        # Save file
        filepath = os.path.join(self.upload_dir, filename)

        try:
            with open(filepath, "wb") as f:
                f.write(self.body[: self.content_length])

            file_size = len(self.body[: self.content_length])
            print(
                f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] '
                f"Saved: {filename} ({file_size} bytes)"
            )

            self.send_response(
                201,
                "Created",
                f"File {filename} uploaded successfully "
                f"({file_size} bytes)",
            )
        except Exception as e:
            print(
                f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] '
                f"Error saving {filename}: {e}"
            )
            self.send_response(
                500, "Internal Server Error", f"Error saving file: {str(e)}"
            )

    def send_response(self, status_code, status_text, message):
        response_body = f"{message}\n".encode("utf-8")
        response = (
            f"HTTP/1.1 {status_code} {status_text}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Content-Length: {len(response_body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("utf-8") + response_body

        self.transport.write(response)
        self.transport.close()

    def connection_lost(self, exc):
        pass


async def run_server(host, port, upload_dir):
    loop = asyncio.get_event_loop()

    # Create upload directory if it doesn't exist
    os.makedirs(upload_dir, exist_ok=True)

    server = await loop.create_server(
        lambda: FileUploadProtocol(upload_dir), host, port
    )

    print(f"File upload server running on http://{host}:{port}")
    print(f"Upload directory: {os.path.abspath(upload_dir)}")
    print(f"\nUpload files using:")
    print(f"  curl -T file.pcap http://{host}:{port}/file.pcap")
    print(
        f"  curl -X PUT --data-binary @file.pcap http://{host}:{port}/file.pcap"
    )
    print(f"\nPress Ctrl+C to stop\n")

    # Python 3.6 compatible - wait forever
    await asyncio.Event().wait()


def main():
    parser = argparse.ArgumentParser(
        description="Async HTTP file upload server"
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port to bind to (default: 8080)"
    )
    parser.add_argument(
        "--dir",
        default="./uploads",
        help="Upload directory (default: ./uploads)",
    )

    args = parser.parse_args()

    try:
        asyncio.run(run_server(args.host, args.port, args.dir))
    except AttributeError:
        # Python 3.6 compatibility - asyncio.run() doesn't exist
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(run_server(args.host, args.port, args.dir))
        except KeyboardInterrupt:
            print("\nServer stopped")
        finally:
            loop.close()


if __name__ == "__main__":
    main()

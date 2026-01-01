#!/usr/bin/env python
# -*- encoding: utf-8 -*-

"""
Async HTTP server that receives file uploads via PUT/POST requests.
Compatible with Python 3.6+

Examples:
    curl -T mg.pcap http://10.10.10.1:8080/mg.pcap
    curl -X PUT --data-binary @mg.pcap http://10.10.10.1:8080/mg.pcap
    wget --method=PUT --body-file=gwcapture.pcap http://10.10.10.1:8080/mg.pcap
"""

############################## BEGIN IMPORTS #################################

import asyncio
import os
from urllib.parse import unquote
from utils import logger, config
from asyncio import Queue
from datetime import datetime

############################## END IMPORTS ###################################
############################## BEGIN CLASSES #################################

class FileUploadProtocol(asyncio.Protocol):
    def __init__(self, upload_dir, upload_queue):
        self.upload_dir = upload_dir
        self.upload_queue = upload_queue if upload_queue else Queue()
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
        logger.info(f"Connection from {peername[0]}:{peername[1]}")
        
        if peername:
            self.remote_ip = peername[0]
        else:
            self.remote_ip = None

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
        if not self.path:
            self.send_response(400, "Bad Request", "Filename missing")
            return

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
            logger.info(f"Received {filename} ({file_size} bytes) via HTTP")

            item = {
                "remote_ip": self.remote_ip,
                "filename": filename,
                "file_size": file_size,
                "received_timestamp": datetime.now()
            }
            
            self.upload_queue.put_nowait(item)
            logger.info(f"Put {item} in upload_queue")
            
            self.send_response(
                201,
                "Created",
                f"File {filename} uploaded successfully "
                f"({file_size} bytes)",
            )
        except Exception as e:
            logger.error(f"Error saving {filename}: {e}")
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

        if self.transport:
            self.transport.write(response)
            self.transport.close()

    def connection_lost(self, exc):
        logger.info(f"Connection lost {exc}")
        pass

############################## END CLASSES ###################################
############################## BEGIN FUNCTIONS ###############################

async def start_http_server(host, port, upload_dir, upload_queue):
    loop = asyncio.get_event_loop()

    try:
        os.makedirs(upload_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"{e} while creating {upload_dir}")
    
    server = await loop.create_server(
        lambda: FileUploadProtocol(upload_dir, upload_queue), host, port
    )

    logger.info(f"HTTP server started on http://{host}:{port}")
    logger.info(f"Upload directory: {os.path.abspath(upload_dir)}")

    try:
        # wait forever
        await asyncio.Event().wait()

    except asyncio.CancelledError:
        logger.info("HTTP server task cancelled")
        raise

    finally:
        server.close()
        await server.wait_closed()
        logger.info("HTTP server closed")

############################## END FUNCTIONS #################################

if __name__ == "__main__":
    from utils import asyncio_run
    
    port = config.get("http_port", 8080)
    host = "0.0.0.0"
    upload_dir = config.get("upload_dir", "./")
        
    asyncio_run(start_http_server(host, port, upload_dir))

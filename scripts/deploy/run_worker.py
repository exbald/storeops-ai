"""Cloud Run Worker Entrypoint (T11 / AC-41).

Runs the StoreOps asynchronous worker loop while binding an HTTP listener
on $PORT to satisfy Cloud Run Services lifecycle and health probe requirements.

Security Architecture:
This worker service is strictly private:
- Ingress is restricted to internal traffic only (INGRESS_TRAFFIC_INTERNAL_ONLY).
- Public access is denied (--no-allow-unauthenticated).
- Only authorized callers (Cloud Tasks / Cloud Scheduler via storeops-invoker-sa)
  possessing roles/run.invoker can reach this service via Google IAM OIDC tokens.
- Perimeter authentication and network isolation are enforced at the Google Cloud Run
  infrastructure layer; this container-internal HTTP shim provides port binding and health
  probes without redundant in-container token verification.
"""

import asyncio
import json
import logging
import os
import signal

from apps.api.core.config import settings
from apps.api.worker import run_worker_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("storeops.cloud_worker")


async def _handle_http_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Minimal HTTP request handler for Cloud Run container lifecycle health checks."""
    try:
        request_line = await reader.readline()
        if not request_line:
            writer.close()
            return

        _method, _path, _version = request_line.decode("utf-8", errors="ignore").split(maxsplit=2)

        # Consume remaining HTTP headers
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break

        body = json.dumps({
            "status": "READY",
            "service": "storeops-worker",
            "profile": settings.profile,
        }).encode("utf-8")

        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n".encode()
            + b"Connection: close\r\n"
            b"\r\n"
            + body
        )
        writer.write(response)
        await writer.drain()
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    except (OSError, ValueError) as exc:
        logger.warning("HTTP handler error: %s", exc)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except OSError:
            pass


async def main():
    port = int(os.getenv("PORT", "8001"))
    host = "0.0.0.0"

    logger.info("Starting Cloud Run Worker HTTP server on %s:%d...", host, port)
    server = await asyncio.start_server(_handle_http_client, host, port)

    logger.info("Starting background worker outbox polling loop...")
    worker_task = asyncio.create_task(run_worker_loop())

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    async with server:
        server_task = asyncio.create_task(server.serve_forever())
        wait_stop = asyncio.create_task(stop_event.wait())

        _done, pending = await asyncio.wait(
            [server_task, worker_task, wait_stop],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Worker gracefully stopped.")

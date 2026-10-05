import subprocess
import sys


processes = [
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--port",
            "8001",
        ]
    ),

    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.workers.research_worker",
        ]
    ),

    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.messaging.outbox_publisher",
        ]
    ),
]


try:
    for process in processes:
        process.wait()

except KeyboardInterrupt:
    print("\nStopping Research Service processes...")

    for process in processes:
        process.terminate()

    for process in processes:
        process.wait()
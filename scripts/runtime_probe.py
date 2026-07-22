"""Probe the thin runtime from inside the container image."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import subprocess
import zipfile
from pathlib import Path

FLINK_LIB = Path("/opt/flink/lib")
SERIALIZER = FLINK_LIB / "interaction-serializer.jar"
KAFKA_CONNECTOR = FLINK_LIB / "flink-sql-connector-kafka-5.0.0-2.2.jar"
SERIALIZER_CLASS = "io/extendedotel/flink/FirstColumnStringSerializationSchema.class"


def main() -> int:
    probe = Path("/opt/application/.runtime-probe")
    probe.write_text("ok", encoding="ascii")
    probe.unlink()
    java = subprocess.run(
        ["java", "-XshowSettings:properties", "-version"],
        check=True,
        capture_output=True,
        text=True,
    )
    with zipfile.ZipFile(SERIALIZER) as archive:
        bytecode = archive.read(SERIALIZER_CLASS)
    class_major_version = int.from_bytes(bytecode[6:8], byteorder="big")
    output = {
        "effective_uid": os.geteuid(),
        "effective_gid": os.getegid(),
        "java_11": "java.version = 11." in java.stderr,
        "python": platform.python_version(),
        "pyflink": importlib.metadata.version("apache-flink"),
        "kafka_connector_present": KAFKA_CONNECTOR.is_file(),
        "serializer_present": SERIALIZER.is_file(),
        "serializer_class_major_version": class_major_version,
        "application_path_writable": os.access("/opt/application", os.W_OK),
    }
    print(json.dumps(output, sort_keys=True))
    if not all(
        (
            output["java_11"],
            output["python"] == "3.12.13",
            output["pyflink"] == "2.2.1",
            output["kafka_connector_present"],
            output["serializer_present"],
            output["serializer_class_major_version"] == 55,
            output["application_path_writable"],
        )
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

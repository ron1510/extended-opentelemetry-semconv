from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from uuid import uuid4

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

KIND_NODE_IMAGE = "kindest/node:v1.32.2"
REDPANDA_CHART_VERSION = "26.1.3"
NAMESPACE = "servicegraph-e2e"


@dataclass
class PortForward:
    process: subprocess.Popen[str]
    local_port: int

    def close(self) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


@dataclass
class E2EEnvironment:
    root: Path
    work_dir: Path
    cluster_name: str = field(default_factory=lambda: f"servicegraph-e2e-{uuid4().hex[:8]}")
    namespace: str = NAMESPACE
    port_forwards: list[PortForward] = field(default_factory=lambda: list[PortForward]())

    @property
    def kubeconfig(self) -> Path:
        return self.work_dir / "kubeconfig"

    @property
    def image_suffix(self) -> str:
        return self.cluster_name.removeprefix("servicegraph-e2e-")

    @property
    def flink_image(self) -> str:
        return f"extended-otel-flink-runtime:e2e-{self.image_suffix}"

    @property
    def ui_repository(self) -> str:
        return "extended-otel-servicegraph-ui"

    @property
    def ui_tag(self) -> str:
        return f"e2e-{self.image_suffix}"

    @property
    def ui_image(self) -> str:
        return f"{self.ui_repository}:{self.ui_tag}"

    def provision(self) -> None:
        self._announce("checking local prerequisites")
        self._check_prerequisites()
        self._announce("building Flink and UI images from the current checkout")
        self._build_images()
        self._announce(f"creating Kind cluster {self.cluster_name}")
        self.run(
            [
                "kind",
                "create",
                "cluster",
                "--name",
                self.cluster_name,
                "--image",
                KIND_NODE_IMAGE,
                "--kubeconfig",
                str(self.kubeconfig),
                "--wait",
                "5m",
            ],
            timeout=600,
            include_kubeconfig=False,
        )
        self._announce("loading project images into Kind")
        for image in (self.flink_image, self.ui_image):
            self.run(
                ["kind", "load", "docker-image", image, "--name", self.cluster_name],
                timeout=900,
                include_kubeconfig=False,
            )
        self.kubectl("create", "namespace", self.namespace)
        self._announce("installing Redpanda and creating topics")
        self._install_redpanda()
        self._announce("installing Collector, Flink, and UI charts")
        self._install_project()
        self._announce("disposable environment is ready")

    def cleanup(self) -> None:
        for forward in reversed(self.port_forwards):
            forward.close()
        self.port_forwards.clear()
        self.run(
            ["kind", "delete", "cluster", "--name", self.cluster_name],
            timeout=300,
            check=False,
            include_kubeconfig=False,
        )
        self.run(
            ["docker", "image", "rm", self.flink_image, self.ui_image],
            timeout=120,
            check=False,
            include_kubeconfig=False,
        )
        self.kubeconfig.unlink(missing_ok=True)

    def diagnostics(self) -> str:
        commands = (
            ["get", "pods", "-o", "wide"],
            ["get", "jobs"],
            ["get", "events", "--sort-by=.metadata.creationTimestamp"],
            ["logs", "deployment/processing-servicegraph-flink-jobmanager", "--tail=200"],
            ["logs", "deployment/processing-servicegraph-flink-taskmanager", "--tail=200"],
            ["logs", "deployment/servicegraph-collector-router", "--tail=100"],
            ["logs", "statefulset/servicegraph-collector-backend", "--tail=100"],
            ["logs", "deployment/servicegraph-ui", "--tail=100"],
        )
        sections: list[str] = []
        for command in commands:
            result = self.kubectl(*command, check=False, timeout=60)
            sections.append(f"$ kubectl {' '.join(command)}\n{result.stdout}{result.stderr}")
        return "\n\n".join(sections)

    def start_port_forward(self, resource: str, remote_port: int) -> str:
        local_port = _free_port()
        command = [
            "kubectl",
            "port-forward",
            "--namespace",
            self.namespace,
            resource,
            f"{local_port}:{remote_port}",
            "--address",
            "127.0.0.1",
        ]
        process = subprocess.Popen(
            command,
            cwd=self.root,
            env=self.command_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        forward = PortForward(process=process, local_port=local_port)
        self.port_forwards.append(forward)

        def ready() -> bool:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout is not None else ""
                raise RuntimeError(f"port-forward exited with {process.returncode}: {output}")
            try:
                with socket.create_connection(("127.0.0.1", local_port), timeout=1):
                    return True
            except OSError:
                return False

        wait_for(f"port-forward {resource}", 30, ready)
        return f"http://127.0.0.1:{local_port}"

    def get_json(self, url: str) -> JsonValue:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=5) as response:
            return cast(JsonValue, json.loads(response.read()))

    def kafka_records(self, topic: str) -> list[tuple[str, str]]:
        command = [
            "kubectl",
            "exec",
            "--namespace",
            self.namespace,
            "streaming-0",
            "-c",
            "redpanda",
            "--",
            "rpk",
            "-X",
            "brokers=streaming:9093",
            "topic",
            "consume",
            topic,
            "-o",
            "start",
            "--format",
            "%k\\t%v\\n",
        ]
        process = subprocess.Popen(
            command,
            cwd=self.root,
            env=self.command_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            stdout, _ = process.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                stdout, _ = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, _ = process.communicate(timeout=5)
        records: list[tuple[str, str]] = []
        for line in stdout.splitlines():
            if "\t" not in line:
                continue
            key, value = line.split("\t", maxsplit=1)
            records.append((key, value))
        return records

    def kubectl(
        self,
        *args: str,
        timeout: int = 120,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return self.run(
            ["kubectl", "--namespace", self.namespace, *args],
            timeout=timeout,
            check=check,
        )

    @property
    def command_environment(self) -> dict[str, str]:
        return {**os.environ, "KUBECONFIG": str(self.kubeconfig)}

    def run(
        self,
        command: Sequence[str],
        *,
        timeout: int,
        check: bool = True,
        include_kubeconfig: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        environment = self.command_environment if include_kubeconfig else os.environ.copy()
        result = subprocess.run(
            command,
            cwd=self.root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if check and result.returncode != 0:
            rendered = subprocess.list2cmdline(list(command))
            raise RuntimeError(f"command failed ({result.returncode}): {rendered}\n{result.stdout}{result.stderr}")
        return result

    def _check_prerequisites(self) -> None:
        missing = [command for command in ("docker", "kind", "kubectl", "helm") if shutil.which(command) is None]
        if missing:
            raise RuntimeError(f"missing E2E prerequisites: {', '.join(missing)}")
        self.run(["docker", "version"], timeout=30, include_kubeconfig=False)

    def _announce(self, message: str) -> None:
        print(f"[servicegraph-e2e] {message}", flush=True)

    def _build_images(self) -> None:
        build_arguments: list[str] = []
        for name in ("PIP_INDEX_URL", "PIP_TRUSTED_HOST", "NPM_CONFIG_REGISTRY"):
            value = os.getenv(name)
            if value:
                build_arguments.extend(["--build-arg", f"{name}={value}"])
        maven_settings = os.getenv("MAVEN_SETTINGS")
        maven_secret = ["--secret", f"id=maven_settings,src={maven_settings}"] if maven_settings else []
        self.run(
            [
                "docker",
                "build",
                "--tag",
                self.flink_image,
                "--file",
                "apps/otel-servicegraph-diff/Dockerfile",
                *build_arguments,
                *maven_secret,
                ".",
            ],
            timeout=1800,
            include_kubeconfig=False,
        )
        self.run(
            [
                "docker",
                "build",
                "--tag",
                self.ui_image,
                "--file",
                "apps/servicegraph-ui/Dockerfile",
                *build_arguments,
                ".",
            ],
            timeout=1200,
            include_kubeconfig=False,
        )

    def _install_redpanda(self) -> None:
        self.run(
            ["helm", "repo", "add", "redpanda", "https://charts.redpanda.com", "--force-update"],
            timeout=120,
        )
        self.run(["helm", "repo", "update", "redpanda"], timeout=300)
        self.run(
            [
                "helm",
                "upgrade",
                "--install",
                "streaming",
                "redpanda/redpanda",
                "--version",
                REDPANDA_CHART_VERSION,
                "--namespace",
                self.namespace,
                "--set",
                "statefulset.replicas=1",
                "--set",
                "statefulset.podAntiAffinity.type=soft",
                "--set",
                "console.enabled=false",
                "--set",
                "external.enabled=false",
                "--set",
                "tls.enabled=false",
                "--set",
                "tuning.tune_aio_events=false",
                "--set",
                "tests.enabled=false",
                "--set",
                "storage.persistentVolume.size=2Gi",
                "--set",
                "storage.persistentVolume.storageClass=standard",
                "--set",
                "config.cluster.default_topic_replications=1",
                "--wait",
                "--timeout",
                "10m",
            ],
            timeout=660,
        )
        self._create_topic("otel.servicegraph.metrics")
        self._create_topic("graph.elements.events", cleanup_policy="compact")

    def _create_topic(self, topic: str, *, cleanup_policy: str | None = None) -> None:
        command = [
            "exec",
            "streaming-0",
            "-c",
            "redpanda",
            "--",
            "rpk",
            "-X",
            "brokers=streaming:9093",
            "topic",
            "create",
            topic,
        ]
        if cleanup_policy is not None:
            command.extend(("--config", f"cleanup.policy={cleanup_policy}"))
        deadline = time.monotonic() + 120
        while True:
            result = self.kubectl(*command, check=False)
            output = f"{result.stdout}\n{result.stderr}"
            if result.returncode == 0 or "already exists" in output.casefold():
                return
            if time.monotonic() >= deadline:
                rendered = subprocess.list2cmdline(["kubectl", *command])
                raise RuntimeError(f"topic creation did not become ready: {rendered}\n{output}")
            time.sleep(2)

    def _install_project(self) -> None:
        self.run(
            [
                "helm",
                "upgrade",
                "--install",
                "collection",
                "deploy/helm/servicegraph-collector",
                "--namespace",
                self.namespace,
                "--set",
                "fullnameOverride=servicegraph-collector",
                "--set",
                "streamContract.kafka.brokers[0]=streaming:9093",
                "--set",
                "streamContract.kafka.security.protocol=PLAINTEXT",
                "--wait",
                "--timeout",
                "5m",
            ],
            timeout=360,
        )
        self.run(
            [
                "helm",
                "upgrade",
                "--install",
                "processing",
                "deploy/helm/servicegraph-flink",
                "--namespace",
                self.namespace,
                "--set",
                f"image.ref={self.flink_image}",
                "--set",
                "image.pullPolicy=IfNotPresent",
                "--set",
                "application.parallelism=1",
                "--set",
                "application.jobManagerReplicas=1",
                "--set",
                "application.taskManagerReplicas=1",
                "--set",
                "application.taskManagerSlots=1",
                "--set",
                "streamContract.kafka.brokers[0]=streaming:9093",
                "--set",
                "streamContract.kafka.security.protocol=PLAINTEXT",
                "--set",
                "storage.storageClassName=standard",
                "--set",
                "storage.size=2Gi",
                "--set",
                "storage.accessModes[0]=ReadWriteOnce",
                "--set",
                "podSecurityContext.runAsUser=9999",
                "--set",
                "podSecurityContext.runAsGroup=9999",
                "--set",
                "podSecurityContext.fsGroup=9999",
                "--set",
                "job.interactionTtlSeconds=15",
                "--set",
                "job.allowedLatenessSeconds=2",
                "--set",
                "job.stateTtlSeconds=60",
                "--set",
                "job.checkpointIntervalMs=5000",
                "--wait",
                "--timeout",
                "10m",
            ],
            timeout=660,
        )
        self.run(
            [
                "helm",
                "upgrade",
                "--install",
                "visualization",
                "deploy/helm/servicegraph-ui",
                "--namespace",
                self.namespace,
                "--set",
                "fullnameOverride=servicegraph-ui",
                "--set",
                f"image.repository={self.ui_repository}",
                "--set",
                f"image.tag={self.ui_tag}",
                "--set",
                "image.pullPolicy=IfNotPresent",
                "--set",
                "streamContract.kafka.brokers[0]=streaming:9093",
                "--set",
                "streamContract.kafka.security.protocol=PLAINTEXT",
                "--set",
                "streamContract.kafka.security.existingSecret=",
                "--wait",
                "--timeout",
                "5m",
            ],
            timeout=360,
        )


def wait_for[T](description: str, timeout_seconds: int, probe: Callable[[], T | None | bool]) -> T:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = probe()
            if result:
                return cast(T, result)
        except (AssertionError, json.JSONDecodeError, OSError, urllib.error.URLError) as exc:
            last_error = exc
        time.sleep(2)
    detail = f": {last_error}" if last_error is not None else ""
    raise AssertionError(f"timed out waiting for {description}{detail}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])

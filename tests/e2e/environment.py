# pyright: reportUnknownMemberType=false

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

from kafka import KafkaAdminClient, KafkaProducer
from kafka.admin import NewTopic

# kafka-python-ng exposes dynamic producer future and admin response types.

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

KIND_NODE_IMAGE = "kindest/node:v1.32.2"
REDPANDA_IMAGE = "docker.redpanda.com/redpandadata/redpanda:v26.1.6"
ELASTICSEARCH_IMAGE = "docker.elastic.co/elasticsearch/elasticsearch:8.15.5"
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
    elasticsearch_host_url: str | None = field(default=None, init=False)
    kafka_host_address: str | None = field(default=None, init=False)
    port_forwards: list[PortForward] = field(default_factory=lambda: list[PortForward](), init=False)

    @property
    def kubeconfig(self) -> Path:
        return self.work_dir / "kubeconfig"

    @property
    def suffix(self) -> str:
        return self.cluster_name.removeprefix("servicegraph-e2e-")

    @property
    def access_image(self) -> str:
        return f"extended-otel-servicegraph-access:e2e-{self.suffix}"

    @property
    def elasticsearch_container(self) -> str:
        return f"servicegraph-es-{self.suffix}"

    @property
    def redpanda_container(self) -> str:
        return f"servicegraph-kafka-{self.suffix}"

    @property
    def command_environment(self) -> dict[str, str]:
        return {**os.environ, "KUBECONFIG": str(self.kubeconfig)}

    def provision(self) -> None:
        self._announce("checking local prerequisites")
        self._check_prerequisites()
        self._announce("building the access production image")
        self._build_access_image()
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
        self.run(
            ["kind", "load", "docker-image", self.access_image, "--name", self.cluster_name],
            timeout=600,
            include_kubeconfig=False,
        )
        self.kubectl("create", "namespace", self.namespace)
        self._announce("starting Docker Redpanda and Elasticsearch")
        self._start_elasticsearch()
        self._start_redpanda()
        self._announce("installing the access Helm chart")
        self._install_access()
        self._announce("focused projector environment is ready")

    def cleanup(self) -> None:
        for forward in reversed(self.port_forwards):
            forward.close()
        self.port_forwards.clear()
        self.run(
            ["docker", "rm", "--force", self.elasticsearch_container, self.redpanda_container],
            timeout=120,
            check=False,
            include_kubeconfig=False,
        )
        self.run(
            ["kind", "delete", "cluster", "--name", self.cluster_name],
            timeout=300,
            check=False,
            include_kubeconfig=False,
        )
        self.run(
            ["docker", "image", "rm", self.access_image],
            timeout=120,
            check=False,
            include_kubeconfig=False,
        )
        self.kubeconfig.unlink(missing_ok=True)

    def diagnostics(self) -> str:
        sections: list[str] = []
        for command in (
            ["get", "pods", "-o", "wide"],
            ["get", "jobs"],
            ["get", "events", "--sort-by=.metadata.creationTimestamp"],
            ["logs", "deployment/servicegraph-access-projector", "--tail=200"],
            ["logs", "deployment/servicegraph-access-api", "--tail=200"],
        ):
            result = self.kubectl(*command, check=False, timeout=60)
            sections.append(f"$ kubectl {' '.join(command)}\n{result.stdout}{result.stderr}")
        for container in (self.redpanda_container, self.elasticsearch_container):
            result = self.run(
                ["docker", "logs", "--tail", "100", container],
                timeout=60,
                check=False,
                include_kubeconfig=False,
            )
            sections.append(f"$ docker logs {container}\n{result.stdout}{result.stderr}")
        return "\n\n".join(sections)

    def produce_events(self, events: Sequence[dict[str, object]]) -> None:
        address = self.kafka_host_address
        if address is None:
            raise RuntimeError("Redpanda host address is not initialized")
        producer = KafkaProducer(
            bootstrap_servers=address,
            key_serializer=_serialize_key,
            value_serializer=_serialize_event,
        )
        try:
            for event in events:
                producer.send("graph.elements.events", key=cast(str, event["element_id"]), value=event).get(timeout=30)
            producer.flush(timeout=30)
        finally:
            producer.close(timeout=10)

    def committed_offset(self) -> int:
        address = self.kafka_host_address
        if address is None:
            raise RuntimeError("Redpanda host address is not initialized")
        admin = KafkaAdminClient(bootstrap_servers=address)
        try:
            offsets = admin.list_consumer_group_offsets("servicegraph-elasticsearch-projector")
            return max((metadata.offset for metadata in offsets.values()), default=0)
        finally:
            admin.close()

    def elasticsearch_sources(self) -> list[dict[str, JsonValue]]:
        url = self.elasticsearch_host_url
        if url is None:
            raise RuntimeError("Elasticsearch host URL is not initialized")
        with urllib.request.urlopen(f"{url}/servicegraph-elements/_search?size=500", timeout=5) as response:
            document = cast(dict[str, JsonValue], json.loads(response.read()))
        hits_section = cast(dict[str, JsonValue], document["hits"])
        hits = cast(list[JsonValue], hits_section["hits"])
        return [cast(dict[str, JsonValue], cast(dict[str, JsonValue], hit)["_source"]) for hit in hits]

    def start_api_port_forward(self) -> str:
        local_port = _free_port()
        process = subprocess.Popen(
            [
                "kubectl",
                "port-forward",
                "--namespace",
                self.namespace,
                "service/servicegraph-access-api",
                f"{local_port}:8080",
                "--address",
                "127.0.0.1",
            ],
            cwd=self.root,
            env=self.command_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        forward = PortForward(process, local_port)
        self.port_forwards.append(forward)

        def ready() -> bool:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout is not None else ""
                raise RuntimeError(f"API port-forward failed: {output}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{local_port}/health/ready", timeout=2) as response:
                    return response.status == 200
            except urllib.error.URLError:
                return False

        wait_for("access API port-forward", 30, ready)
        return f"http://127.0.0.1:{local_port}"

    def post_json(self, url: str, document: dict[str, object]) -> dict[str, JsonValue]:
        request = urllib.request.Request(
            url,
            data=json.dumps(document).encode(),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return cast(dict[str, JsonValue], json.loads(response.read()))

    def kubectl(
        self,
        *args: str,
        timeout: int = 120,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return self.run(["kubectl", "--namespace", self.namespace, *args], timeout=timeout, check=check)

    def run(
        self,
        command: Sequence[str],
        *,
        timeout: int,
        check: bool = True,
        include_kubeconfig: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            command,
            cwd=self.root,
            env=self.command_environment if include_kubeconfig else os.environ.copy(),
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

    def _build_access_image(self) -> None:
        build_arguments: list[str] = []
        for name in ("PIP_INDEX_URL", "PIP_TRUSTED_HOST"):
            if value := os.getenv(name):
                build_arguments.extend(("--build-arg", f"{name}={value}"))
        self.run(
            [
                "docker",
                "build",
                "--tag",
                self.access_image,
                "--file",
                "apps/servicegraph-access/Dockerfile",
                *build_arguments,
                ".",
            ],
            timeout=1200,
            include_kubeconfig=False,
        )

    def _start_elasticsearch(self) -> None:
        port = _free_port()
        self.run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                self.elasticsearch_container,
                "--network",
                "kind",
                "--publish",
                f"127.0.0.1:{port}:9200",
                "--env",
                "discovery.type=single-node",
                "--env",
                "xpack.security.enabled=false",
                "--env",
                "ES_JAVA_OPTS=-Xms512m -Xmx512m",
                ELASTICSEARCH_IMAGE,
            ],
            timeout=180,
            include_kubeconfig=False,
        )
        self.elasticsearch_host_url = f"http://127.0.0.1:{port}"
        self._expose_container("servicegraph-elasticsearch", self.elasticsearch_container, 9200)

    def _start_redpanda(self) -> None:
        port = _free_port()
        internal_host = f"servicegraph-redpanda.{self.namespace}.svc"
        self.run(
            [
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                self.redpanda_container,
                "--network",
                "kind",
                "--publish",
                f"127.0.0.1:{port}:19092",
                REDPANDA_IMAGE,
                "redpanda",
                "start",
                "--mode",
                "dev-container",
                "--smp",
                "1",
                "--memory",
                "512M",
                "--reserve-memory",
                "0M",
                "--node-id",
                "0",
                "--check=false",
                "--kafka-addr",
                "internal://0.0.0.0:9092,external://0.0.0.0:19092",
                "--advertise-kafka-addr",
                f"internal://{internal_host}:9092,external://127.0.0.1:{port}",
            ],
            timeout=180,
            include_kubeconfig=False,
        )
        self.kafka_host_address = f"127.0.0.1:{port}"
        self._expose_container("servicegraph-redpanda", self.redpanda_container, 9092)
        wait_for("Redpanda", 120, self._create_topic)

    def _create_topic(self) -> bool:
        address = self.kafka_host_address
        if address is None:
            return False
        try:
            admin = KafkaAdminClient(bootstrap_servers=address, request_timeout_ms=5_000)
            try:
                topic = NewTopic(
                    "graph.elements.events",
                    1,
                    1,
                    topic_configs={"cleanup.policy": "compact"},
                )
                admin.create_topics((topic,))
            finally:
                admin.close()
            return True
        except Exception:
            return False

    def _expose_container(self, service_name: str, container: str, port: int) -> None:
        address = self.run(
            ["docker", "inspect", "--format", "{{(index .NetworkSettings.Networks \"kind\").IPAddress}}", container],
            timeout=30,
            include_kubeconfig=False,
        ).stdout.strip()
        if not address:
            raise RuntimeError(f"{container} has no address on the Kind network")
        self._apply_json(
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": service_name, "namespace": self.namespace},
                "spec": {"ports": [{"name": "tcp", "port": port, "targetPort": port}]},
            }
        )
        self._apply_json(
            {
                "apiVersion": "discovery.k8s.io/v1",
                "kind": "EndpointSlice",
                "metadata": {
                    "name": service_name,
                    "namespace": self.namespace,
                    "labels": {"kubernetes.io/service-name": service_name},
                },
                "addressType": "IPv4",
                "ports": [{"name": "tcp", "protocol": "TCP", "port": port}],
                "endpoints": [{"addresses": [address]}],
            }
        )

    def _apply_json(self, manifest: dict[str, object]) -> None:
        result = subprocess.run(
            ["kubectl", "apply", "--filename", "-"],
            cwd=self.root,
            env=self.command_environment,
            input=json.dumps(manifest),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"failed to apply test resource: {result.stdout}{result.stderr}")

    def _install_access(self) -> None:
        self.run(
            [
                "helm",
                "upgrade",
                "--install",
                "access",
                "deploy/helm/servicegraph-access",
                "--namespace",
                self.namespace,
                "--set",
                "fullnameOverride=servicegraph-access",
                "--set",
                "image.repository=extended-otel-servicegraph-access",
                "--set",
                f"image.tag=e2e-{self.suffix}",
                "--set",
                "image.pullPolicy=IfNotPresent",
                "--set",
                "elasticsearch.urls[0]=http://servicegraph-elasticsearch:9200",
                "--set",
                "elasticsearch.numberOfReplicas=0",
                "--set",
                "elasticsearch.auth.existingSecret=",
                "--set",
                "elasticsearch.tls.existingSecret=",
                "--set",
                "api.elasticsearchPageSize=1",
                "--set",
                "streamContract.kafka.brokers[0]=servicegraph-redpanda:9092",
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

    @staticmethod
    def _announce(message: str) -> None:
        print(f"[servicegraph-e2e] {message}", flush=True)


def wait_for[T](description: str, timeout_seconds: int, probe: Callable[[], T | None | bool]) -> T:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = probe()
            if result:
                return cast(T, result)
        except (AssertionError, json.JSONDecodeError, OSError, urllib.error.URLError) as error:
            last_error = error
        time.sleep(2)
    detail = f": {last_error}" if last_error is not None else ""
    raise AssertionError(f"timed out waiting for {description}{detail}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _serialize_key(value: object) -> bytes:
    return cast(str, value).encode()


def _serialize_event(value: object) -> bytes:
    return json.dumps(cast(dict[str, object], value), separators=(",", ":")).encode()

"""Validated visualization service settings."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, StringConstraints, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TopicName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[A-Za-z0-9._-]+$")]


class KafkaSecurityProtocol(StrEnum):
    PLAINTEXT = "PLAINTEXT"
    SASL_SSL = "SASL_SSL"


class VisualizationConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="forbid", frozen=True)

    kafka_bootstrap_servers: NonEmptyString = Field(
        default="kafka:9092",
        validation_alias="KAFKA_BOOTSTRAP_SERVERS",
    )
    kafka_security_protocol: KafkaSecurityProtocol = Field(
        default=KafkaSecurityProtocol.PLAINTEXT,
        validation_alias="KAFKA_SECURITY_PROTOCOL",
    )
    kafka_sasl_mechanism: str | None = Field(default=None, validation_alias="KAFKA_SASL_MECHANISM")
    kafka_sasl_username: NonEmptyString | None = Field(default=None, validation_alias="KAFKA_SASL_USERNAME")
    kafka_sasl_password: SecretStr | None = Field(default=None, validation_alias="KAFKA_SASL_PASSWORD")
    kafka_ssl_ca_file: Path | None = Field(default=None, validation_alias="KAFKA_SSL_CA_FILE")
    kafka_ssl_endpoint_identification_algorithm: str = Field(
        default="https",
        pattern=r"^https$",
        validation_alias="KAFKA_SSL_ENDPOINT_IDENTIFICATION_ALGORITHM",
    )
    topic: TopicName = Field(
        default="graph.interactions.events",
        validation_alias="SERVICEGRAPH_UI_INPUT_TOPIC",
    )
    group_id: TopicName = Field(
        default="servicegraph-visualization",
        validation_alias="SERVICEGRAPH_UI_GROUP_ID",
    )
    database_path: Path = Field(
        default=Path("/data/servicegraph.db"),
        validation_alias="SERVICEGRAPH_UI_DATABASE_PATH",
    )
    recent_event_limit: int = Field(default=1_000, ge=10, le=100_000, validation_alias="SERVICEGRAPH_UI_EVENT_LIMIT")
    static_dir: Path = Field(default=Path("/app/static"), validation_alias="SERVICEGRAPH_UI_STATIC_DIR")

    @model_validator(mode="after")
    def validate_kafka_security(self) -> VisualizationConfig:
        if self.kafka_security_protocol is KafkaSecurityProtocol.SASL_SSL:
            if self.kafka_sasl_mechanism != "SCRAM-SHA-256":
                raise ValueError("SASL_SSL requires SCRAM-SHA-256")
            if self.kafka_sasl_username is None or self.kafka_sasl_password is None:
                raise ValueError("SASL username and password are required when Kafka uses SASL_SSL")
            if self.kafka_ssl_ca_file is None:
                raise ValueError("CA file is required when Kafka uses SASL_SSL")
        elif any(
            value is not None
            for value in (
                self.kafka_sasl_mechanism,
                self.kafka_sasl_username,
                self.kafka_sasl_password,
                self.kafka_ssl_ca_file,
            )
        ):
            raise ValueError("Kafka authentication and TLS fields require SASL_SSL")
        return self

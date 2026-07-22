from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from otel_servicegraph_diff.config import (
    InteractionDiffConfig,
    KafkaSaslMechanism,
    KafkaSecurityProtocol,
)


def test_config_rejects_state_ttl_that_can_preempt_business_expiry() -> None:
    with pytest.raises(ValidationError):
        InteractionDiffConfig(
            interaction_ttl_seconds=300,
            allowed_lateness_seconds=60,
            state_ttl_seconds=360,
        )


def test_config_rejects_invalid_topic_name() -> None:
    with pytest.raises(ValidationError):
        InteractionDiffConfig(output_topic="contains spaces")


def test_config_rejects_non_positive_parallelism() -> None:
    with pytest.raises(ValidationError):
        InteractionDiffConfig(parallelism=0)


def test_plaintext_config_has_only_explicit_security_protocol() -> None:
    config = InteractionDiffConfig()

    assert config.kafka_client_properties == {"security.protocol": "PLAINTEXT"}


def test_sasl_ssl_config_builds_complete_kafka_properties() -> None:
    config = InteractionDiffConfig(
        kafka_security_protocol=KafkaSecurityProtocol.SASL_SSL,
        kafka_sasl_mechanism=KafkaSaslMechanism.SCRAM_SHA_256,
        kafka_sasl_username='service"graph',
        kafka_sasl_password=SecretStr('pass\\word'),
        kafka_ssl_ca_file=Path("/etc/kafka/tls/ca.crt"),
    )

    assert config.kafka_client_properties == {
        "security.protocol": "SASL_SSL",
        "sasl.mechanism": "SCRAM-SHA-256",
        "sasl.jaas.config": (
            "org.apache.flink.kafka.shaded.org.apache.kafka.common.security.scram.ScramLoginModule required "
            'username="service\\"graph" password="pass\\\\word";'
        ),
        "ssl.truststore.location": "/etc/kafka/tls/ca.crt",
        "ssl.truststore.type": "PEM",
        "ssl.endpoint.identification.algorithm": "https",
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"kafka_security_protocol": "SASL_SSL"}, "SASL mechanism"),
        (
            {
                "kafka_security_protocol": "SASL_SSL",
                "kafka_sasl_mechanism": "SCRAM-SHA-256",
            },
            "username and password",
        ),
        (
            {
                "kafka_security_protocol": "SASL_SSL",
                "kafka_sasl_mechanism": "SCRAM-SHA-256",
                "kafka_sasl_username": "user",
                "kafka_sasl_password": "secret",
            },
            "CA file",
        ),
        ({"kafka_ssl_ca_file": "/tmp/ca.crt"}, "require SASL_SSL"),
    ],
)
def test_config_rejects_incomplete_or_inconsistent_kafka_security(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        InteractionDiffConfig.model_validate(overrides)

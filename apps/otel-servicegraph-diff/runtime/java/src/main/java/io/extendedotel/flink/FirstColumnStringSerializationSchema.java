package io.extendedotel.flink;

import java.nio.charset.StandardCharsets;
import org.apache.flink.api.common.serialization.SerializationSchema;
import org.apache.flink.types.Row;

/** Serializes the interaction ID from the first field of a two-column sink row. */
public final class FirstColumnStringSerializationSchema implements SerializationSchema<Row> {
    private static final long serialVersionUID = 1L;

    @Override
    public byte[] serialize(final Row element) {
        return requiredString(element, 0).getBytes(StandardCharsets.UTF_8);
    }

    private static String requiredString(final Row element, final int fieldIndex) {
        final Object value = element.getField(fieldIndex);
        if (!(value instanceof String)) {
            throw new IllegalArgumentException(
                    "Kafka sink row field " + fieldIndex + " must be a non-empty string");
        }
        final String stringValue = (String) value;
        if (stringValue.isEmpty()) {
            throw new IllegalArgumentException(
                    "Kafka sink row field " + fieldIndex + " must be a non-empty string");
        }
        return stringValue;
    }
}

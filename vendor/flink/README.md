# Flink Runtime Artifacts

The runtime image includes `flink-sql-connector-kafka-5.0.0-2.2.jar`, the
official shaded Kafka runtime JAR matched to Apache Flink 2.2.x. PyFlink uses
it for the DataStream `KafkaSource` and `KafkaSink`; it does not require Kafka
Connect.

Kafka's compression codecs are optional runtime dependencies and are not
embedded in the shaded connector. The checked-in codec JARs match the Kafka
4.2.0 client used by connector 5.0.0-2.2, allowing the consumer to read any
standard Kafka compression format in a closed network.

`extended-otel-kafka-serialization-1.0.0.jar` contains the two narrow
column-selecting serializers used to turn a typed Flink `Row` into a Kafka
record key and value. Its reviewed source is under `runtime/java`; it exists
because PyFlink 2.2.1 otherwise applies both serializers to the complete row.

Verify the checked-in artifact before building:

```text
Get-FileHash vendor\flink\*.jar -Algorithm SHA256
```

Expected SHA-256:

```text
flink-sql-connector-kafka-5.0.0-2.2.jar
  5605C691D11A501382C383FECBA37A7A552467DA5AB7BA904EF5D6F3D62C5616
extended-otel-kafka-serialization-1.0.0.jar
  35495F404CD07D31209AD66B7D1FF26D7D2B2C28CC0BD20B968D93ABF565455A
lz4-java-1.10.1.jar
  A58A84C4271E50DF4C96ED916CCB7E48A869F8ED9CDCDA1AD5D3D4C33B0214A3
snappy-java-1.1.10.7.jar
  4C766CB3F855415EE734B2392949A0B6F12A60879334A74518DEAF6270D32E36
zstd-jni-1.5.6-10.jar
  B6C3237E24B8252A5A9C3A0E1AE30EF8F323412E74BD358548B7A9E527D676DF
```

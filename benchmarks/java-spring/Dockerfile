FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /src
COPY pom.xml .
RUN mvn -q -e dependency:go-offline
COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /src/target/ingest-0.1.0.jar app.jar
# Konfigurace přes env (MQTT_HOST, DSN, BATCH_SIZE, FLUSH_MS, …) — viz IngestApplication.
ENTRYPOINT ["java", "-jar", "app.jar"]

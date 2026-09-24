FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /app/backend
COPY backend/pom.xml .
COPY backend/src ./src
COPY config /app/config
RUN mvn -B package -DskipTests
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/backend/target/hamlab-1.0.0.jar app.jar
ENV SERVER_ADDRESS=0.0.0.0 STORAGE_DIR=/app/data
ENTRYPOINT ["java","-Djava.awt.headless=true","-jar","app.jar"]

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY ingest.csproj .
RUN dotnet restore
COPY Program.cs .
RUN dotnet publish -c Release -o /app

FROM mcr.microsoft.com/dotnet/runtime:8.0
WORKDIR /app
COPY --from=build /app .
# Konfigurace přes env (MQTT_HOST, DSN, BATCH_SIZE, FLUSH_MS, …) — viz Program.cs.
ENTRYPOINT ["dotnet", "ingest.dll"]

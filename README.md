# VCF AI OpenAI Bridge

Bridge para conectar **VMware VCF Operations / Intelligent Assist** con un proveedor de IA compatible con la API de OpenAI, como **LiteLLM, vLLM u otros gateways OpenAI-compatible**.

El bridge adapta la API del proveedor para que VCF pueda detectar los modelos y utilizar `chat/completions` y tool calling.

## Arquitectura

```text
VCF Intelligent Assist
        │
        ▼
VCF AI OpenAI Bridge
        │
        ▼
OpenAI-compatible API
        │
        ├── LiteLLM
        ├── vLLM
        └── otro proveedor compatible
```

## Requisitos

- Docker
- Docker Compose
- Un proveedor que exponga una API compatible con OpenAI
- Un modelo compatible con tool/function calling
- Certificado TLS para el endpoint que utilizará VCF

## Configuración

Copiar el archivo de ejemplo:

```bash
cp .env.example .env
```

Editar `.env`:

```env
# API real del proveedor
UPSTREAM_BASE_URL=https://llm.example.com/v1
UPSTREAM_API_KEY=YOUR_PROVIDER_API_KEY

# API key que utilizará VCF para conectarse al bridge
PUBLIC_API_KEY=YOUR_VCF_API_KEY

# Configuración presentada a VCF
MODEL_TYPE=COMPLETIONS
MODEL_ENGINE=OPENAI
MODEL_STATUS=AVAILABLE

# Opcional: limitar los modelos visibles para VCF
EXPOSE_MODELS=

# TLS
TLS_CERT_FILE=/certs/cert.pem
TLS_KEY_FILE=/certs/key.pem

# Logs
LOG_LEVEL=INFO
LOG_REQUEST_BODIES=false
```

`UPSTREAM_API_KEY` y `PUBLIC_API_KEY` son credenciales diferentes:

- `UPSTREAM_API_KEY`: acceso del bridge al proveedor real.
- `PUBLIC_API_KEY`: acceso de VCF al bridge.

## Certificados

Colocar el certificado y su clave en:

```text
certs/
├── cert.pem
└── key.pem
```

El certificado debe corresponder al FQDN que se utilizará desde VCF.

## Iniciar

```bash
docker compose up -d --build
```

Ver estado:

```bash
docker compose ps
```

Ver logs:

```bash
docker compose logs -f
```

## Probar

Health check:

```bash
curl -k https://localhost:8443/health
```

Listar los modelos que verá VCF:

```bash
curl -k \
  https://localhost:8443/api/v1/compatibility/openai/v1/models \
  -H "Authorization: Bearer YOUR_VCF_API_KEY"
```

## Configurar VCF

En **VCF Operations → Intelligent Assist**:

**Provider**

```text
VCF Private AI
```

**API Endpoint**

```text
https://bridge.example.com:8443/api/v1/compatibility/openai
```

> Importante: no agregar `/v1` al final. VCF agrega `/v1/models` y `/v1/chat/completions` automáticamente.

**API Key**

```text
PUBLIC_API_KEY
```

Después de conectar, VCF debería detectar los modelos disponibles.

Seleccionar el modelo desde la configuración de Intelligent Assist y probar una consulta que utilice las herramientas de VCF.

Por ejemplo:

```text
Consultá las alertas activas del entorno y resumilas por severidad.
```

## Qué hace el bridge

El bridge:

- expone los modelos del proveedor a VCF;
- agrega los metadatos que VCF espera en `/models`;
- pasa las solicitudes `chat/completions` al proveedor real;
- soporta streaming;
- soporta tool/function calling;
- mantiene separadas las credenciales de VCF y del proveedor;
- permite limitar qué modelos puede ver VCF.

El modelo sigue ejecutándose en el proveedor configurado. El bridge solamente adapta y transporta las solicitudes entre VCF y la API OpenAI-compatible.

## Detener

```bash
docker compose down
```

## Actualizar

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

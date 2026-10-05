# Configuración y operación

Todos los valores específicos del despliegue están en `.env`. El archivo se lee como pares RAW `KEY=value`. Las credenciales no se evalúan como expresiones de shell ni como variables de Compose al usar `bridgectl`. No ejecutar `source .env`.

| Variable | Uso |
|---|---|
| `PUBLIC_HOSTNAME` | Nombre DNS expuesto, utilizado por las pruebas TLS con SNI y validación de hostname |
| `PUBLIC_BIND_ADDRESS` | Interfaz/IP del host donde Docker publica el servicio; predeterminado `0.0.0.0` |
| `PUBLIC_PORT` | Puerto del host; el contenedor utiliza internamente 8443 |
| `PUBLIC_API_KEY` | Key de VCF hacia el bridge; obligatoria, mínimo 24 caracteres |
| `UPSTREAM_BASE_URL` | Base exacta upstream, normalmente con `/v1` incluido; nunca la URL del propio bridge |
| `UPSTREAM_API_KEY` | Key real del proveedor; no se reenvía la key pública |
| `UPSTREAM_AUTH_HEADER` | Encabezado upstream; predeterminado `Authorization` |
| `UPSTREAM_AUTH_PREFIX` | Prefijo upstream; `Bearer` por defecto, vacío para enviar solo la key |
| `UPSTREAM_VERIFY_TLS` | `true` por defecto; no deshabilitar para una instalación permanente |
| `UPSTREAM_CA_BUNDLE` | PEM de CA interna, por ejemplo `/ca/upstream-ca.pem`; montar el archivo en el directorio `ca/` |
| `UPSTREAM_TRUST_ENV` | `false`; controla si HTTPX puede usar proxy/configuración de confianza del entorno del contenedor |
| `EXPOSE_MODELS` | CSV de IDs permitidos; vacío expone todos. Filtra listado y bloquea inferencia de otros IDs |
| `DISCOVERY_MODE` | `enriched` conserva el comportamiento del prototipo; `passthrough` es para una futura prueba controlada |
| `MODEL_TYPE` | Metadato declarado por el operador; predeterminado `COMPLETIONS` |
| `MODEL_ENGINE` | Metadato declarado por el operador; predeterminado `OPENAI` |
| `MODEL_STATUS` | Campo extra heredado del prototipo; `AVAILABLE` por compatibilidad. Vacío lo omite |
| `MODEL_OWNER_OVERRIDE` | Opcional; vacío conserva `owned_by` del upstream |
| `TLS_CERT_FILE`, `TLS_KEY_FILE` | Rutas dentro de `/certs/` en el contenedor |
| `CONTAINER_UID`, `CONTAINER_GID` | Usuario/grupo numérico sin privilegios, con lectura de la key TLS |
| `CONNECT_TIMEOUT_SECONDS` | Timeout de conexión upstream; 15 s por defecto |
| `READ_TIMEOUT_SECONDS` | Timeout de inactividad de lectura/escritura upstream; 600 s por defecto, no duración total |
| `MAX_REQUEST_BYTES` | Límite de body JSON entrante; 8 MiB por defecto |
| `MAX_RESPONSE_BYTES` | Límite de respuesta JSON no streaming; 32 MiB por defecto |
| `MAX_INFLIGHT_REQUESTS` | Operaciones autenticadas simultáneas, incluidas inferencias; 8 por defecto |
| `SMOKE_MODEL` | Modelo de prueba opcional; `--model` tiene prioridad |

No asignar `COMPLETIONS` a modelos de embeddings ni exponer modelos que el operador no quiera utilizar desde VCF. El bridge no detecta por sí solo las capacidades del modelo. Un campo `status=AVAILABLE` es una etiqueta de compatibilidad, no una comprobación de capacidad GPU o salud de inferencia.

## TLS

Para una CA interna upstream, copiar el certificado CA público a `ca/` y establecer `UPSTREAM_CA_BUNDLE=/ca/nombre.pem`. Esto no modifica los certificados de entrada al bridge. Un CA bundle explícito tiene prioridad sobre el booleano de verificación.

El certificado que ve VCF es `certs/cert.pem`; su key está en `certs/key.pem`. El healthcheck local confía en ese certificado y valida el nombre DNS configurado. No emplea `curl -k` ni desactiva la comprobación de hostname. Si el certificado cambia, VCF puede requerir una nueva decisión de confianza.

## Ejecución y logs

```bash
./bridgectl status
./bridgectl info
./bridgectl logs --since 10m
./bridgectl logs --follow --since 1m
./bridgectl restart
./bridgectl reconfigure
```

Ejemplo esquemático de log, sin valores del entorno:

```json
{"event":"request_complete","operation":"chat_completions","tools_offered":6,"tool_results_in_history":1,"tool_calls_returned":0,"http_status":200,"duration_ms":1200.0}
```

`duration_ms` mide el tiempo del bridge hasta terminar el transporte de respuesta, no solo el tiempo de inferencia ni los tokens por segundo. Los nombres de herramientas y sus argumentos no se guardan.

## Diagnóstico

| Resultado | Interpretación / siguiente paso |
|---|---|
| 401 con `invalid_api_key` | La credencial presentada al bridge no coincide con `PUBLIC_API_KEY` |
| 401/403 con `upstream_error` | El proveedor rechazó la credencial/solicitud upstream |
| 404 en `/v1/v1/...` | Revisar base VCF: el cliente observado añade `/v1` |
| 403 `model_not_allowed` | El modelo no está en `EXPOSE_MODELS` |
| 413 | Body mayor que el límite configurado |
| 429 upstream | Cuota/rate limit del proveedor; no se reintenta automáticamente |
| 502 | Error de conexión, contrato, TLS, tipo de contenido, JSON o respuesta upstream |
| 503 `bridge_busy` | Se alcanzó `MAX_INFLIGHT_REQUESTS` |
| 504 | Timeout upstream |
| Stream interrumpido con HTTP inicial 200 | Revisar `error_code`, `sse_done`, disponibilidad y timeout upstream |

Las respuestas de error del proveedor se sustituyen por un mensaje genérico para no exponer credenciales, URLs o detalles internos. Se conserva el estado HTTP de error cuando existe. El diagnóstico profundo se realiza en los logs del proveedor, bajo sus propias reglas de acceso.

La protección de red/allowlist de orígenes corresponde al operador. El proyecto no crea reglas de firewall ni modifica UFW/iptables. La key común del bridge tampoco sustituye la autorización individual de usuarios y herramientas dentro de VCF.

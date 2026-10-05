# VCF AI OpenAI Bridge

**1.0.0-rc1 · Primera publicación comunitaria · Proyecto independiente**

> Funcionamiento reportado por el operador en VCF Operations / Intelligent Assist 9.1.1 + LiteLLM. Ver [alcance de la validación](docs/FIELD_VALIDATION.md).

**Para publicar desde una PC sin acceder a producción:** [guía de carga en GitHub](docs/PUBLICAR_DESDE_PC.md).

Bridge HTTP pequeño para conectar el flujo observado de **VCF Intelligent Assist** con un proveedor que exponga `GET /models` y `POST /chat/completions` compatibles con OpenAI.

Separa la credencial que presenta VCF de la utilizada contra el proveedor real. Puede enriquecer el descubrimiento de modelos y transporta las solicitudes de chat y herramientas sin cambiar su contenido. No sirve modelos, no requiere GPU propia y no ejecuta las herramientas de VCF.

```text
VCF Intelligent Assist
  Provider configurado: VCF Private AI
        │ HTTPS + PUBLIC_API_KEY
        ▼
VCF AI OpenAI Bridge :8443
  /v1/models                       → descubrimiento configurable
  /v1/chat/completions              → transporte JSON / SSE
        │ UPSTREAM_BASE_URL + UPSTREAM_API_KEY
        ▼
Proveedor OpenAI-compatible
        ▼
Modelo y servidor de inferencia elegidos por el operador
```

**No es PAIS, no implementa su plano de control y no es un producto soportado o avalado por Broadcom/VMware.** La compatibilidad depende de la versión del cliente VCF, el proveedor y el modelo. Ver [compatibilidad y evidencia](docs/COMPATIBILITY.md).

## Qué incluye

Configuración en `.env`, autenticación obligatoria hacia el bridge, credencial upstream independiente, HTTPS, CA upstream configurable, allowlist de modelos aplicada tanto al listado como a inferencia, límites de solicitudes, logs estructurados sin contenido, healthcheck, migración del prototipo y rollback.

El contenedor corre sin root, con filesystem de solo lectura, sin capacidades Linux añadidas y sin acceso al socket Docker. Las dependencias Python están fijadas; el build ejecuta los tests antes de producir la imagen final. La etiqueta base de Python aún no está fijada por digest: no se promete reproducibilidad binaria.

## Requisitos

Linux, Bash, Python 3.10 o superior **en el host**, OpenSSL, Docker Engine y Docker Compose **2.30.0 o superior**. El servicio usa Python 3.13 **dentro del contenedor**. Ejecutar `bridgectl` con el usuario normal que ya tiene permisos Docker, no con `sudo`.

Compose 2.30 permite `env_file.format: raw`, utilizado para conservar literalmente credenciales con `$`, `#` o comillas. `bridgectl` también evita que Compose intente interpolar el archivo de credenciales: solo pasa los valores no secretos de publicación de puerto/UID/GID a la interpolación.

El build necesita descargar la imagen base y las dependencias Python. Esto no hace consultas al proveedor de IA. El bridge solo solicita inferencias cuando VCF o una prueba explícita de chat las solicita.

## Preparar el lanzador después de extraer o clonar

Desde la carpeta raíz del proyecto, en el host Linux de instalación:

```bash
chmod +x bridgectl
```

Esto permite usar `./bridgectl` aunque el ZIP, una copia desde Windows o la carga web no haya conservado el permiso de ejecución. No es un paso necesario para publicar el código desde una PC.

## Migrar un prototipo que ya funciona en 8443

Este es el camino indicado cuando existe el contenedor anterior. **No iniciar la nueva versión manualmente sobre el mismo puerto.**

```bash
cd /opt/vcf-ai-openai-bridge
./bridgectl migrate --old-dir /opt/pais-shim --old-container pais-shim --port 8443
./bridgectl deploy
./bridgectl status
./bridgectl smoke
```

La migración copia la configuración efectiva del contenedor, convierte `SHIM_API_KEY` en `PUBLIC_API_KEY` **sin cambiar su valor**, reutiliza certificado/key y conserva el directorio original. No regenera credenciales y no solicita que se vuelvan a pegar.

`deploy` construye y ejecuta un preflight sin publicar otro puerto. Solo entonces detiene el bridge anterior y habilita el candidato en el mismo puerto. Si falla el arranque o la prueba local posterior, intenta restaurar el contenedor anterior. El respaldo contiene secretos: permanece en `.local/backups/`, fuera de los archivos exportables.

Para volver al anterior:

```bash
./bridgectl rollback
```

Ver [migración detallada](docs/MIGRATION.md). Una caída de Docker, pérdida de energía, `SIGKILL` o desconexión que termine abruptamente el proceso puede impedir el rollback automático: existe el comando manual.

## Instalación nueva, sin prototipo

No ejecutar este flujo para una migración.

```bash
./bridgectl init --public-hostname bridge.example.org --port 8443
./bridgectl up
./bridgectl smoke
./bridgectl info
```

El asistente pregunta URL y API key del proveedor sin guardar la key en el historial de shell. Genera una key pública aleatoria si se deja vacía y crea un certificado autofirmado independiente si no existen los archivos. Para uso permanente, instalar un certificado de la organización en `certs/cert.pem` y `certs/key.pem` y establecer la confianza correspondiente en VCF.

`bridge.example.org` es solo un ejemplo: debe reemplazarse por el FQDN real que resuelva hacia la VM y coincida con el SAN del certificado. No se crea DNS ni se modifica firewall/NAT.

## Configuración mínima

```dotenv
PUBLIC_HOSTNAME=bridge.example.org
PUBLIC_PORT=8443
PUBLIC_API_KEY=una-key-del-bridge-larga-y-aleatoria
UPSTREAM_BASE_URL=https://proveedor.example.org/v1
UPSTREAM_API_KEY=key-del-proveedor-real
```

Estas líneas son ejemplos, no credenciales válidas. Los valores `.env` son **RAW**: no rodearlos con comillas, no agregar comentarios al final, no usar `source .env`. Los comentarios van en su propia línea. No se permiten valores multilínea.

`UPSTREAM_BASE_URL` es la base exacta del API upstream y normalmente **incluye `/v1`**. No debe apuntar al propio bridge, porque produciría un bucle. `localhost` desde el contenedor no es el host: para un servicio del host puede emplearse `host.docker.internal` si el servicio escucha en una interfaz accesible desde Docker.

`UPSTREAM_API_KEY` puede estar vacía para un servidor local sin autenticación. En ese caso no se reenvía la key pública. La credencial del bridge siempre es obligatoria.

Cambios de `.env`:

```bash
./bridgectl reconfigure
```

Esto valida la configuración y recrea **solo** el bridge. `restart` es para reiniciar con la configuración que ya está dentro del contenedor, no para importar cambios del archivo `.env`.

## Endpoint que se configura en VCF

Mantener el provider `VCF Private AI`, con esta forma de base:

```text
https://bridge.example.org:8443/api/v1/compatibility/openai
```

**No agregar `/v1` al final de esa base en el cliente VCF observado.** En el prototipo el cliente añadió `/v1/models` automáticamente. Con una base que ya terminaba en `/v1`, se observó un `/v1/v1/models` y un 404.

La URL HTTP completa de modelos es distinta:

```text
https://bridge.example.org:8443/api/v1/compatibility/openai/v1/models
```

El bridge también ofrece el alias corto `/v1/...`. `./bridgectl info` muestra la base VCF correcta para el `.env` local, sin imprimir ninguna key.

## Pruebas

```bash
# Sin inferencia: HTTPS, autenticación, listado y disponibilidad upstream.
./bridgectl smoke

# Elegir uno de los modelos realmente devueltos por /models.
./bridgectl smoke --model MI_MODELO --chat --stream --tools

# Log de la nueva versión, no del contenedor antiguo.
./bridgectl logs --follow --since 1m
```

`--chat` y `--stream` generan una consulta cada uno; `--tools` genera dos. Pueden consumir tokens, cuota y capacidad del proveedor real. La prueba de herramientas usa una función local de eco, sin acciones externas. Comprueba formato, argumentos JSON y el segundo turno con resultado de herramienta. **No prueba las skills ni los permisos de VCF.**

Para cerrar la validación en VCF, usar [el checklist](docs/VALIDATION.md): consulta real de alertas, comparación con la interfaz, seguimiento conversacional y repetición después de reiniciar el bridge.

## Rutas implementadas

| Método | Ruta | Autenticación | Función |
|---|---|---|---|
| GET | `/healthz` y `/health` | No | Vida del proceso y versión, sin datos del proveedor |
| GET | `/readyz` | Sí | Comprueba modelos upstream; no solicita inferencia |
| GET | `/v1/models` | Sí | Listado con filtro y enriquecimiento opcional |
| GET | `/v1/models/{id}` | Sí | Búsqueda en el listado, sin construir una URL dinámica upstream |
| POST | `/v1/chat/completions` | Sí | JSON o SSE; preserva bytes de la solicitud |

Las tres rutas `/v1/...` también están bajo `/api/v1/compatibility/openai/v1/...`. No se implementan administración, carga de archivos, Responses API, embeddings, fine-tuning ni rutas arbitrarias de PAIS. Los métodos/rutas no contemplados se rechazan y nunca se convierten en un proxy abierto.

## Logs y límites

Se registra UTC, identificador de solicitud, operación, estado HTTP, duración, tamaño de respuesta y contadores de herramientas. No se registran prompts, respuestas, argumentos de herramientas, nombres de modelos, IPs, URL del proveedor, cookies ni API keys. Docker limita la retención a tres archivos de 10 MB para este contenedor.

En SSE los contadores de herramientas se inspeccionan de forma acotada y son diagnósticos, no una auditoría completa. `tool_calls_returned` significa que se observó una llamada emitida por el modelo; `tool_results_in_history` significa que llegó un mensaje `role=tool`. Ninguno prueba por sí solo que los datos sean correctos o que una acción VCF se haya completado.

`READ_TIMEOUT_SECONDS` es un timeout de lectura/inactividad, no un límite total del trabajo del modelo. No se hacen reintentos automáticos de inferencia. Después de enviar encabezados SSE no puede transformarse un error en un nuevo estado HTTP: el stream se interrumpe y se registra el problema.

No hay métricas Prometheus, interfaz web ni endpoint para consultar los cuerpos históricos. Las herramientas se ejecutan en VCF, no en este contenedor.

## Publicación de código desde una PC

El ZIP de fuentes se puede extraer y cargar desde el navegador en el repositorio ya creado. No hace falta conectarse a la VM, copiar su `.env`, instalar Git allí ni ejecutar comandos sobre producción. Ver [pasos desde la PC](docs/PUBLICAR_DESDE_PC.md), [notas de release](docs/RELEASE_NOTES.md) y [texto para LinkedIn](docs/LINKEDIN.md).

### Exportar otras copias de fuentes (opcional)

No publicar el directorio de ejecución completo. El exportador incluye una lista explícita de archivos fuente/documentación y comprueba que no contengan las keys o nombres configurados localmente:

```bash
python3 tools/package_source.py
```

El resultado se guarda en `.local/releases/`, en `.tar.gz` y `.zip`, con hashes SHA-256. No incluye `.env`, certificados, backups ni logs. Es una comprobación básica; revisar igualmente los cambios y las capturas antes de publicarlos.

Se incluye un workflow de CI que construye y ejecuta los tests. No publica imágenes ni hace releases automáticamente. Esta entrega no crea ni modifica ningún repositorio GitHub.

## Documentación

[Configuración y operación](docs/CONFIGURATION.md) · [Migración](docs/MIGRATION.md) · [Validación](docs/VALIDATION.md) · [Compatibilidad](docs/COMPATIBILITY.md) · [Resultado de pruebas](docs/TEST_REPORT.md) · [Seguridad](SECURITY.md) · [Referencias](docs/REFERENCES.md)

## Licencia y atribución

MIT. Copyright © 2026 Demian Ferrari. VMware, Broadcom, VCF y los demás nombres de terceros pertenecen a sus respectivos titulares. El nombre del proyecto describe una integración y no implica afiliación, certificación ni soporte del fabricante.

# Migración del prototipo en el mismo 8443

## Alcance y corte

El único servicio que se detiene es el contenedor pasado explícitamente a `--old-container`. El script verifica que ese contenedor esté activo y publique el puerto pedido. No usa `docker compose down`, `docker system prune`, reinicios de Docker, limpieza de volúmenes ni cambios a otro compose.

La compilación consume algo de CPU/RAM/disco de la misma VM y requiere descargar dependencias. No modifica la configuración de LiteLLM, NGINX o los modelos. Durante el cambio hay una interrupción breve de **este bridge**, y las consultas en curso pueden cortarse: elegir un momento sin consultas VCF activas. No es un cambio de cero downtime.

## Preparación

Extraer el paquete en un directorio separado, propiedad del usuario que ejecuta Docker. No hacerlo dentro del directorio anterior. Cuando se instala en `/opt/vcf-ai-openai-bridge`:

```bash
cd /opt/vcf-ai-openai-bridge
./bridgectl migrate --old-dir /opt/pais-shim --old-container pais-shim --port 8443
```

El script lee la configuración efectiva del contenedor mediante Docker, no imprime su `inspect` y copia:

| Origen | Destino |
|---|---|
| `UPSTREAM_BASE_URL` | `UPSTREAM_BASE_URL` |
| `UPSTREAM_API_KEY` | `UPSTREAM_API_KEY` |
| `SHIM_API_KEY` | `PUBLIC_API_KEY`, mismo valor |
| `MODEL_ENGINE`, `MODEL_TYPE`, `EXPOSE_MODELS` | Mismos valores cuando existen |
| `certs/cert.pem`, `certs/key.pem` | Copias independientes en el directorio nuevo |

Se infiere `PUBLIC_HOSTNAME` del SAN DNS del certificado. Para un certificado wildcard o SAN ambiguo usar `--public-hostname FQDN_REAL`. No se confía en un nombre inventado ni se cambia DNS.

Se fija el UID/GID del contenedor al usuario del host para que lea la copia de `key.pem` con permiso 600. No se cambian permisos de los originales. Se guarda un tar privado del directorio anterior y metadatos de rollback en `.local/`.

Se rechaza sobrescribir un `.env` o un estado de migración ya existente. Un error antes de `deploy` no detiene el prototipo.

## Reemplazo

```bash
./bridgectl deploy
```

El orden es: build con tests → preflight sin puertos publicados → detener anterior → iniciar candidato en el mismo puerto → validar HTTPS, hostname, versión, autenticación y `/models` por el puerto del host.

El preflight hace una consulta al listado upstream, pero no genera tokens. La nueva imagen no contiene keys ni certificados: se proveen al crear el contenedor.

Al retener el contenedor anterior para rollback, se cambia su restart policy a `no`. Esto evita que reclame el puerto en un reinicio del host. El valor anterior se conserva en el estado y se restaura con `rollback`. El antiguo directorio e imagen no se borran.

Si fallan el build o el preflight, el anterior sigue funcionando. Si falla el corte o la comprobación posterior, se intenta rollback automático. Un cierre abrupto del host/daemon o `SIGKILL` no puede manejarse: ejecutar el rollback manual cuando Docker vuelva.

## Validación y rollback

```bash
./bridgectl status
./bridgectl smoke
./bridgectl logs --follow --since 1m
```

Repetir una consulta en VCF conservando endpoint, API key y modelo. Después usar el checklist de validación. No borrar el provider para hacer esta actualización.

Para regresar:

```bash
cd /opt/vcf-ai-openai-bridge
./bridgectl rollback
```

Este comando detiene solo el candidato, restaura la política del anterior y lo inicia por su ID original. No necesita reconstruirlo. La UI de VCF puede necesitar que se reintente la consulta que estaba en curso.

No borrar manualmente el contenedor anterior durante esta fase: el rollback por ID depende de que exista. Si se borró, el backup contiene su código/configuración, pero se necesita una recuperación manual y no debe darse por completado un rollback automático.

## Cambiar variables más adelante

Editar solo el nuevo `.env` y ejecutar:

```bash
./bridgectl reconfigure
```

Para reiniciar sin cambios:

```bash
./bridgectl restart
```

El flujo `deploy` es una migración desde el prototipo. No pretende ser un orquestador genérico de actualizaciones arbitrarias de releases posteriores.

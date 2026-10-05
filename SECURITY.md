# Security Policy

## Reportar una vulnerabilidad

Si encontrás una vulnerabilidad de seguridad, **no abras un issue público con credenciales, tokens, certificados, datos internos o detalles explotables**.

Reportala de forma privada al mantenedor del repositorio, incluyendo:

- versión utilizada;
- descripción del problema;
- pasos para reproducirlo;
- impacto estimado;
- logs o capturas sanitizadas, si ayudan a reproducirlo.

No incluyas API keys, archivos `.env`, claves privadas TLS ni información sensible de tu entorno.

## Recomendaciones de despliegue

Antes de usar el bridge:

- protegé el archivo `.env`;
- usá una `PUBLIC_API_KEY` distinta de la `UPSTREAM_API_KEY`;
- utilizá HTTPS con un certificado válido para el FQDN del bridge;
- restringí el acceso al puerto del bridge a las redes que realmente lo necesiten;
- no publiques certificados privados ni archivos `key.pem`;
- mantené `LOG_REQUEST_BODIES=false` salvo durante troubleshooting controlado;
- rotá las API keys si sospechás que fueron expuestas;
- mantené Docker, Docker Compose y la imagen base actualizados.

Permisos recomendados:

```bash
chmod 600 .env
chmod 600 certs/key.pem
chmod 644 certs/cert.pem
```

## Datos sensibles

El bridge puede transportar prompts, respuestas del modelo, tool calls y resultados provenientes de VCF.

Por ese motivo:

- evitá registrar cuerpos completos de requests en producción;
- revisá los logs antes de compartirlos;
- no publiques archivos de configuración reales;
- no subas al repositorio `.env`, certificados privados, backups ni logs.

El repositorio incluye `.env.example` únicamente como plantilla de configuración.

## API keys

El bridge utiliza dos credenciales separadas:

- `PUBLIC_API_KEY`: la utiliza VCF para autenticarse contra el bridge.
- `UPSTREAM_API_KEY`: la utiliza el bridge para autenticarse contra el proveedor OpenAI-compatible.

No reutilices la misma clave para ambos lados.

## Versiones

Las correcciones de seguridad se aplicarán sobre la versión más reciente publicada del proyecto.

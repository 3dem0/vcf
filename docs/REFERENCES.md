# Referencias técnicas

Consultadas al preparar la candidata. Las rutas y schemas de una documentación `latest` pueden cambiar; registrar las versiones del entorno validado.

- [Broadcom: OpenAIModel](https://developer.broadcom.com/xapis/vmware-private-ai-service-api/latest/data-structures/OpenAIModel/). Referencia de `model_type` y `model_engine`. No demuestra que un cliente VCF exija todos los campos ni convierte al bridge en PAIS.
- [Docker Compose: services/env_file](https://docs.docker.com/reference/compose-file/services/). `format: raw` y requisito de Compose 2.30.0.
- [Docker Compose: run](https://docs.docker.com/reference/cli/docker/compose/run/). Los comandos one-shot no publican los puertos del servicio salvo que se pida explícitamente.
- [Docker Compose: up](https://docs.docker.com/reference/cli/docker/compose/up/). Creación y recreación de servicios.
- [Docker: políticas de reinicio](https://docs.docker.com/engine/containers/start-containers-automatically/). Tratamiento de contenedores detenidos/retenidos para rollback.
- [HTTPX: streaming asíncrono](https://www.python-httpx.org/async/). Transporte por stream y necesidad de cerrar las respuestas.
- [HTTPX: TLS/SSL](https://www.python-httpx.org/advanced/ssl/). Verificación upstream y CA personalizada.
- [FastAPI: lifespan](https://fastapi.tiangolo.com/advanced/events/). Ciclo de vida del cliente HTTP compartido.
- [GitHub Actions: checkout](https://github.com/actions/checkout). Workflow de lectura y tests, sin publicación automática.

Los resultados del prototipo y la ruta `/v1` añadida por el cliente provienen de observaciones del operador, no de una garantía contractual del fabricante. No se incluyeron sus logs originales porque contienen datos de la instalación.

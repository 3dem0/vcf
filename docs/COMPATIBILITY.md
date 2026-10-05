# Compatibilidad: qué se sabe y qué no

## Evidencia del prototipo

En una prueba reportada por el operador con VCF Operations/Intelligent Assist 9.1.1 se observaron:

- Una solicitud `/v1/v1/models` cuando la base configurada ya terminaba en `/v1`; el upstream devolvió 404.
- Después de corregir la base, el cliente obtuvo `/models` con 200 y mostró los modelos.
- Una inferencia local atravesó el bridge y devolvió una respuesta del proveedor.
- El asistente de VCF devolvió un resumen de alertas que requiere cotejo con la UI y/o trazas de herramientas para confirmar los datos.

Esto no constituye certificación de soporte ni confirma todas las funcionalidades del asistente. Después de probar la candidata `1.0.0-rc1`, el operador reportó funcionamiento correcto; ver [validación de campo](FIELD_VALIDATION.md). Cada nueva instalación requiere sus propias comprobaciones.

## El enriquecimiento no está demostrado como requisito

Corregir el `/v1` duplicado fue un cambio decisivo observado. Como también estaba habilitado el enriquecimiento de modelos, **no se ha aislado si el cliente necesita esos metadatos**. No publicar que se demostró que LiteLLM directo es imposible o que agregar tres campos era obligatoriamente la solución.

`DISCOVERY_MODE=enriched` conserva el formato que estaba funcionando. La alternativa `passthrough` permite una prueba A/B posterior, pero no se recomienda cambiarla durante esta migración.

La referencia pública `OpenAIModel` consultada describe `model_type` y `model_engine`. No se usa esa referencia para afirmar que `status` sea un campo obligatorio: `MODEL_STATUS=AVAILABLE` se conserva como extensión heredada del prototipo y puede omitirse con valor vacío.

## Contrato limitado

El bridge requiere un listado `{"data":[{"id":"..."}]}` y un API de chat JSON/SSE. No implementa endpoints administrativos PAIS, licencias, identidades, Kubernetes, registro/despliegue de modelos ni un endpoint de Responses API.

Las solicitudes mantienen `model`, `messages`, `tools`, `tool_choice`, `stream` y parámetros adicionales tal como llegaron. Eso no hace que un modelo sin soporte/configuración de tool calling lo adquiera. El proveedor debe interpretar y devolver el contrato esperado.

No se sigue automáticamente un redirect upstream y no se aceptan queries con keys o versiones. Backends que requieran protocolos distintos necesitan una adaptación explícita, no una promesa genérica de compatibilidad.

Las herramientas se ejecutan en VCF. El bridge solo transporta el intercambio. La prueba local de eco no invoca VCF ni accede a su inventario.

## Formulación pública recomendada

"Bridge comunitario para un flujo observado de VCF Intelligent Assist hacia un proveedor OpenAI-compatible, con configuración por `.env`, separación de credenciales, transporte de herramientas y migración reversible. Compatibilidad probada en el entorno y versiones indicados; no es una implementación completa ni una integración oficialmente soportada de PAIS."

Completar los resultados reales y las versiones antes de publicar una release estable. No publicar capturas con dominios internos, nombres de recursos, IPs, API keys o datos de clientes.

# Resultado de pruebas y validación

Fecha de preparación: 2026-10-05. Versión: `1.0.0-rc1`.

## Ejecutado en el entorno de preparación

Python 3.13.5, FastAPI 0.128.2, Starlette 0.50.0, Uvicorn 0.48.0, HTTPX 0.28.1, pytest 9.0.2.

- Suite automatizada: **58 tests aprobados**. Autenticación, separación de keys, no reenvío de cookies/headers arbitrarios, allowlist en listado e inferencia, JSON/raw tool payload, SSE y cierre, errores/timeouts, límites, logs, configuración y control de migración/rollback.
- Prueba HTTPS real con Uvicorn, certificado autofirmado temporal con el formato del prototipo y proveedor simulado por HTTP local: aprobada.
- Probe de hostname/certificado sin desactivar verificación: aprobado.
- Chat JSON y función de eco con dos turnos: aprobados contra el proveedor simulado.
- SSE incremental: primer evento observado aproximadamente a 0.003 s, final aproximadamente a 0.704 s en una respuesta de prueba con pausas deliberadas. Es evidencia de transporte incremental local, **no** un benchmark del modelo.
- Comando Python del healthcheck de contenedor ejecutado contra el servicio HTTPS local: aprobado.
- Comprobación de ausencia de keys/prompts de prueba en el log: aprobada.

Los tests de rollback usan dobles de Docker: comprueban el orden de comandos y que build/preflight fallidos no detengan el anterior; no sustituyen una ejecución sobre Docker Engine.

## Reempaquetado para GitHub

La suite automatizada se volvió a ejecutar durante la preparación del ZIP público: **58 tests aprobados**. El código ejecutable, tests, dependencias, configuración de ejemplo y archivos de despliegue se conservaron byte por byte respecto del paquete original. Esta comprobación no despliega ni prueba la VM del operador.

## Validación posterior reportada por el operador

El operador reportó funcionamiento correcto de la candidata después de probarla en su instalación con VCF y LiteLLM. Ver [alcance de la validación](FIELD_VALIDATION.md). No se adjuntan logs ni resultados individuales que permitan convertir ese reporte en una matriz de certificación.

## Límites del entorno de preparación

No hubo un daemon Docker disponible durante la preparación inicial; las pruebas de control de migración utilizan dobles. No se realizó una auditoría independiente de seguridad ni un benchmark de carga sostenida. No se afirma soporte oficial ni compatibilidad universal.

## Reproducir tests de desarrollo

En un entorno de desarrollo separado:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q tests
```

Solo en un entorno descartable, con 8443 libre y OpenSSL:

```bash
python tests/integration_https.py
```

**No ejecutar el test HTTPS aislado en la VM de migración:** necesita abrir su propio servicio de prueba en 8443. En esa VM se utilizan `bridgectl deploy` y `bridgectl smoke`, que respetan el flujo de reemplazo del bridge existente.

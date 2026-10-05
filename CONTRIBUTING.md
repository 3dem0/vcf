# Contribuir

Trabajar en una copia de desarrollo, nunca sobre el directorio activo durante una consulta VCF. Incluir tests para cada cambio en autenticación, rutas, JSON, SSE o migración.

```bash
python -m pytest -q tests
```

No agregar URLs, IPs, nombres de modelos o keys de una instalación al código ni a capturas. Los fixtures deben ser sintéticos. No afirmar soporte de un modelo/proveedor sin registrar versión y prueba.

Mantener el transporte transparente de las solicitudes y no agregar ejecución de herramientas o acceso al socket Docker dentro del servicio. Los comandos Docker pertenecen al controlador local del operador.

Una modificación del contrato necesita una prueba controlada con VCF y un mecanismo de retorno. Actualizar CHANGELOG, versión del código, Docker/Compose, probes y documentación juntos.

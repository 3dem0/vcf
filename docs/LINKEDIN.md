# Texto para LinkedIn

Completar el enlace público y publicar después de revisar el repositorio y su CI.

---

¿Cómo conectar modelos on-premises a VCF Intelligent Assist usando un proveedor
OpenAI-compatible?

Desarrollé y probé **VCF AI OpenAI Bridge**: un contenedor intermedio entre VCF y el
proveedor de modelos, con configuración por `.env`, credenciales independientes,
HTTPS, transporte de chat y llamadas a herramientas, y migración con rollback.

La integración funcionó en mi entorno con VCF Operations / Intelligent Assist 9.1.1
y LiteLLM. Las herramientas de infraestructura siguen ejecutándose en VCF; el bridge
transporta el intercambio con el modelo.

Publico la primera versión comunitaria `1.0.0-rc1`, con código, documentación en
español y pruebas, para facilitar la reproducción y recibir resultados de
compatibilidad de otras instalaciones.

Es un proyecto independiente: no implementa PAIS completo ni representa una
integración oficialmente soportada o avalada por Broadcom/VMware.

Repositorio: PEGAR_URL_PUBLICA_DEL_REPOSITORIO

#VMware #VCF #PrivateAI #LiteLLM #OpenSource

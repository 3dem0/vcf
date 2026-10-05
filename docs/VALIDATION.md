# Checklist de validación por instalación

La candidata cuenta con un [reporte funcional del operador](FIELD_VALIDATION.md). Esta tabla es una **plantilla reutilizable**: las celdas pendientes no niegan ese reporte ni afirman que cada prueba haya sido documentada individualmente.

## Pruebas automáticas contra la instalación

```bash
./bridgectl status
./bridgectl smoke
./bridgectl smoke --model MI_MODELO --chat --stream --tools
```

La primera prueba no solicita inferencia. La segunda puede generar cuatro solicitudes de inferencia en total: chat, SSE y dos turnos de eco con herramientas. Usar un modelo realmente devuelto por `/models` y autorizado para pruebas.

Anotar la salida sin publicar credenciales. Un fallo en la función de eco puede ser del modelo o de la configuración del servidor de inferencia, no necesariamente del bridge.

## Validación en VCF

| Comprobación | Resultado del operador |
|---|---|
| Versión/build exacta de VCF Operations | Pendiente |
| Provider y modelo seleccionados | Pendiente |
| Provider sigue conectado sin cambiar URL/key | Pendiente |
| Descubrimiento de modelos correcto | Pendiente |
| Chat simple responde | Pendiente |
| Consulta de alertas responde | Pendiente |
| Alertas, severidades y ámbito coinciden con la UI en el mismo momento | Pendiente |
| Log registra herramientas ofrecidas / llamadas / resultados de herramientas | Pendiente |
| Conversación con seguimiento conserva contexto | Pendiente |
| Consulta repetida después de reiniciar solo el bridge | Pendiente |
| Comportamiento de rollback probado o procedimiento revisado | Pendiente |
| Logs/artefactos públicos sin datos corporativos | Pendiente |

Prompts de prueba:

```text
Respondé únicamente VCF IA OK.
```

```text
Consultá las alertas activas usando las herramientas disponibles.
Respondé en español e incluí recurso, severidad y estado.
No infieras causas que no estén respaldadas por datos.
```

Después, en la misma conversación:

```text
De esas alertas, mostrame solamente las críticas.
```

Comparar datos con VCF usando el mismo alcance, permisos, filtros y momento. No atribuir causalidad entre alertas solo por su distribución entre componentes. Los enlaces marcados como no verificados no deben darse por comprobados.

Reinicio:

```bash
./bridgectl restart
# Esperar a que el proceso esté disponible; luego:
./bridgectl smoke
```

Repetir una consulta VCF. `health=ok` no prueba skills, exactitud de datos ni autorización de VCF.

## Cierre

Esta publicación conserva la identificación `1.0.0-rc1` del código probado. Una release estable necesita registrar la matriz probada, revisar dependencias/imagen y preparar documentación/capturas saneadas. No borrar el prototipo de rollback durante la prueba.

# Resultados de simulación sintética — JobScout Pro

**Fecha de ejecución:** 26 de octubre de 2026  
**Versión probada:** rama `fix/domain-aware-ranking`  
**Datos:** CV y vacantes ficticios creados para las pruebas. No se utilizaron CV reales ni se hicieron llamadas de red.

## Resultado clave: perfil científico del IGME

Se simuló un currículum de geociencias con un objetivo deliberadamente ambiguo: «Scientist». El CV contiene términos de geología, geoquímica, hidrogeología y recursos minerales, además de vocabulario genérico de investigación, dirección de equipos, análisis y reporting.

| Oferta ficticia | Puntuación sin protección de ámbito | Puntuación protegida |
|---|---:|---:|
| Oncology Research Scientist | **89** (1.ª) | 24 |
| Senior Geoscientist | 87 (2.ª) | **95 (1.ª)** |
| Research Scientist | 86 (3.ª) | 86 |
| Data Scientist | 84 (4.ª) | 24 |

La comparación sin protección es una reconstrucción del componente base de título y solapamiento textual para este escenario genérico; no pretende reproducir todos los detalles de cualquier versión histórica del producto. Su propósito es comprobar que el mecanismo nuevo evita que el vocabulario transversal de investigación domine la compatibilidad profesional.

## Ocho perfiles probados

Cada perfil se comparó con cuatro ofertas sintéticas: 32 combinaciones de perfil/oferta en total.

| Perfil sintético | Posición de la oferta pertinente | Puntuación máxima |
|---|---:|---:|
| Geociencias / IGME, objetivo «Scientist» | 1.ª de 4 | 95/100 |
| Economía / analítica junior | 1.ª de 4 | 98/100 |
| Investigación clínica / oncología | 1.ª de 4 | 100/100 |
| Ingeniería de software | 1.ª de 4 | 100/100 |
| Ciencias medioambientales | 1.ª de 4 | 100/100 |
| Derecho | 1.ª de 4 | 100/100 |
| Finanzas / inversión | 1.ª de 4 | 100/100 |
| Cambio declarado de geología a análisis de datos | 1.ª de 4 | 88/100 |

**Resultado top-1 del benchmark sintético: 8/8 (100 %).** Es una prueba de regresión pequeña y deliberadamente construida; no es una estimación de precisión en producción, ni permite inferir una probabilidad de entrevista o contratación. Hay que seguir comprobando ofertas reales y perfiles ambiguos.

## Controles automáticos de esta rama

- **67 pruebas de Python superadas** en la ejecución validada de Python 3.12.
- Compilación de los módulos y carga de ayuda del CLI superadas.
- El simulador de ranking termina correctamente y verifica que el caso IGME no vuelve a colocar oncología por encima de geociencias.
- El escaneo automatizado de secretos en el código e historial de Git no detectó secretos reconocidos por sus patrones.
- La auditoría automatizada de dependencias declaradas terminó sin vulnerabilidades reportadas por la herramienta en esa ejecución.

Estos controles no equivalen a una auditoría de seguridad independiente. El escáner de secretos no detecta todos los tipos de exposición: por ejemplo, el correo del autor que aparece en metadatos públicos de commits es información personal, no un secreto tipo API key. Consulta `PRIVACY_REVIEW.md`.

## Próximas pruebas antes de un lanzamiento público

1. Probar el CV del IGME con consentimiento del titular y revisar los resultados reales.
2. Evaluar una muestra mayor de vacantes reales en varios países y fuentes.
3. Medir precisión de los primeros resultados, no solo el primer puesto: relevancia en top-5/top-10, falsos positivos y cobertura.
4. Verificar en el alojamiento elegido el aislamiento de sesiones, los registros, el borrado y las condiciones de cada proveedor de ofertas.

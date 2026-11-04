# Auditoría y resultados de validación — JobScout Pro

**Fecha:** 4 de noviembre de 2026
**Rama:** `feat/privacy-first-ai-cv-review`
**Alcance:** pruebas locales, perfiles y ofertas sintéticas y consultas reales de las fuentes públicas. No se han utilizado CV reales en el benchmark sintético ni se ha enviado ningún CV a proveedores.

## Resultado de los perfiles sintéticos

Se ha ampliado la batería a 16 perfiles profesionales, con cuatro vacantes ficticias por perfil (64 combinaciones):

| Perfil | Oferta pertinente en primer lugar |
|---|---:|
| Economía / analítica junior | 1.ª de 4 |
| Hidrogeología | 1.ª de 4 |
| Investigación clínica | 1.ª de 4 |
| Ingeniería de software | 1.ª de 4 |
| Ciencias medioambientales | 1.ª de 4 |
| Derecho | 1.ª de 4 |
| Finanzas | 1.ª de 4 |
| Recursos humanos | 1.ª de 4 |
| Marketing | 1.ª de 4 |
| Cadena de suministro | 1.ª de 4 |
| Diseño UX | 1.ª de 4 |
| Educación | 1.ª de 4 |
| Enfermería | 1.ª de 4 |
| Atención al cliente | 1.ª de 4 |
| Geología / jefatura de equipo | 1.ª de 4 |
| Graduado / analista junior | 1.ª de 4 |

**Top-1 sintético: 16/16.** La batería de ocho escenarios original también mantiene 8/8 en primera posición. Son pruebas de regresión construidas con vocabulario y ofertas artificiales; no representan una estimación estadística de precisión en el mercado laboral.

### Casos adversariales añadidos

- Una búsqueda de hidrogeólogo no debe premiar un puesto administrativo que mencione derechos de aguas: la puntuación de un desajuste profesional claro queda limitada a 14/100, por debajo del umbral de visualización habitual (20).
- Una búsqueda de prácticas no debe colocar por delante una vacante conocida como jornada completa por compartir el título base. La oferta a tiempo completo se limita a 14/100; una práctica real conserva su puntuación.
- Se prueban cambios de carrera explícitos, niveles junior/senior, títulos con palabras comunes y familias profesionales distintas.

## Inspección de ofertas reales

Las consultas se realizaron el 4 de noviembre de 2026. Los portales pueden actualizar o retirar anuncios después de esta fecha.

**Freehire**
- «Data Analyst Intern», España: la primera lista contenía ocho resultados. Entre los primeros aparecieron prácticas de analítica en HP (Sant Cugat), Criteo (Barcelona) y Schneider Electric (Barcelona), con fechas entre el 29 de octubre y el 4 de noviembre. Los títulos y ámbitos eran compatibles con el objetivo sintético de economía/analítica.
- «Business Analyst Intern», remoto Europa: la fuente devolvió puestos de Business Analyst, pero con metadatos de jornada completa. La nueva regla los deja por debajo del umbral de visualización de una búsqueda de prácticas; no se presentan como becas.
- «Hydrogeologist», España: el feed devolvió algunas coincidencias parciales. El puesto administrativo de Grupo Tragsa sobre derechos de aguas fue identificado como desajuste de ámbito y queda por debajo del umbral. No se encontraron suficientes vacantes hidrogeológicas claramente pertinentes en esa consulta.

**Arbeitnow**
- En las consultas concretas de prácticas Data Analyst/Business Analyst y de hidrogeología realizadas en esta muestra, no devolvió resultados que pasaran los filtros de título y ubicación. El adaptador se ha endurecido para que una etiqueta genérica como «data», «business» o «remote» no convierta un puesto de otra profesión en una coincidencia.

**Jobicy**
- En la muestra de su feed remoto europeo de los últimos siete días aparecieron cinco puestos de ingeniería backend compatibles con una búsqueda de Backend Engineer, uno de recursos humanos y uno de análisis financiero.
- No se encontraron coincidencias recientes para las consultas de prácticas Data Analyst / Business Analyst en España/Europa, UX Designer o Hydrogeologist. Jobicy es una fuente remota complementaria; no sustituye las búsquedas locales de Freehire.

La ausencia de resultados pertinentes no se compensa bajando automáticamente los criterios de relevancia. Es preferible mostrar cero coincidencias correctas que llenar la pantalla con falsos positivos.

### Ensayo de búsqueda para un perfil sintético de analítica junior

Se probó una lista de once títulos de prácticas de analítica y ciencias de la decisión (282 caracteres en total); el campo del dashboard se ha ampliado a 700 caracteres para admitir listas largas sin truncarse. Las consultas se ejecutaron con un resumen sintético de un perfil de economía junior, sin abrir ni transmitir ningún CV real:

- **Data Analyst Intern — España:** ocho resultados; HP, Criteo y Schneider Electric aparecen entre los primeros y están clasificados como prácticas.
- **Data Analyst Intern — remoto Europa:** cinco resultados brutos; una práctica de analítica de datos en energía superó el umbral de visualización. Los anuncios part-time/contract sin señal de prácticas quedaron a 14/100.
- **Business Intelligence Intern — España:** HP apareció en primera posición con una oferta explícita de prácticas.
- **Decision Science Intern y Operations Research Intern:** la muestra no produjo puestos suficientemente próximos y de nivel adecuado para superar el umbral de visualización. Se prefiere no recomendar prácticas de nóminas, cargos de dirección o puestos operativos genéricos por compartir palabras.

Esta muestra es específica de esos términos, fuentes, ubicaciones y fecha de consulta; no implica que no existan otras vacantes en otros portales o días.

## Pruebas técnicas

- **145 pruebas automatizadas superadas** en Windows / Python 3.12 en la última ejecución (4 de noviembre de 2026).
- Benchmark sintético: 16/16 perfiles en primera posición; simulación de ocho escenarios: 8/8.
- Ruff: los módulos nuevos de Jobicy, filtros de fechas y sus pruebas pasan las comprobaciones seleccionadas. El repositorio heredado conserva avisos de lint en otros archivos; no se afirma que todo el código legado esté libre de avisos.
- Compilación Python de la aplicación y módulos comprobada.
- Prueba de renderizado de Streamlit: cero excepciones; cinco pestañas y controles principales presentes.
- Comprobación HTTP local de Streamlit: respuesta 200 en el endpoint de salud y en la página principal.
- La integración Groq de revisión de CV está cubierta por pruebas simuladas; todavía no se ha probado una petición real porque no se ha proporcionado una clave API.

## Qué significan estos resultados

JobScout está más protegido frente a errores claros de título, ámbito profesional, geografía, antigüedad y nivel. Aun así, un 100 % en datos sintéticos no es un 100 % de precisión en vacantes reales. Los proveedores pueden devolver feeds incompletos, etiquetas erróneas o anuncios ya cerrados. El enlace específico tampoco garantiza que el puesto siga abierto: revisa la ficha original y los requisitos antes de solicitarlo.

La puntuación es un índice de relevancia, no una probabilidad de entrevista o contratación. La auditoría real debe continuar con tus búsquedas de cada semana y con feedback manual sobre ofertas buenas y malas.

# Alertas de JobScout Pro: la forma más sencilla

La opción recomendada es **ntfy para recibir avisos en el móvil**. No necesita cuenta, token, bot ni configuración SMTP. Telegram y correo siguen disponibles como alternativas, pero requieren una configuración adicional.

## Opción recomendada: notificaciones en el móvil con ntfy

### 1. Copia el canal que muestra JobScout Pro
1. Abre la pestaña **Alertas** de JobScout Pro.
2. En **Avisos al móvil**, copia el nombre del canal que aparece en el campo «Canal ntfy».
3. No lo publiques ni lo uses como nombre de usuario. Es un canal compartido: quien lo conozca puede publicar o suscribirse.

La aplicación genera un canal largo y aleatorio al empezar la sesión. **Guárdalo**. Si abres una sesión nueva y no configuraste `NTFY_TOPIC`, pega otra vez tu canal guardado en el campo. También puedes fijar un canal permanente en Secrets, como se explica más abajo.

### 2. Suscríbete desde el móvil
1. Instala la aplicación oficial **ntfy** en el móvil desde la tienda de aplicaciones.
2. Añade una suscripción usando el servidor `https://ntfy.sh`.
3. Escribe exactamente el mismo canal que copiaste de JobScout Pro y guarda la suscripción.
4. Asegúrate de que las notificaciones de ntfy estén permitidas en los ajustes del móvil.

### 3. Envía el Top 10
1. Lanza una búsqueda de ofertas y espera a que aparezcan resultados.
2. En la pestaña **Alertas**, pulsa **Enviar Top 10 al móvil**.
3. Deberías recibir una o varias notificaciones en el móvil. El resumen puede dividirse en varios mensajes para no sobrepasar los límites del servicio.

Para que JobScout envíe el resumen tras futuras búsquedas, activa **Enviar avisos al móvil por ntfy automáticamente después de cada búsqueda** y, además, **Enviar automáticamente el Top 10 al terminar cada búsqueda correcta**.

**Importante:** el envío automático solo se produce cuando tú lanzas una búsqueda mientras la app está abierta. No es un envío diario en segundo plano. ntfy.sh es un servicio público; el resumen de ofertas se transmite a ese servicio, así que no incluyas datos personales o confidenciales en el canal.

## Mantener el mismo canal entre sesiones (opcional)

Si puedes editar los secretos del despliegue, define un canal privado largo y aleatorio como `NTFY_TOPIC`. Añádelo en `.streamlit/secrets.toml` en local o en la sección Secrets del alojamiento:

```toml
NTFY_TOPIC = "elige-un-canal-largo-y-aleatorio"
```

No uses el ejemplo literal. Utiliza una cadena aleatoria, guárdala en un lugar privado y suscríbete a ese mismo nombre en ntfy. También puedes introducir manualmente tu canal guardado en la pestaña Alertas en cada sesión.

## Alternativa: Telegram

Telegram necesita un bot y un chat ID:

1. En Telegram, abre la cuenta oficial **@BotFather** y envía `/newbot`.
2. Guarda el token que te entrega. Trátalo como una contraseña; no lo compartas ni lo subas a GitHub.
3. Abre el chat de tu bot y pulsa **Iniciar** o envía `/start`.
4. Obtén tu chat ID de forma local. En PowerShell, guarda el token temporalmente en la sesión y ejecuta:

```powershell
$env:TELEGRAM_BOT_TOKEN = "PEGA_AQUI_TU_TOKEN"
Invoke-RestMethod "https://api.telegram.org/bot$env:TELEGRAM_BOT_TOKEN/getUpdates" |
  ConvertTo-Json -Depth 10
```

Busca el campo `chat.id` del mensaje que acabas de enviar. No compartas la salida: puede incluir datos del chat. Guarda token y chat ID en Secrets:

```toml
TELEGRAM_BOT_TOKEN = "TU_TOKEN"
TELEGRAM_CHAT_ID = "TU_CHAT_ID"
```

En JobScout, pulsa **Enviar Top 10 por Telegram**.

## Alternativa: correo electrónico

El correo necesita un servidor SMTP y credenciales. Para Gmail, suele requerirse una contraseña de aplicación en lugar de la contraseña habitual de la cuenta. Añade estos valores a `.streamlit/secrets.toml` o a los Secrets del despliegue:

```toml
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "tu-cuenta@gmail.com"
SMTP_PASSWORD = "CONTRASENA_DE_APLICACION"
SMTP_FROM = "tu-cuenta@gmail.com"
SMTP_TO = "tu-destino@gmail.com"
```

En la pestaña Alertas, escribe el destinatario y pulsa **Enviar Top 10 por correo**. No publiques ni compartas las credenciales.

## Qué contiene el resumen

- Hasta 10 ofertas con mayor puntuación entre las que pasan los filtros activos.
- Empresa, puesto, ubicación, relevancia y enlaces disponibles.
- Pros basados en la información localizada en el anuncio.
- Condiciones que conviene confirmar, como salario, horas, modalidad o duración.

**Un dato desconocido no elimina una oferta por defecto.** Se señala como «No indicado» y solo se excluye si activas explícitamente la opción de descartar ofertas con ese dato desconocido. La puntuación es orientativa; no representa la probabilidad de contratación.

## Solución de problemas

- **No llega el aviso de ntfy:** comprueba que el canal coincide exactamente en JobScout y en el móvil, que la suscripción usa `https://ntfy.sh` y que las notificaciones de ntfy están permitidas.
- **Cambió el canal al abrir otra sesión:** vuelve a introducir el nombre que guardaste o fija `NTFY_TOPIC` en Secrets.
- **Telegram no envía:** comprueba el token, el chat ID y que hayas pulsado `/start` en el bot.
- **Correo no enviado:** revisa host, puerto, usuario y contraseña de aplicación.
- **No hay ofertas:** ejecuta primero una búsqueda correcta; el resumen nunca inventa vacantes.


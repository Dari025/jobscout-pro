import sqlite3
from pathlib import Path

import requests
import yaml


def cargar_config():
	config_path = Path("busqueda.yaml")
	if not config_path.exists():
		config_path = Path("config.minimal.yaml")
	with config_path.open("r", encoding="utf-8") as archivo:
		return yaml.safe_load(archivo) or {}


def calcular_puntuacion(oferta):
	"""Puntúa una oferta según su encaje y descarta ubicaciones no válidas."""
	puntos = 50
	titulo = (oferta.get("title") or "").lower()
	descripcion = (oferta.get("description") or "").lower()
	ubicacion = (oferta.get("location") or "").lower()

	es_espana = "spain" in ubicacion or "españa" in ubicacion
	es_madrid = "madrid" in ubicacion
	es_remoto = any(
		termino in ubicacion
		for termino in ("remote", "remoto", "worldwide", "europe")
	)

	if es_espana and not es_madrid and not es_remoto:
		return -1

	puestos_objetivo = (
		"data analyst", "business analyst", "product analyst",
		"decision science", "risk analyst", "quant",
	)
	if any(termino in titulo for termino in puestos_objetivo):
		puntos += 25
	elif any(
		termino in descripcion
		for termino in ("analyst", "analytics", "data", "decision")
	):
		puntos += 15

	if any(
		termino in titulo or termino in descripcion
		for termino in ("intern", "junior", "graduate", "prácticas", "beca")
	):
		puntos += 20

	if es_remoto:
		puntos += 15
	elif es_madrid:
		puntos += 10

	return min(max(puntos, 0), 100)


def enviar_telegram(token, chat_id, mensaje):
	url = f"https://api.telegram.org/bot{token}/sendMessage"
	respuesta = requests.post(
		url,
		json={
			"chat_id": chat_id,
			"text": mensaje,
			"parse_mode": "Markdown",
			"disable_web_page_preview": True,
		},
		timeout=20,
	)
	respuesta.raise_for_status()
	return respuesta.json()


def main():
	print("🚀 Iniciando el generador de informes Top para Telegram...")
	config = cargar_config()
	telegram_cfg = config.get("telegram", {})
	token = telegram_cfg.get("bot_token")
	chat_id = telegram_cfg.get("chat_id")

	if not token or not chat_id:
		print("❌ Error: no se han encontrado bot_token o chat_id en la configuración.")
		return

	db_files = list(Path(".").glob("**/*.db"))
	if not db_files:
		print("⚠️ No se encuentra ninguna base de datos SQLite.")
		return

	try:
		with sqlite3.connect(db_files[0]) as conn:
			conn.row_factory = sqlite3.Row
			filas = conn.execute(
				"SELECT title, company, location, description, job_url FROM jobs"
			).fetchall()
	except sqlite3.Error as error:
		print(f"❌ Error leyendo la base de datos: {error}")
		return

	print(f"📦 Total de ofertas encontradas en bruto: {len(filas)}")
	ofertas = []
	for fila in filas:
		oferta = dict(fila)
		puntuacion = calcular_puntuacion(oferta)
		if puntuacion >= 0:
			oferta["score"] = puntuacion
			ofertas.append(oferta)
	ofertas.sort(key=lambda oferta: oferta["score"], reverse=True)
	top_ofertas = ofertas[:25]

	if not top_ofertas:
		print("⚠️ No hay ofertas que cumplan los filtros geográficos.")
		return

	cabecera = (
		f"📊 *INFORME DE SELECCIÓN PROFESIONAL (TOP {len(top_ofertas)})*\n"
		"🎯 _Perfil: Economía & Sistemas de Decisión (Madrid / Remoto)_\n"
		"───────────────────────────\n\n"
	)
	mensajes = []
	mensaje_actual = cabecera
	for indice, oferta in enumerate(top_ofertas, 1):
		titulo = (oferta.get("title") or "Sin título").replace("*", "")
		empresa = (oferta.get("company") or "Empresa confidencial").replace("*", "")
		ubicacion = oferta.get("location") or "No especificada"
		url = oferta.get("job_url") or "#"
		bloque = (
			f"*{indice}. {titulo}*\n"
			f"🏢 *Empresa:* {empresa}\n"
			f"📍 *Ubicación:* {ubicacion}\n"
			f"⭐ *Compatibilidad:* `{oferta['score']}/100`\n"
			f"🔗 [Ver oferta]({url})\n\n"
		)
		if len(mensaje_actual) + len(bloque) > 3900:
			mensajes.append(mensaje_actual)
			mensaje_actual = bloque
		else:
			mensaje_actual += bloque
	if mensaje_actual:
		mensajes.append(mensaje_actual)

	print(f"📤 Enviando {len(mensajes)} mensaje(s) a Telegram...")
	for indice, mensaje in enumerate(mensajes, 1):
		try:
			respuesta = enviar_telegram(token, chat_id, mensaje)
			if respuesta.get("ok"):
				print(f"✅ Parte {indice} enviada con éxito a Telegram.")
			else:
				print(f"❌ Error al enviar la parte {indice}: {respuesta}")
		except requests.RequestException as error:
			print(f"❌ Error de conexión al enviar la parte {indice}: {error}")


if __name__ == "__main__":
	main()

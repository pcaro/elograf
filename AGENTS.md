# Descripción del Proyecto

EloGraf es una utilidad de escritorio escrita en Python que facilita el dictado por voz en Linux integrándose con múltiples motores de reconocimiento de voz, entre ellos nerd-dictation, Whisper Docker, Google Cloud Speech y OpenAI Realtime. La aplicación ofrece una bandeja del sistema, atajos globales y una interfaz avanzada para configurar dispositivos de audio, comandos previos y posteriores, y parámetros específicos de cada motor STT.

## Capacidades principales
- Lanzador gráfico y CLI para iniciar, detener, suspender y reanudar dictado
- Gestión de modelos y descarga desde repositorios remotos
- Persistencia de configuración mediante QSettings y soporte multilenguaje a través de Qt
- Integración IPC (D-Bus/sockets locales) para coordinar con otros componentes del sistema

## Estructura técnica
El código está organizado como un paquete Python con interfaz Qt (PyQt6), controladores específicos para cada motor de voz, un `SystemTrayIcon` que coordina el flujo de dictado y una batería de pruebas unitarias/funcionales en `tests/`. La distribución se gestiona con `pyproject.toml` y `setup.cfg`.

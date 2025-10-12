# Descripción del Proyecto

> **⚠️ DOCUMENTACIÓN DESACTUALIZADA**: Este archivo necesita actualización para reflejar cambios recientes:
> - Añadido método `remove_exit_listener()` a la interfaz STTController
> - Corregida condición de carrera en gestión de exit handlers durante refresh del motor
> - Todas las implementaciones de controladores ahora soportan desregistro de listeners
>
> Ver commit 3feed86 para detalles.

EloGraf es una utilidad de escritorio escrita en Python que facilita el dictado por voz en Linux integrándose con múltiples motores de reconocimiento de voz, entre ellos nerd-dictation, Whisper Docker, Google Cloud Speech y OpenAI Realtime. La aplicación ofrece una bandeja del sistema, atajos globales y una interfaz avanzada para configurar dispositivos de audio, comandos previos y posteriores, y parámetros específicos de cada motor STT.

## Capacidades principales
- Lanzador gráfico y CLI para iniciar, detener, suspender y reanudar dictado
- Gestión de modelos y descarga desde repositorios remotos
- Persistencia de configuración mediante QSettings y soporte multilenguaje a través de Qt
- Integración IPC (D-Bus/sockets locales) para coordinar con otros componentes del sistema

## Estructura técnica
El código está organizado como un paquete Python con interfaz Qt (PyQt6), controladores específicos para cada motor de voz, un `SystemTrayIcon` que coordina el flujo de dictado y una batería de pruebas unitarias/funcionales en `tests/`. La distribución se gestiona con `pyproject.toml` y `setup.cfg`.

## Motores de reconocimiento de voz

### OpenAI Realtime API

La integración con OpenAI Realtime API se implementa en `openai_realtime_controller.py` y utiliza un modelo de comunicación basado en WebSocket para transcripción de voz en tiempo real.

#### Arquitectura

La API de OpenAI Realtime utiliza dos conceptos de modelo distintos:

1. **Modelo de sesión**: Define el comportamiento general de la conexión WebSocket
   - Modelos disponibles: `gpt-4o-realtime-preview`, `gpt-4o-mini-realtime-preview`
   - Se especifica en la URL de conexión WebSocket
   - Controla el motor de conversación general

2. **Modelo de transcripción**: Define el motor específico para transcribir audio a texto
   - Modelos disponibles: `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe`
   - Se especifica en la configuración de `input_audio_transcription`
   - Es independiente del modelo de sesión

#### Configuración de sesión

La configuración inicial de la sesión se envía mediante un evento `session.update`:

```python
{
    "type": "session.update",
    "session": {
        "input_audio_format": "pcm16",  # Formato: PCM 16-bit
        "input_audio_transcription": {
            "model": "gpt-4o-transcribe"  # Modelo de transcripción
        },
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 200,
            "create_response": False  # Solo transcribir, no generar respuestas
        }
    }
}
```

#### Detección de actividad de voz (VAD)

El servidor implementa VAD (Voice Activity Detection) automático que:
- Detecta cuándo el usuario comienza y termina de hablar
- Segmenta el audio en fragmentos lógicos
- Elimina la necesidad de hacer commits manuales del buffer
- Parámetros configurables:
  - `threshold`: Umbral de energía para detectar voz (0.0-1.0)
  - `prefix_padding_ms`: Milisegundos de audio previo a incluir
  - `silence_duration_ms`: Duración de silencio para considerar fin de frase

#### Flujo de datos de audio

1. **Captura**: Audio capturado de PulseAudio mediante `parec`
   - Formato: PCM 16-bit, 16kHz, mono
   - Chunks de 200ms (6400 bytes)
   - Thread dedicado lee continuamente de parec

2. **Envío**: Cada chunk se envía como evento `input_audio_buffer.append`:
```python
{
    "type": "input_audio_buffer.append",
    "audio": base64_encoded_audio
}
```

3. **Detección de voz**: El servidor VAD envía notificaciones:
   - `input_audio_buffer.speech_started`: Detectó inicio de voz
     - Incluye `audio_start_ms`: Timestamp del inicio
     - Incluye `item_id`: ID del elemento de conversación
   - `input_audio_buffer.speech_stopped`: Detectó fin de voz
     - Incluye `audio_end_ms`: Timestamp del fin
   - `input_audio_buffer.committed`: Buffer confirmado para procesamiento
   - `conversation.item.created`: Elemento de conversación creado

4. **Transcripción**: El servidor procesa el audio y envía:
   - `conversation.item.input_audio_transcription.delta`: Fragmentos de transcripción
     - Se reciben múltiples deltas a medida que se procesa el audio
     - Cada delta contiene `item_id`, `content_index` y `delta` (el texto)
     - Ejemplo: "Hola", " buenos", " días", ",", " ¿", "qué", " tal", "?"
   - `conversation.item.input_audio_transcription.completed`: Transcripción final
     - Contiene el `transcript` completo: "Hola buenos días, ¿qué tal?"
     - Incluye `usage` con contadores de tokens

5. **Simulación de entrada**: El texto transcrito se escribe en el sistema
   - Se usa `dotool` (preferido) o `xdotool` (fallback)
   - El texto se escribe donde esté el cursor activo

#### Eventos principales

| Evento | Dirección | Propósito |
|--------|-----------|-----------|
| `session.created` | Servidor → Cliente | Sesión creada con configuración por defecto |
| `session.update` | Cliente → Servidor | Configurar sesión (transcripción, VAD, etc.) |
| `session.updated` | Servidor → Cliente | Confirmación de configuración actualizada |
| `input_audio_buffer.append` | Cliente → Servidor | Enviar chunk de audio |
| `input_audio_buffer.speech_started` | Servidor → Cliente | VAD detectó inicio de voz |
| `input_audio_buffer.speech_stopped` | Servidor → Cliente | VAD detectó fin de voz |
| `input_audio_buffer.committed` | Servidor → Cliente | Buffer de audio confirmado para procesamiento |
| `conversation.item.created` | Servidor → Cliente | Elemento de conversación creado |
| `conversation.item.input_audio_transcription.delta` | Servidor → Cliente | Fragmento de transcripción |
| `conversation.item.input_audio_transcription.completed` | Servidor → Cliente | Transcripción completa con texto final |
| `error` | Servidor → Cliente | Notificación de error |

#### Parámetros de audio

- **Sample rate**: 16000 Hz (requisito de la API)
- **Canales**: 1 (mono)
- **Formato**: PCM 16-bit
- **Tamaño mínimo de chunk**: 100ms de audio
- **Codificación para envío**: Base64

#### Configuración en EloGraf

Los parámetros de OpenAI Realtime se configuran en la pestaña "OpenAI" del diálogo de configuración avanzada:

- **API Key**: Clave de autenticación de OpenAI
- **Model**: Selección del modelo de sesión (dropdown con opciones regular y mini)
- **Language**: Código de idioma para transcripción (ej: "es", "en-US")
- **VAD Threshold**: Sensibilidad de detección de voz
- **VAD Prefix Padding**: Contexto previo en milisegundos
- **VAD Silence Duration**: Duración de silencio para segmentar
- **Sample Rate**: Tasa de muestreo (16000 Hz)
- **Channels**: Número de canales (1 = mono)

#### Implementación

El controlador `OpenAIRealtimeController` hereda de `BaseSTTEngine` e implementa:

1. **Conexión WebSocket**: Establece conexión con `wss://api.openai.com/v1/realtime`
2. **Thread de audio**: Captura audio de PulseAudio en thread separado
3. **Thread de recepción**: Procesa eventos del servidor en thread separado
4. **Manejo de errores**: Reconexión automática opcional
5. **Simulación de entrada**: Envía texto transcrito al sistema mediante `ydotool` o `xdotool`

#### Ejemplo de flujo completo

Un ejemplo real de transcripción de "Hola buenos días, ¿qué tal?":

1. Cliente envía chunks de audio continuamente (cada 200ms)
2. Servidor detecta voz: `input_audio_buffer.speech_started` (audio_start_ms: 308)
3. Cliente sigue enviando audio mientras el usuario habla
4. Servidor detecta silencio: `input_audio_buffer.speech_stopped` (audio_end_ms: 2368)
5. Servidor confirma: `input_audio_buffer.committed`
6. Servidor crea elemento: `conversation.item.created`
7. Servidor envía transcripción incremental:
   - Delta: "Hola"
   - Delta: " buenos"
   - Delta: " días"
   - Delta: ","
   - Delta: " ¿"
   - Delta: "qué"
   - Delta: " tal"
   - Delta: "?"
8. Servidor envía transcripción completa: `conversation.item.input_audio_transcription.completed`
   - transcript: "Hola buenos días, ¿qué tal?"
   - usage: 31 tokens totales (21 input, 10 output)
9. Cliente escribe el texto en el sistema usando `dotool`/`xdotool`

**Duración del ejemplo**: ~2 segundos de audio, procesamiento casi instantáneo

#### Costos aproximados

- **gpt-4o-realtime-preview**: ~$5-10 por hora de audio
- **gpt-4o-mini-realtime-preview**: ~$1-2 por hora de audio

Los modelos mini son más económicos pero pueden tener menor precisión en acentos o ruido de fondo.

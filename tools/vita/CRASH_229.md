# Crash de la compilacion 229: primer frame real de UI

## Avance confirmado

El build probado es `d73977ceaa957a7c4d540a9e9f65b4367a220d5d`.
La primera carga de imagenes termina en 37/37, se completa el traspaso del HUD
nativo a VitaGL y el motor entra en `INITIALIZING USER INTERFACE...`. El log de
Vita3K compila los programas del backend, carga las fuentes TTF y comienza a
registrar iconos del HUD. El final se corta mientras abre pak001.pk4 durante esa
inicializacion; no hay una nueva EXCEPTION_ACCESS_VIOLATION registrada.

Esto es posterior a los crashes de 223-228: ya se esta ejecutando la interfaz
real sobre el renderer VitaGL.

## Reserva de 16 MiB

Inmediatamente despues de dibujar el mensaje de entrada a UI, VitaGL informa que
`gpu_alloc_mapped_aligned_for_cpu` no puede reservar 16,777,216 bytes y necesita
tres ciclos forzados de garbage collection.

La coincidencia de tamano no es accidental:

- `r_rendererUploadMegs` tiene 16 MiB por defecto.
- el perfil general crea cuatro frame buffers: 64 MiB de memoria CPU-mapped;
- `idUploadManager::BeginFrame` llama otra vez a `glBufferData(..., 16 MiB,
  NULL, GL_STREAM_DRAW)` para orphaning;
- en VitaGL, GL_STREAM_DRAW usa `gpu_alloc_mapped_for_cpu`, exactamente la
  funcion que aparece en el log;
- `PrintLoadingMessage("INITIALIZING USER INTERFACE...")` ejecuta BeginFrame
  antes de `uiManager->Init()`, por lo que el orden temporal coincide.

Se investigaron tambien los atlas TTF. Un atlas RGBA 2048x2048 tambien mide
16 MiB, pero la ruta `glTexSubImage2D` de este VitaGL escribe directamente en
la textura. El nombre del allocator y el momento del fallo identifican al VBO
de streaming como la explicacion mas directa de esta reserva concreta.

## Perfil Vita del upload stream

La siguiente compilacion limita solo el perfil Vita:

- maximo 4 MiB por frame buffer;
- exactamente cinco buffers rotatorios;
- no se vuelve a llamar a glBufferData para orphaning en cada BeginFrame.

El VitaGL fijado conserva buffers recientes durante cuatro frames
(`FRAME_PURGE_FREQ=4`). Cinco slots permiten que el uso normal vuelva a un
buffer fuera de esa ventana. Si un slot todavia esta ocupado, la propia ruta
glBufferSubData de VitaGL conserva copy-on-write, pero ahora el bloque maximo es
4 MiB y no 16 MiB.

Con la configuracion por defecto la reserva persistente pasa de 64 MiB a un
maximo de 20 MiB y desaparece el pico adicional de 16 MiB en cada frame. Los
cvars publicos no se reescriben, por lo que la configuracion sigue siendo
portable. Un overflow de frame-temp conserva el fallback estatico que ya tenia
idVertexCache.

Se agregan checkpoints de UI para distinguir fuentes, iconos integrados,
cursores/scrollbars y final de DeviceContext sin aumentar de forma relevante
loading.log.

## Validacion

`test_vita_renderer_upload_policy.py` comprueba el presupuesto 4x5, que cinco
slots superan la ventana de cuatro frames de la dependencia fijada, que la rama
Vita de BeginFrame no contiene glBufferDataARB y que el cap no modifica los
cvars del usuario. El enlace ARM y las compile gates siguen siendo la validacion
obligatoria de CI; solo una ejecucion de Vita3K puede confirmar el comportamiento
del allocator y el siguiente punto de arranque.

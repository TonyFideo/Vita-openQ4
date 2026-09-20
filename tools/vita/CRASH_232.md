# Crash de la compilacion 232: propiedad del framebuffer de diagnostico

## Evidencia nueva

La captura de #232 muestra simultaneamente el HUD nativo de arranque y un atlas
grande de glifos de openQ4. Es una combinacion que el motor no dibuja como una
pantalla normal: el HUD nativo escribe directamente en un bloque CDRAM propio,
mientras que los glifos se crean como recursos de VitaGL.

El log de Vita3K tambien registra, durante el arranque de menus, una reserva
forzada de 4 MiB en gpu_utils.c. Un atlas RGBA de 1024x1024 ocupa exactamente
4 MiB. La aparicion de ese atlas sobre el antiguo HUD es consistente con que
CDRAM liberada haya sido reutilizada mientras el display seguia apuntando a la
direccion antigua.

## Carrera encontrada

openQ4 hacia lo siguiente al primer swap de VitaGL:

1. vglSwapBuffers encola un callback GXM.
2. VitaLoadingHud_EndRendererHandoff llama sceGxmDisplayQueueFinish.
3. VitaDiagScreen_ReleaseBacking libera inmediatamente el framebuffer nativo.

La implementacion actual de Vita3K de sceGxmDisplayQueueFinish solo ejecuta
display_queue.wait_empty(). La cola puede quedar vacia cuando el worker extrae
el callback, antes de que ese callback termine. En vitaGL, el propio callback es
el que llama sceDisplaySetFrameBuf. Por tanto "cola vacia" no demuestra que
SceDisplay haya dejado de usar el framebuffer antiguo.

## Correccion

La liberacion pasa a estar gobernada por propiedad real:

- se sincroniza la cola GXM;
- se cruza un vblank de display;
- se consulta sceDisplayGetFrameBuf;
- si SceDisplay aun devuelve la direccion del framebuffer de diagnostico, el
  bloque CDRAM se conserva;
- los siguientes swaps vuelven a comprobarlo;
- solo se libera cuando SceDisplay confirma una direccion distinta.

No hay sleeps ni numero de frames supuesto. La condicion es el estado real del
subsistema de display y tambien es valida en hardware.

El defineicon lazy introducido en #232 se elimina. Los defineicon vuelven a la
semantica normal del motor: FindMaterial, EnsureNotPurged, SetSort, SizeIcon y
registro inmediato. Se mantienen unicamente las trazas de GPU/mips y el progreso
de parser, porque no alteran el comportamiento del juego.

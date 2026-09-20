# Crash de la compilacion 232: atlas visible y COW del ring de vertices

## Evidencia de #232

La captura de #232 muestra el HUD de arranque y un atlas de glifos grande antes
del cierre. El log llega a INITIALIZING MENUS y, exactamente en esa transicion,
VitaGL informa de una reserva CPU-mapped de 4194304 bytes que falla inicialmente
y solo sale adelante tras forzar un ciclo de garbage collection.

El renderer habia registrado previamente:

    Renderer upload manager: ... buffers=5, ring=4096KB
    UPLOAD VITA: 5 buffers x 4096 KB

Por tanto los 4194304 bytes coinciden exactamente con un slot completo del ring
de streaming de vertices.

## Hipotesis descartadas

La reserva no es el backing RGBA8 de un atlas de 1024x1024. Las texturas
ordinarias de VitaGL usan la ruta GPU-mapped, mientras el mensaje observado
procede de gpu_alloc_mapped_aligned_for_cpu.

Tambien se reviso la implementacion de sceGxmDisplayQueueFinish de Vita3K. El
worker ejecuta el callback de display antes de hacer pop de la cola, de modo que
la explicacion anterior de una cola vacia antes de completar sceDisplaySetFrameBuf
era incorrecta. La comprobacion explicita de propiedad con
sceDisplayGetFrameBuf se conserva como invariante defensivo, pero no se considera
la causa demostrada del crash.

## Contrato real del VBO en VitaGL

En el VitaGL fijado por el port:

- FRAME_PURGE_FREQ es 4.
- un VBO utilizado por un draw recibe last_frame = vgl_framecount.
- glBufferSubData comprueba esa edad.
- si el VBO fue usado en los ultimos cuatro frames, no escribe en el backing
  existente: reserva otro bloque del tamano COMPLETO del VBO y copia todo el
  contenido antes de aplicar el cambio.

El ring de openQ4 tiene cinco VBO de 4 MiB. Hasta #233 se elegia el slot con
tr.frameCount % 5, pero VitaGL decide la seguridad con vgl_framecount, que solo
avanza en vglSwapBuffers. Los dos contadores no representan necesariamente el
mismo ciclo de vida durante carga, UI, capturas o trabajo de frontend.

## Correccion #234

La vida del ring de Vita pasa a seguir el reloj que realmente usa VitaGL:

1. BeginFrame consulta vglGetFrameNumber().
2. Solo selecciona un slot nunca usado o cuya ultima utilizacion tenga mas de
   cuatro frames VitaGL de antiguedad.
3. Si el slot preferido sigue ocupado, busca otro slot seguro.
4. Si excepcionalmente no queda ninguno, glFinish establece una barrera GPU
   real y se reinician las marcas de propiedad.
5. Los datos de frame se escriben mediante glMapBufferRange/glUnmapBuffer sobre
   el backing CPU-mapped ya existente. No se usa glBufferSubData para el ring de
   Vita, por lo que una actualizacion pequena no puede disparar un COW de 4 MiB.

Esto no reduce calidad, no omite recursos, no difiere parsing y no cambia la
semantica de los GUI. El defineicon lazy de #232 permanece eliminado: los iconos
se cargan por la ruta normal del motor.

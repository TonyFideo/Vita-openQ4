# Investigacion del crash de la compilacion 226

## Evidencia y limites

El build probado es 4a6cdf724745e5daf79e6cf1c9c0ab2f0928f0b8. El log de Vita3K aportado el 2026-09-20 contiene tres arranques concatenados. El ultimo llega a `CACHE bypass runtime` y `SOURCE decode: gfx/lights/squarelight1`, despues de `IMG OK 31/37`. No hay lecturas .bimage en ese ultimo arranque. Por tanto, la hipotesis de que basta desactivar la cache no resuelve este crash.

El archivo del emulador termina en mitad de una linea y en un multiplo de 4096 bytes. La ultima linea visible no identifica la instruccion culpable. No se dispone de un backtrace final ni de una ejecucion local de Vita3K con los PK4 del usuario. La imagen del HUD nativo puede seguir mostrando la fase anterior al traspaso al renderer.

## Defectos de textura encontrados en la dependencia fijada

VitaGL eccee6d767ad5f632812414a6b8251031fe62f0b:

- `gpu_alloc_mipmaps` calcula parte de la capacidad con `while (w > 1 && h > 1)`. OpenQ4 produce una cadena hasta que ambas dimensiones son 1. Texturas 1xN/Nx1 y colas rectangulares pueden acabar con niveles subidos fuera de la reserva.
- `_glTexSubImage2D` no comprueba los limites del nivel real y puede utilizar `mip_stride` sin inicializar en la rama que copia una textura usada recientemente. El ancho se calculaba con `orig_w / (2 * level)` en lugar de una reduccion por potencias de dos.
- Algunas transferencias comprimidas usan `w/4, h/4` o `w/8, h/4`; un mip menor que un bloque puede enviar dimensiones cero a GXM.

La correccion comparte una unica distribucion de memoria entre reserva, copia y escritura: offsets, dimensiones y pitch por nivel. Conserva la cadena de mipmaps, repaqueta las filas NPOT al crecer, no modifica el objeto si falla la reserva y evita redimensionar in situ una textura potencialmente en uso. Los mips comprimidos pequenos toman el swizzler de CPU existente. El perfil sigue fijado al mismo VitaGL y conserva los parches previos en `patch_vitagl_vita3k_base.py`.

## Diagnostico de consola

`Sys_Printf`, `Sys_DebugPrintf` y `Sys_DebugVPrintf` pasaban un va_list a `sceClibVprintf`. La implementacion HLE consultada trata ese argumento como argumentos variadicos de registros, a diferencia de `sceClibVsnprintf`, que construye el lector desde una direccion de lista. Esto es consistente con los mensajes ilegibles de los logs. Se formatea con el vsnprintf del toolchain y se envia texto mediante `sceClibPrintf("%s", text)`.

Warnings y errores se guardan adicionalmente en `ux0:data/Vita-OpenQ4/logs/errors.log`, cerrando el descriptor despues de escribir. Se reinicia este archivo en Sys_Init. No se llama al filesystem del motor desde este sumidero. Los mensajes de asignacion de mips incluyen dimensiones, formato en bytes por pixel, niveles y capacidad.

## Pruebas

`VOQ_MIP_SANITIZE=1 python3 -m unittest discover -s tools/vita/tests -p 'test_vita*.py' -v`

Prueba nativa aislada con llamadas de GXM simuladas: 75 combinaciones de dimensiones/formato, generacion y niveles escritos, copy-on-write, fallos de reserva, limites, 1D y NPOT. La transcripcion aislada del calculo anterior para 64x1 produce `heap-buffer-overflow` con AddressSanitizer; la implementacion nueva pasa AddressSanitizer y UndefinedBehaviorSanitizer. El formateador tiene pruebas de strings, enteros, double, 64 bits, porcentaje, truncamiento, nulos y preservacion de va_list.

La comprobacion del cableado del parche usa VITAGL_REPO en CI y se omite localmente si no esta descargada la dependencia. Las pruebas nativas no validan renderizado de Vita, muestreo de GXM ni prueban que este sea el unico fallo del arranque real. Hace falta probar el VPK y comparar los nuevos logs. No se reactivan caches .bimage en este cambio.

## Fuentes

- https://github.com/Rinnegatamante/vitaGL/blob/eccee6d767ad5f632812414a6b8251031fe62f0b/source/utils/gpu_utils.c
- https://github.com/Rinnegatamante/vitaGL/blob/eccee6d767ad5f632812414a6b8251031fe62f0b/source/textures.c
- https://github.com/TonyFideo/Vita-openQ4/blob/4a6cdf724745e5daf79e6cf1c9c0ab2f0928f0b8/src/renderer/Image_load.cpp
- https://github.com/Vita3K/Vita3K/blob/master/vita3k/modules/SceLibKernel/SceLibKernel.cpp
- https://docs.vitasdk.org/group__SceCLibUser.html

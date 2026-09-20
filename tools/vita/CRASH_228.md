# Crash 228: segunda recarga y diagnosticos compactos

## Evidencia

El build probado es ab6092fd38728ae9f8473b8c9d42368a1d74026c. Completa
`IMG OK 37/37` y `IMAGES: RELOAD OK`. A continuacion imprime
`Texture reduction changed, reloading images...` y vuelve a recorrer las imagenes.
La segunda pasada falla en `GPU alloc: makeIntensity(gfx/lights/squarelight1a)`;
Vita3K registra EXCEPTION_ACCESS_VIOLATION / lectura de 0xFFFFFFFFFFFFFFFF.
Esta direccion pertenece al diagnostico del host, no es un PC ARM simbolicable.

No es el mismo punto que #226: la primera carga ya paso squarelight1 y las 37
imagenes. Tampoco demuestra por si solo cual de los cambios de #227 elimino el
bloqueo anterior. No se han aportado un backtrace del host ni errors.log.

## Cambio acotado

ImageManager::Init llama PrimeCvars antes de que la configuracion del usuario se
aplique. Esas opciones quedan marcadas como modificadas aunque la primera carga
real ya usa sus valores. El GLimp de Vita ahora llama PrimeCvars una vez al
inicializar/reutilizar el contexto, antes de esa carga, y registra
`IMAGE policy primed before upload`. No lo llama por frame ni desde EnsureContext.
Los cambios posteriores vuelven a marcar las cvars y siguen funcionando normalmente.
No se desactivan mipmaps, no se ignora una textura ni se reactiva bimage.

Esto elimina el disparador innecesario que muestra el log. No afirma reparar la
causa interna de la violacion del host durante una recarga real. Hace falta probar
el VPK y, si persiste, obtener la siguiente excepcion o traza de liberacion/reserva.

## Tamano de logs

El archivo recibido pesa 29,261,027 bytes (27.9 MiB), pero acumula cuatro lanzamientos.
El ultimo ocupa 7,367,907 bytes. loading.log pesa solamente 9,994 bytes.
Los mensajes dominantes son sondeos de rutas ausentes, sus codigos ENOENT y trazas
de I/O. Cambiar Trace por Info reduce el detalle pero NO elimina warnings/errors
que Vita3K emite por cada archivo no encontrado.

`compact_vita3k_log.py` no altera la configuracion del emulador ni los originales.
Extrae el ultimo lanzamiento (tambien si se concatena a una linea truncada), agrupa
los sondeos ENOENT y conserva las otras advertencias, errores, mensajes del motor,
detalles multilinea y las ultimas 120 lineas sin filtrar. El ZIP conserva SIEMPRE
el ultimo lanzamiento completo byte a byte. La vista compacta no reemplaza esa
copia: un ENOENT tambien puede corresponder a un recurso requerido.

En el archivo recibido: vista compacta 72,535 bytes; ZIP con ultimo arranque completo,
vista compacta, metadatos y loading.log: 261,436 bytes.

Uso (Python 3.10 o posterior, sin dependencias):

```sh
python tools/vita/compact_vita3k_log.py "Vita3K.log" --attach "loading.log" --attach "errors.log"
```

Omitir --attach errors.log si no existe. Se crea una carpeta nueva junto al log;
para reemplazar solamente un informe anterior, usar --overwrite. Para compartir
el diagnostico usar diagnostics.zip. No se comparte ni se cambia automaticamente
ningun archivo. Para contener el log original durante pruebas, archivar el anterior
con Vita3K cerrado y seleccionar nivel Info en lugar de Trace; no desactivar todos
los errores. Las etiquetas de la interfaz dependen de la version del emulador.

## Validacion local

9 pruebas nuevas: 7 del extractor (sesiones concatenadas, linea final parcial,
excepciones y su detalle, copia sin perdida, proteccion del original) y 2 de GLimp.
La prueba nativa ejecuta las funciones reales GLimp_Init y primado extraidas del
fuente con VitaGL/GXM y el estado de imagenes simulados. Cubre inicio valido/fallido,
reutilizacion, cambios posteriores y ausencia de primado por frame. Ejecutada con
Clang, AddressSanitizer y UndefinedBehaviorSanitizer; no equivale a ejecutar Vita3K.

```sh
VOQ_POLICY_SANITIZE=1 python3 -m unittest discover -s tools/vita/tests -p 'test_*.py' -v
```

El workflow de VitaSDK ejecuta los tests por descubrimiento y compila el motor real.
La ejecucion local de esta iteracion cubrio solo las 9 pruebas nuevas; el resto del
repositorio y el enlace ARM se validan en CI.

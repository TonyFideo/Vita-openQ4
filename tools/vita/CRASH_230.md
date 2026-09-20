# Crash de la compilacion 230: entrada a Session/mainmenu

## Resultado de #230

El cambio del upload stream queda validado por el nuevo arranque: el renderer
informa 5 buffers de 4096 KiB y no vuelve a aparecer la reserva fallida de
16,777,216 bytes ni el GC forzado de #229.

El motor completa DeviceContext, carga el modulo de juego, compila main.script,
imprime "game initialized" y entra en Session::Init.

## Ultimo punto observado

Session comienza a cargar guis/mainmenu.gui. InitFromFile hace dos accesos
consecutivos al mismo qpath:

1. ReadFile(qpath, NULL, &timeStamp), que solo consulta metadata.
2. idParser::LoadFile(qpath), que vuelve a abrir el archivo y lee el payload.

El primer acceso encuentra guis/mainmenu.gui en app0:/baseoq4/pak0.pk4 y cierra
el pak correctamente. Inmediatamente comienza el segundo recorrido por los
directorios sueltos y el log de Vita3K termina a mitad de una linea de open_file,
sin EXCEPTION, FATAL ni error de allocator del guest. Esto conserva como
hipotesis principal una terminacion host-side de Vita3K durante el churn de I/O,
el mismo tipo de recorrido que ya obligo a poner el fast-path PK4 para imagenes.

mainmenu.gui es ademas grande: unas 708 KiB, 23,955 lineas y 1,275 windowDef.
Si el fast-path permite superar la segunda apertura, el siguiente riesgo es la
presion de memoria durante su parse.

## Cambio #231

- Los qpaths guis/*.gui prueban primero el hash PK4 en Vita.
- Si no existe una copia empaquetada, se conserva el fallback normal a
  directorios+PK4 para desarrollo/mods.
- fs_vitaLooseGuiOverrides=1 restaura explicitamente el orden original.
- mainmenu registra metadata, entrada/salida de Lexer::LoadFile, entrada/salida
  de Parse, FixupParms y memoria libre user/phycont/cdram.
- Window::Parse informa una muestra cada 128 ventanas para localizar progreso
  dentro del GUI sin inundar loading.log.
- Session::Init marca mundos, FindGui, precarga de recursos, listas,
  GUIs auxiliares y demo/arena.

La telemetria de memoria usa sceKernelGetFreeMemorySize y enlaza SceSysmem_stub.

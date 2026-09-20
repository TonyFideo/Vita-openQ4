# Crash de la compilacion 231: defineicon / icon_repeater

## Lo que cambia respecto de #230

Visualmente ambos fallan en "INITIALIZING MENUS", pero #231 si supera el
punto donde termino #230.

El fast-path de guis/*.gui funciona:

- metadata de guis/mainmenu.gui: OK, 692 KiB;
- segunda apertura del lexer: PK4 directa;
- lexer retorno=1, loaded=1;
- comienza Parse(Desktop).

La memoria reportada justo antes del parse es user=10240 KiB,
phycont=0 KiB, cdram=112640 KiB.

## Ultimo punto exacto

La primera construccion especial del Desktop es:

    defineicon "rpe" "gfx/guis/mainmenu/icon_repeater.tga"

RegisterIcon llamaba EnsureNotPurged de forma sincrona. Eso selecciona el DDS
retail de icon_repeater, lo decodifica correctamente, crea el objeto GPU y
Vita3K termina inmediatamente despues de:

    GPU upload: gfx/guis/mainmenu/icon_repeater

No llega a GPU ready. Por tanto el recorrido PK4 de mainmenu ya no es la
frontera; el nuevo limite esta dentro de SubImageUpload de un recurso que se
estaba cargando como efecto lateral del parser.

## Cambio #232

Los defineicon de GUI se registran de forma lazy en Vita. El parser conserva el
material y el escape code, pero no fuerza EnsureNotPurged. FindIcon hace
residente el material la primera vez que el texto realmente usa ese icono.

Esto es especialmente apropiado para rpe: es un icono del browser de servidores
y no es necesario para construir la pantalla inicial del menu.

Los iconos integrados del DeviceContext conservan la precarga existente porque
RegisterBuiltinIcons usa el valor preload=true por defecto.

Tambien se aumenta la resolucion del diagnostico:

- progreso de mainmenu cada 32 ventanas en vez de 128;
- para gfx/guis/* se registra el plan de upload (dimensiones, niveles, formato,
  compresion);
- se marca antes y despues de cada mip en cadenas pequenas.

Si el parser alcanza el siguiente bloque, #232 demostrara que el crash era el
trabajo GPU prematuro de defineicon. Si el mismo icono falla mas tarde al entrar
al browser, los nuevos datos de mip/formato permiten corregir especificamente
el upload sin bloquear el arranque.

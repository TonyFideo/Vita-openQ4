# Crash de la compilacion 235: agotamiento del heap al cargar GUIs

## Evidencia de los tres logs

El build probado es 70fb809458f9ef12c1dc1dbb7e7111c918dd6206 (Action 235).

El menu principal ya no se detiene en texturas: termina de parsear 2047 ventanas,
completa FixupParms, termina la precarga principal y entra en las GUIs auxiliares.
restart.gui y gameover.gui se abren. q4logo_alpha sube sus diez mipmaps y llega a
GPU ready.

Inmediatamente despues el guest imprime:

    terminate called after throwing an instance of 'std::bad_alloc'

El dump de Vita3K conserva la pila ARM. Simbolizando las direcciones contra el
ELF con debug_info exacto del artefacto #235 se obtiene la cadena:

    __cxa_throw / operator new
        -> idWindow::Parse(idParser *, bool)

La instruccion inmediatamente anterior al retorno dentro de idWindow::Parse
carga 0x1477C como argumento de operator new. Es una reserva de 83,836 bytes:
el sizeof(idWindow) del ejecutable #235.

errors.log contiene advertencias de cvars de mando/gyro/touch no publicadas por
el backend Vita. Son un trabajo real de integracion de input, pero no son la
excepcion que termina esta ejecucion.

## Causa estructural

Window.h de openQ4 contiene:

    wexpOp_t ops[MAX_EXPRESSION_OPS];

wexpOp_t lleva un enum y cuatro intptr_t. En ARM de 32 bits son 20 bytes. Con
MAX_EXPRESSION_OPS=4096 el array ocupa aproximadamente 80 KiB en CADA idWindow,
aunque esa ventana no tenga ninguna expresion.

El mainmenu de Quake 4 construye 2047 ventanas completas en este fork. IsSimple()
se mantiene desactivado porque Quake 4 anima aliases por componente que
idSimpleWindow no representa con semantica completa. Por tanto no es correcto
"arreglar" la memoria volviendo a simplificar ventanas a ciegas.

Solo el array fijo puede superar 160 MiB durante mainmenu, antes de sumar objetos,
scripts, strings, materiales y las GUIs auxiliares. El bad_alloc aparece cuando
la siguiente ventana completa ya no cabe.

## Por que no volver simplemente a idList<wexpOp_t>

El Doom 3 GPL original usaba idList<wexpOp_t> y crecia bajo demanda. openQ4
cambio esto por almacenamiento fijo bajo el comentario "gui crash".

El motivo tecnico sigue existiendo en el parser actual: el operador ternario
guarda un wexpOp_t* y luego llama recursivamente a ParseExpressionPriority para
crear mas operaciones antes de escribir oop->d. Si un idList plano crece y
realoca durante esa recursion, ese puntero queda colgando.

Por eso esta correccion NO restaura ingenuamente el idList relocatable.

## Implementacion

Expression ops pasan a bloques bajo demanda de 32 entradas:

- expressionOpBlocks solo contiene punteros;
- cada bloque wexpOp_t[] se asigna una vez y nunca se mueve;
- la tabla de punteros puede crecer sin invalidar wexpOp_t* ya entregados;
- se mantiene exactamente MAX_EXPRESSION_OPS como limite logico;
- EvaluateRegisters, FixupParms y la lectura de demos acceden mediante
  ExpressionOpAt;
- CommonInit/UpdateFromDictionary liberan todos los bloques correctamente;
- Allocated() vuelve a contabilizar la memoria dinamica real;
- el formato y la evaluacion de expresiones no cambian.

Una ventana sin expresiones ya no paga ~80 KiB. La primera expresion reserva un
bloque de 32 operaciones (aprox. 640 bytes en ARM) y solo crece si lo necesita.

Hay un static_assert especifico de Vita que exige sizeof(idWindow) < 8 KiB para
impedir que un futuro cambio reintroduzca silenciosamente el array gigante.

## Validacion

tools/vita/tests/test_vita_gui_expression_storage.py verifica:

- ausencia del array MAX_EXPRESSION_OPS embebido;
- bloques de direccion estable;
- ausencia de indexacion del viejo array;
- liberacion en reinicializacion;
- mantenimiento del caso ternario que requiere estabilidad de puntero.

La validacion definitiva es la compilacion ARM completa y despues inspeccionar
el ELF resultante: la llamada new idWindow ya no debe solicitar 0x1477C bytes.
La ejecucion en Vita3K sigue siendo necesaria para verificar el siguiente punto
real del arranque.

## Trabajo de menu/input que queda separado

errors.log demuestra que mainmenu referencia opciones de mando, gyro y touch que
el backend Vita aun no implementa. vita_events.cpp actualmente devuelve cero
eventos de joystick y no implementa rumble. Esas opciones deben conectarse a
SceCtrl/SceTouch y al modelo de Usercmd, no silenciarse creando cvars ficticias.
Se aborda despues de eliminar este agotamiento de heap para no mezclar dos
subsistemas en un mismo diagnostico.

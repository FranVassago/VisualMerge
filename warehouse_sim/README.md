# Warehouse Simulator Prototype

Primer prototipo de simulador de almacén desktop (sin navegador) basado en `pygame`.

## Requisitos

- Python 3.11+
- `pip install -r requirements.txt`

## Ejecución

```bash
python warehouse_sim/main.py
```

## Ejecución en Windows (.bat)

Desde `warehouse_sim/`, ejecutar `run_sim.bat`. El script:

- crea `.venv` si no existe
- activa el entorno
- instala/actualiza `pip` solo si falta
- instala `pygame` solo si falta
- arranca con `py main.py`

## Controles

- **Botón derecho + arrastrar**: mover cámara (modo idle)
- **Rueda**: zoom
- **Click izquierdo**: seleccionar un elemento
- **Arrastrar izquierdo**: selección múltiple por recuadro
- **Barra inferior**:
  - Inducción / Cinta / Cinta+Input / Diverter: modo instanciación
  - Borrador: modo borrado (click o drag izquierdo)
  - Guardar / Cargar: `layout.json`
- **Modo instanciación**:
  - `Esc`: cancelar
  - Click derecho: rotar 90°
  - Click izquierdo: instanciar (permanece en modo instanciación para colocar varios)
- **Arriba**:
  - `Play/Pause`
  - `Stop`: elimina todas las cajas en circulación y deja la simulación en pausa
  - `⚙`: abre configuración
- **Config panel**:
  - velocidad de simulación
  - intervalo de polling en inducción para consulta al gestor
  - gris del grid
  - se guarda en `config.ini`

## Notas del modelo de cajas

- Las cajas se mueven de forma fluida.
- El elemento activo de una caja se determina por la celda donde cae el centro de la caja.
- Se registran eventos de entrada y salida en el panel de logs (arriba derecha).
- Capacidad:
  - inducción: hasta 4 cajas
  - resto de elementos: 1 caja
- Diverter de 4 puntos con entrada por izquierda y salidas arriba/derecha/abajo en round-robin.

## Persistencia

- `warehouse_sim/layout.json`: layout del almacén (elementos + cámara)
- `warehouse_sim/config.ini`: parámetros de simulación/UI



## Integración logística (primera versión)

- La inducción ya no genera cajas por temporizador local: hace polling cada `induction_poll_interval` segundos.
- Cada inducción usa su `tag` (scannerId) y llama al endpoint `scan_endpoint`.
- Estado de inductor:
  - **Sin caja**: consulta siguiente caja/tracking y envía `scannerId + barcode + trackingId`.
  - **Con caja en espera**: reintenta con `scannerId + trackingId + decision`.
- Si la decisión devuelta es `0`, la caja queda retenida en el inductor.
- Si la decisión devuelta es `99`, la caja se libera al circuito.
- Códigos `>=400` detienen la simulación, muestran mensaje rojo (truncado) y marcan el elemento con exclamación roja.
- Click derecho en modo normal:
  - sobre **induction** o **belt_input**: panel contextual para editar Tag (único).
  - sobre una caja: panel contextual con ID completo de la caja.
- Las cajas muestran solo los 4 últimos caracteres del ID en la vista principal.

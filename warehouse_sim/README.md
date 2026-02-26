# Warehouse Simulator Prototype

Primer prototipo de simulador de almacén desktop (sin navegador) basado en `pygame`.

## Requisitos

- Python 3.11+
- `pip install -r requirements.txt`

## Ejecución

```bash
python warehouse_sim/main.py
```

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
  - Click izquierdo: instanciar y volver a modo idle
- **Arriba**:
  - `Play/Pause`
  - `Stop`: elimina todas las cajas en circulación
  - `⚙`: abre configuración
- **Config panel**:
  - velocidad de simulación
  - intervalo de spawn en inducción
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


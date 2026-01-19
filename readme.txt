First Commit

---

Documentación de la simulación

Prioridades de decisión (orden estricto)
1) Regla 1 — Caja en salida con stackability A: si una línea esperando en el escáner de salida
   tiene una A en la primera posición, puede pasar.
2) Regla 2 — Saturación >= 85%: si una línea esperando está saturada, puede pasar.
3) Regla 3 — Existe alguna A en el segmento de evaluación: si una línea esperando contiene
   alguna A, puede pasar.
4) Regla 4 — Puntuación ponderada: se calcula la puntuación por línea activa y solo pasan
   líneas en espera que igualan el máximo global. Si ninguna coincide, se espera.
5) Desempate — Prioridad fija: Línea 1 > Línea 2 > Línea 3.

Puertas globales (antes de la Regla 1)
- waitingAtExit: líneas con una caja detenida en el escáner de salida.
- activeLines: líneas con al menos una caja en el segmento de evaluación.
- Si cualquier línea activa tiene una A, solo las líneas en espera que también contienen una A
  son elegibles. Si ninguna línea en espera tiene A, el sistema se mantiene en espera.

Factores usados en los cálculos
- Valores de stackability: A=3, B=2, C=1.
- Saturación: cajas_en_evaluación / capacidad (limitado a 100%).
- Puntuación ponderada: suma de stackability * peso_por_posición, donde las cajas más cercanas
  a la salida tienen pesos mayores (5,4,3,2,1...).

Eventos recurrentes y llamadas de evaluación
- Bucle de ticks (cada 100ms):
  1) Inducción: inserta cajas según cadencia y capacidad.
  2) Movimiento: avanza cajas, aplica bloqueo y actualiza saturación.
  3) Decisión: evalúa reglas globales y libera/retiene.
  4) Renderizado: actualiza UI, métricas, logs y estados de escáneres.
  5) Fin de simulación: detiene cuando todas las secuencias se han procesado.

# Scraper Ecosystem — base endurecida

## Estado real

Este paquete **no debe desplegarse todavía como scraper productivo de REMAJU**. El ZIP de entrada no contenía un flujo real de autenticación, creación de navegador Nodriver ni extracción desde el portal: las estrategias devolvían éxito y datos de muestra. Esta versión elimina ese comportamiento engañoso y falla explícitamente hasta integrar las estrategias reales.

Sí incorpora una base endurecida para el ciclo de vida asíncrono, persistencia SQLite, registro CQRS, cola con reclamación/lease, recuperación y pruebas automatizadas.

## Requisitos

- Python 3.10 o superior.
- Instalar el proyecto y dependencias:
  ```powershell
  python -m pip install -e ".[test]"
  ```
- Para el navegador real, instalar/configurar la versión de Chrome compatible con Nodriver según el entorno operativo.

## Comandos

```powershell
python main.py migrate
python main.py run --name remaju
python -m pytest -q
```

En Windows PowerShell, la verificación automatizada de esta base es:

```powershell
.\scripts\verify.ps1
```

`python main.py run --name remaju` actualmente debe fallar con un mensaje claro de integración pendiente. No escribe datos ficticios ni afirma que el portal se haya consultado.

## Base SQLite

Por defecto, la base se crea en `storage/blackboard.db` bajo la raíz del proyecto. Para usar una ruta absoluta distinta:

```powershell
$env:SCRAPER_ECOSYSTEM_DB_PATH = "D:\datos\scraper_ecosystem\blackboard.db"
```

No cambie esa variable entre comandos si se espera operar sobre la misma base.

## Ciclo de vida asíncrono

El CLI ejecuta `initialize`, `run` y `cleanup` en una única llamada a `asyncio.run()`. `cleanup` se intenta siempre y se ejecuta antes de que termine el bucle de eventos. Si la operación principal falla y también falla la limpieza, se conserva la excepción principal y se registra el fallo de limpieza.

## Antes de producción real

1. Implementar autenticación REMAJU con el DOM/flujo real y validar login exitoso.
2. Implementar extracción real y validar campos contra HTML real; no inferir columnas.
3. Crear/cerrar navegador y pestañas dentro del mismo bucle de eventos.
4. Añadir pruebas de integración controladas con navegador/portal de pruebas.
5. Definir configuración de credenciales fuera del código y secretos fuera del repositorio.
6. Definir operación de consumidores SUNARP/CEJ y la planificación transaccional de tareas.
7. Ejecutar pruebas en la misma versión de Python/Windows/Chrome de producción.

No declarar el sistema productivo hasta completar y validar estos puntos.

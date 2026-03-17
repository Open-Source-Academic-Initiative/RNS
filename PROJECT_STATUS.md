# Estado del Proyecto: SECOP II - Radar TI

## 1. Descripción General
Aplicación web diseñada para la vigilancia tecnológica de contratación pública en Colombia. Utiliza la API de Datos Abiertos (Socrata) para identificar, filtrar y visualizar oportunidades de negocio en el sector de TI (Software, Hardware, Servicios) en tiempo real, aplicando criterios de elegibilidad específicos (presupuesto, ubicación, vigencia).

## 2. Estado Actual (Snapshot)
*   **Funcionalidad**: Operativa. Extrae datos reales, filtra por 10+ palabras clave de TI, permite ordenamiento y detalle visual.
*   **Calidad de Datos**: Alta. Validación de fecha de cierre (`fecha_de_recepcion_de`) implementada.
*   **Deuda Técnica**: Alta.
    *   Acoplamiento fuerte entre lógica de presentación y acceso a datos.
    *   Ausencia de tipado estricto en las respuestas de la API.
    *   Manejo de errores disperso.
    *   Estructura monolítica (todo en raíz).

## 3. Arquitectura Objetivo (DDD & Clean Architecture)
Se migrará de un script monolítico a una arquitectura en capas:

```mermaid
graph TD
    User((Usuario)) --> UI[Capa Presentación (FastAPI/HTML)]
    UI --> App[Capa Aplicación (Casos de Uso)]
    App --> Domain[Capa Dominio (Entidades & Interfaces)]
    Infra[Capa Infraestructura (Socrata Adapter)] --> Domain
    App --> Infra
```

### Stack Tecnológico
*   **Lenguaje**: Python 3.12+
*   **Framework Web**: FastAPI
*   **Servidor**: Uvicorn
*   **Motor de Plantillas**: Jinja2
*   **Estilos**: TailwindCSS (CDN)
*   **Validación de Datos**: Pydantic V2
*   **Cliente HTTP**: Requests (con gestión de timeouts y retries)
*   **Testing**: Unittest / Pytest

## 4. Estándares de Calidad y Seguridad (OWASP)
*   **Input Validation**: Uso de modelos Pydantic para sanear entradas de query params (prevención de inyecciones).
*   **Output Encoding**: Escapado automático vía Jinja2 (prevención XSS).
*   **Error Handling**: Centralizado, sin exponer stack traces al cliente.
*   **Secure Headers**: Implementación de Middleware para cabeceras HTTP seguras.

## 5. Próximos Pasos
1.  Reestructuración de carpetas (`src/domain`, `src/infra`, `src/app`).
2.  Implementación de contratos (Interfaces de Repositorio).
3.  Inyección de dependencias en `main.py`.
4.  Ejecución de suite de pruebas renovada.
